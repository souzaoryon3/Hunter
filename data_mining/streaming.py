"""Consumidor continuo RabbitMQ e outbox de observacoes; ACK somente apos commit."""
import asyncio
import hashlib
import json
import logging
from contextlib import suppress
from decimal import Decimal
from statistics import pstdev

import asyncpg

from config.settings import assert_runtime_role
from data_mining.repository import REAL_SOURCES
from messaging.broker import connect
from messaging.config import Settings
from messaging.runtime import configure_logging

log = logging.getLogger('hunter.analytics')


def rolling_metrics(prices):
    """Janela por contagem, ordem cronologica; ultimo preco nao entra no baseline."""
    values = [Decimal(str(p)) for p in prices]
    if not 1 <= len(values) <= 20 or any(not p.is_finite() or p <= 0 for p in values):
        raise ValueError('Janela invalida')
    previous = values[:-1]
    change = float((values[-1] / values[-2] - 1) * 100) if previous else None
    z = None
    if len(previous) >= 5:
        deviation = pstdev(previous)
        if deviation > 0:
            z = float((values[-1] - sum(previous) / len(previous)) / deviation)
    return dict(window_size=len(values), price=values[-1],
                mean_price=sum(values) / len(values), min_price=min(values), max_price=max(values),
                change_percent=change, drop_detected=change is not None and change <= -5,
                z_score=z, anomaly=abs(z) >= 3 if z is not None else None)


def event_id(body):
    if len(body) > 4096:
        raise ValueError('Mensagem excede limite')
    try:
        payload = json.loads(body)
        value = payload['event_id']
        if type(payload['version']) is not int or payload['version'] != 1 or type(value) not in (str, int):
            raise ValueError()
        # Identificador canonico, sem aceitar floats ou inteiros fora do BIGINT.
        number = int(value)
        if str(number) != str(value) or not 0 < number < 2**63:
            raise ValueError()
        return number
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, RecursionError):
        raise ValueError('Contrato de evento invalido') from None


def checked_table(table):
    if table not in ('hunter_analytics_events', 'hunter_nlp_events'):
        raise ValueError('Tabela de eventos desconhecida')
    return table


async def publish_pending(pool, broker, settings, event_table='hunter_analytics_events'):
    table = checked_table(event_table)
    count = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(f'''SELECT observation_id,status FROM {table}
                WHERE (status IN ('pending','dead_pending') AND available_at<=now())
                   OR (status='published' AND published_at<now()-$1*interval '1 second')
                ORDER BY observation_id LIMIT 50 FOR UPDATE SKIP LOCKED''', settings.recovery_seconds)
            for row in rows:
                dead = row['status'] == 'dead_pending'
                await broker.publish(row['observation_id'], dead=dead)
                await conn.execute(f'''UPDATE {table} SET status=$2,
                    published_at=clock_timestamp(),publications=publications+1
                    WHERE observation_id=$1''', row['observation_id'], 'dead' if dead else 'published')
                count += 1
    return count


async def process_event(conn, observation_id):
    """Uma transacao serializa duplicatas; resultado e status sao atomicos."""
    async with conn.transaction():
        event = await conn.fetchrow('''SELECT * FROM hunter_analytics_events
            WHERE observation_id=$1 FOR UPDATE''', observation_id)
        if not event:
            return 'unknown'
        if event['status'] in ('processed', 'dead_pending', 'dead'):
            return 'duplicate'
        if event['failures'] and event['available_at'] > await conn.fetchval('SELECT now()'):
            return 'deferred'
        observation = await conn.fetchrow('SELECT * FROM hunter_price_observations WHERE id=$1', observation_id)
        # Baseline limitado a vinte pontos ate o tempo do evento, incluindo atrasados.
        rows = await conn.fetch('''SELECT preco FROM (
            SELECT DISTINCT ON (coletado_em) preco,coletado_em,id
            FROM hunter_price_observations WHERE produto_id=$1
              AND fonte_coleta=ANY($2::text[]) AND coletado_em<=now()
              AND (coletado_em,id)<=($3,$4)
            ORDER BY coletado_em DESC,id DESC LIMIT 20
            ) sample ORDER BY coletado_em,id''', observation['produto_id'], list(REAL_SOURCES),
            observation['coletado_em'], observation_id)
        if not rows or observation['coletado_em'] > await conn.fetchval('SELECT now()'):
            raise ValueError('Observacao futura ou janela vazia')
        metrics = rolling_metrics([row['preco'] for row in rows])
        await conn.execute('''INSERT INTO hunter_analytics_results(
            observation_id,produto_id,event_time,replay,window_size,price,mean_price,min_price,
            max_price,change_percent,drop_detected,z_score,anomaly)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)''', observation_id,
            observation['produto_id'], observation['coletado_em'], event['replay'],
            *(metrics[k] for k in ('window_size','price','mean_price','min_price','max_price',
                                   'change_percent','drop_detected','z_score','anomaly')))
        await conn.execute('''UPDATE hunter_analytics_events SET status='processed',
            processed_at=clock_timestamp(),error_code=NULL WHERE observation_id=$1''', observation_id)
    return 'processed'


async def handle_message(message, pool, broker, settings, processor=None,
                         event_table='hunter_analytics_events'):
    table = checked_table(event_table)
    try:
        identity = event_id(message.body)
    except ValueError:
        await broker.quarantine(hashlib.sha256(message.body).hexdigest())
        await message.ack()
        return
    try:
        async with pool.acquire() as conn:
            outcome = await (processor or process_event)(conn, identity)
    except (ValueError, ArithmeticError) as exc:
        # Falha de dados: retry duravel e limitado. Infraestrutura propaga sem ACK.
        async with pool.acquire() as conn:
            await conn.execute(f'''UPDATE {table} SET failures=failures+1,
                status=CASE WHEN failures+1 >= $2 THEN 'dead_pending' ELSE 'pending' END,
                available_at=now()+$3*interval '1 second',error_code=$4
                WHERE observation_id=$1 AND status NOT IN ('processed','dead','dead_pending')''',
                identity, settings.max_attempts, settings.retry_seconds, type(exc).__name__)
        outcome = 'retry'
    if outcome == 'unknown':
        await broker.quarantine(hashlib.sha256(message.body).hexdigest())
    await message.ack()
    log.info('Evento analitico id=%s resultado=%s', identity, outcome)


async def publishing(pool, broker, settings, event_table='hunter_analytics_events'):
    while True:
        count = await publish_pending(pool, broker, settings, event_table)
        if count:
            log.info('Eventos analiticos publicados=%s', count)
        await asyncio.sleep(1)


async def consuming(pool, broker, settings, processor=None, event_table='hunter_analytics_events'):
    async with broker.work.iterator() as messages:
        async for message in messages:
            try:
                await handle_message(message, pool, broker, settings, processor, event_table)
            except Exception:
                if not message.processed:
                    await message.nack(requeue=True)
                raise


async def run(*, purpose='analytics', event_table='hunter_analytics_events', processor=None):
    checked_table(event_table)
    if {'analytics':'hunter_analytics_events','nlp':'hunter_nlp_events'}.get(purpose) != event_table:
        raise ValueError('Fila e tabela de eventos incompativeis')
    settings = Settings.environment()
    while True:
        try:
            async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=5) as pool:
                async with pool.acquire() as conn:
                    await assert_runtime_role(conn)
                    if not await conn.fetchval('SELECT to_regclass($1)', event_table):
                        raise ValueError('Aplique as migracoes antes de iniciar')
                async with connect(settings, purpose=purpose) as broker:
                    log.info('Streaming conectado; fila=%s', broker.work.name)
                    tasks = [asyncio.create_task(publishing(pool, broker, settings, event_table)),
                             asyncio.create_task(consuming(pool, broker, settings, processor, event_table))]
                    try:
                        await asyncio.gather(*tasks)
                    finally:
                        for task in tasks:
                            task.cancel()
                        for task in tasks:
                            with suppress(asyncio.CancelledError, Exception):
                                await task
        except Exception as exc:
            log.error('Streaming interrompido: %s; reconectando', type(exc).__name__)
            await asyncio.sleep(5)


if __name__ == '__main__':
    configure_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
