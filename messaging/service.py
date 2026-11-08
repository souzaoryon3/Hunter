"""Outbox PostgreSQL: detecção, entrega recuperável e processamento idempotente."""
import hashlib
import json
import uuid

from messaging.catalog import catalog_sql


def fingerprint(produto, preco):
    return hashlib.sha256(json.dumps([produto, float(preco)], ensure_ascii=False).encode()).hexdigest()


async def scan(conn):
    created = 0
    catalog = await catalog_sql(conn)
    async with conn.transaction():
        # Uma varredura por vez, mesmo se houver dois agendadores.
        if not await conn.fetchval('SELECT pg_try_advisory_xact_lock(281233)'):
            return 0
        alerts = await conn.fetch('SELECT id, usuario_id, produto, preco FROM alertas_preco ORDER BY id FOR UPDATE')
        for alert in alerts:
            signature = fingerprint(alert['produto'], alert['preco'])
            await conn.execute('''INSERT INTO hunter_alert_state(alerta_id, fingerprint)
                                  VALUES ($1,$2) ON CONFLICT DO NOTHING''', alert['id'], signature)
            state = await conn.fetchrow('SELECT * FROM hunter_alert_state WHERE alerta_id=$1 FOR UPDATE', alert['id'])
            offer = await conn.fetchrow(f'''SELECT nome, preco, link, loja FROM ({catalog}) p
                WHERE strpos(lower(p.nome), lower($1)) > 0 AND preco > 0
                ORDER BY preco, nome, loja, link LIMIT 1''', alert['produto'])
            reached = offer is not None and offer['preco'] <= alert['preco']
            transition = reached and (not state['reached'] or state['fingerprint'] != signature)
            generation = state['generation'] + int(transition)
            if transition:
                payload = dict(produto=offer['nome'], preco=float(offer['preco']),
                               preco_desejado=float(alert['preco']), loja=offer['loja'], link=offer['link'])
                await conn.execute('''INSERT INTO hunter_events
                    (id, alerta_id, usuario_id, generation, fingerprint, payload)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb) ON CONFLICT DO NOTHING''',
                    uuid.uuid4(), alert['id'], alert['usuario_id'], generation, signature, json.dumps(payload))
                created += 1
            await conn.execute('''UPDATE hunter_alert_state SET fingerprint=$2, reached=$3,
                generation=$4, checked_at=clock_timestamp() WHERE alerta_id=$1''',
                alert['id'], signature, reached, generation)
    return created


async def audit(conn, event_id, phase, attempt, status, started, error=None):
    await conn.execute('''INSERT INTO hunter_processing_log
        (event_id, phase, attempt, status, started_at, error_code) VALUES ($1,$2,$3,$4,$5,$6)''',
        event_id, phase, attempt, status, started, error)


async def dispatch(conn, broker, settings, limit=100):
    sent = 0
    for _ in range(limit):
        async with conn.transaction():
            event = await conn.fetchrow('''SELECT * FROM hunter_events
                WHERE (status IN ('pending','retry','dead_pending') AND next_attempt_at <= now())
                   OR (status='published' AND updated_at < now() - $1 * interval '1 second')
                ORDER BY next_attempt_at, created_at FOR UPDATE SKIP LOCKED LIMIT 1''', settings.recovery_seconds)
            if not event:
                break
            started = await conn.fetchval('SELECT clock_timestamp()')
            dead = event['status'] == 'dead_pending'
            attempt = event['publish_attempts'] + 1
            try:
                await broker.publish(event['id'], dead=dead)
            except Exception as exc:
                # Não registrar mensagens de exceção, que podem incluir URLs com segredos.
                error = type(exc).__name__
                await conn.execute('''UPDATE hunter_events SET publish_attempts=$2, last_error=$3,
                    next_attempt_at=now()+$4 * interval '1 second', updated_at=now() WHERE id=$1''',
                    event['id'], attempt, error, settings.retry_seconds)
                await audit(conn, event['id'], 'dead_letter' if dead else 'publish', attempt, 'failed', started, error)
                break
            await conn.execute('''UPDATE hunter_events SET status=$2, publish_attempts=$3,
                published_at=clock_timestamp(), updated_at=clock_timestamp(),
                processed_at=CASE WHEN $2='dead' THEN clock_timestamp() ELSE processed_at END,
                last_error=CASE WHEN $2='dead' THEN last_error ELSE NULL END WHERE id=$1''',
                event['id'], 'dead' if dead else 'published', attempt)
            await audit(conn, event['id'], 'dead_letter' if dead else 'publish', attempt, 'confirmed', started)
            sent += 1
    return sent


class UnknownEvent(ValueError):
    pass


async def process(conn, event_id, settings, fault=None):
    """Resultado e notificação no mesmo commit. Duplicatas nunca criam novo aviso."""
    async with conn.transaction():
        # Ordem de lock igual à varredura: alerta antes do evento.
        owner = await conn.fetchrow('SELECT alerta_id FROM hunter_events WHERE id=$1', event_id)
        if not owner:
            raise UnknownEvent()
        alert = await conn.fetchrow('SELECT * FROM alertas_preco WHERE id=$1 FOR UPDATE', owner['alerta_id']) if owner['alerta_id'] else None
        event = await conn.fetchrow('SELECT * FROM hunter_events WHERE id=$1 FOR UPDATE', event_id)
        if not event:
            raise UnknownEvent()
        if event['status'] in ('processed','cancelled','dead_pending','dead'):
            await audit(conn, event_id, 'consume', event['attempts'], 'duplicate',
                        await conn.fetchval('SELECT clock_timestamp()'))
            return event['status']
        if event['status'] == 'retry' and event['next_attempt_at'] > await conn.fetchval('SELECT clock_timestamp()'):
            return 'retry'
        started = await conn.fetchval('SELECT clock_timestamp()')
        attempt = event['attempts'] + 1
        if not alert or fingerprint(alert['produto'], alert['preco']) != event['fingerprint']:
            await conn.execute("UPDATE hunter_events SET status='cancelled', processed_at=clock_timestamp(), updated_at=clock_timestamp() WHERE id=$1", event_id)
            await audit(conn, event_id, 'consume', attempt, 'cancelled', started, 'AlertDeletedOrChanged')
            return 'cancelled'
        try:
            async with conn.transaction():  # savepoint: falha não deixa notificação parcial.
                if fault:
                    fault(event)
                data = json.loads(event['payload'])
                await conn.execute('''INSERT INTO hunter_notifications
                    (event_id, usuario_id, produto, preco, preco_desejado, loja, link)
                    VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (event_id) DO NOTHING''',
                    event_id, event['usuario_id'], data['produto'], data['preco'], data['preco_desejado'], data['loja'], data['link'])
        except Exception as exc:
            error = type(exc).__name__
            status = 'dead_pending' if attempt >= settings.max_attempts else 'retry'
            await conn.execute('''UPDATE hunter_events SET status=$2, attempts=$3, last_error=$4,
                next_attempt_at=now()+$5 * interval '1 second', updated_at=now() WHERE id=$1''',
                event_id, status, attempt, error, settings.retry_seconds * 2 ** min(attempt - 1, 5))
            await audit(conn, event_id, 'consume', attempt, status, started, error)
            return status
        await conn.execute("UPDATE hunter_events SET status='processed', attempts=$2, processed_at=clock_timestamp(), updated_at=clock_timestamp(), last_error=NULL WHERE id=$1", event_id, attempt)
        await audit(conn, event_id, 'consume', attempt, 'processed', started)
        return 'processed'


async def handle_message(message, pool, broker, settings, fault=None):
    try:
        try:
            if len(message.body) > 4096:
                raise ValueError()
            data = json.loads(message.body)
            if not isinstance(data, dict) or data.get('version') != 1:
                raise ValueError()
            event_id = uuid.UUID(data['event_id'])
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise UnknownEvent()
        async with pool.acquire() as conn:
            await process(conn, event_id, settings, fault)
    except UnknownEvent:
        digest = hashlib.sha256(message.body).hexdigest()
        async with pool.acquire() as conn:
            await conn.execute('''INSERT INTO hunter_message_rejections(body_hash, error_code)
                VALUES ($1,'InvalidOrUnknownEvent') ON CONFLICT(body_hash) DO UPDATE
                SET deliveries=hunter_message_rejections.deliveries+1, last_seen_at=now()''', digest)
        # Confirma a cópia na DLQ antes de remover a mensagem inválida da fila principal.
        await broker.quarantine(digest)
    await message.ack()
