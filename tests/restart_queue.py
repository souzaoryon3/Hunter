"""Prova em duas fases de recuperação; reinício Docker é feito explicitamente fora deste script."""
import argparse
import asyncio
import json
from pathlib import Path
import secrets
import sys
import uuid
from dataclasses import replace

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from messaging.broker import connect
from messaging.config import Settings
from messaging.service import dispatch, handle_message, process, scan
from messaging.testing import require_isolated

LOCAL = Path(__file__).resolve().parents[1] / '.hunter-recovery.local.json'


async def run(phase):
    settings = Settings.environment()
    require_isolated(settings)
    conn = await asyncpg.connect(settings.database_url)
    try:
        if phase == 'prepare':
            marker = 'Recovery' + secrets.token_hex(8)
            settings = replace(settings, prefix='hunter_test_recovery_' + secrets.token_hex(6))
            async with conn.transaction():
                user = await conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES ('Teste Recuperacao',$1,'test-only-unusable-hash') RETURNING id", marker.lower()+'@example.com')
                alerts = []
                for index in range(4):
                    name = marker + str(index)
                    await conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,90,'https://example.com/recovery')", name)
                    alerts.append(await conn.fetchval('INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES ($1,$2,100) RETURNING id', user, name))
                await scan(conn)
                events = [await conn.fetchval('SELECT id FROM hunter_events WHERE alerta_id=$1', alert) for alert in alerts]
            async with connect(settings) as broker:
                for event in events[:2]:
                    await broker.publish(event)
                    await conn.execute("UPDATE hunter_events SET status='published',published_at=clock_timestamp(),updated_at=clock_timestamp() WHERE id=$1", event)
                message = await broker.work.get(timeout=5)
                assert json.loads(message.body)['event_id'] in [str(e) for e in events[:2]]
                # Fecha o canal sem ACK: a entrega deve voltar para a fila durável.
            def fail(_):
                raise RuntimeError('RecoveryTestFailure')
            assert await process(conn, events[2], settings, fail) == 'retry'
            assert await conn.fetchval('SELECT status FROM hunter_events WHERE id=$1', events[3]) == 'pending'
            LOCAL.write_text(json.dumps({'prefix':settings.prefix,'user':user,'events':[str(e) for e in events]}), encoding='utf-8')
            print('Preparado: mensagem pronta, entrega sem ACK, evento retry e outbox pendente; somente fixtures no banco isolado.')
        else:
            fixture = json.loads(LOCAL.read_text(encoding='utf-8'))
            settings = replace(settings, prefix=fixture['prefix'])
            require_isolated(settings)
            events = [uuid.UUID(e) for e in fixture['events']]
            assert await conn.fetchval('SELECT count(*) FROM hunter_events WHERE id=ANY($1::uuid[])', events) == 4
            async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=2) as pool:
                async with connect(settings) as broker:
                    # Esses dois eventos são consumidos antes de qualquer republicação.
                    recovered = set()
                    for _ in range(2):
                        message = await broker.work.get(timeout=10)
                        recovered.add(uuid.UUID(json.loads(message.body)['event_id']))
                        await handle_message(message, pool, broker, settings)
                    assert recovered == set(events[:2]), 'Mensagens não sobreviveram no broker'
                    await dispatch(conn, broker, settings)
                    for _ in range(2):
                        message = await broker.work.get(timeout=10)
                        await handle_message(message, pool, broker, settings)
                    # Nova entrega do mesmo evento após reinício não pode duplicar efeito.
                    await broker.publish(events[0])
                    message = await broker.work.get(timeout=10)
                    await handle_message(message, pool, broker, settings)
            assert await conn.fetchval("SELECT count(*) FROM hunter_events WHERE id=ANY($1::uuid[]) AND status='processed'", events) == 4
            assert await conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE event_id=ANY($1::uuid[])', events) == 4
            assert await conn.fetchval('SELECT attempts FROM hunter_events WHERE id=$1', events[2]) == 2
            print('OK: após reinício RabbitMQ/PostgreSQL, mensagens persistidas e sem ACK recuperadas; retry e outbox concluídos; 4 notificações únicas.')
    finally:
        await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare','verify'])
    asyncio.run(run(parser.parse_args().phase))
