"""Fixtures e inspeção da demonstração, limitadas ao Docker de testes."""
import argparse
import asyncio
import json
import secrets
from pathlib import Path

import asyncpg
from passlib.context import CryptContext
from messaging.broker import connect
from messaging.config import Settings
from messaging.service import scan
from messaging.testing import require_isolated
from messaging.runtime import configure_logging

LOCAL = Path(__file__).resolve().parents[1] / '.hunter-demo.local.json'


def simulated_failure(event):
    if json.loads(event['payload']).get('_demo_failure'):
        raise RuntimeError('SimulatedDemoFailure')


async def run(action):
    settings = Settings.environment()
    require_isolated(settings)
    conn = await asyncpg.connect(settings.database_url)
    try:
        if action == 'seed':
            if LOCAL.exists():
                print('Demonstração local já configurada. Use status, duplicate ou failure.')
                return
            password = secrets.token_urlsafe(18)
            marker = 'HunterDemo' + secrets.token_hex(4)
            email = marker.lower() + '@example.com'
            async with conn.transaction():
                user = await conn.fetchval('INSERT INTO usuarios(nome,email,senha) VALUES ($1,$2,$3) RETURNING id', 'Demonstração Hunter', email, CryptContext(schemes=['bcrypt']).hash(password))
                await conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,90,'https://example.com/demo')", marker)
                alert = await conn.fetchval('INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES ($1,$2,100) RETURNING id', user, marker)
            LOCAL.write_text(json.dumps(dict(email=email, senha=password, usuario_id=user, alerta_id=alert), ensure_ascii=False), encoding='utf-8')
            print('Usuário e oferta sintéticos criados somente no banco isolado. Login no arquivo local ignorado .hunter-demo.local.json; não o versione nem compartilhe.')
            return
        demo = json.loads(LOCAL.read_text(encoding='utf-8'))
        if action == 'failure':
            # Evento de falha é criado antes de subir o agendador, na mesma transação
            # que adiciona a marca de simulação. Nunca mexe em dados reais.
            async with conn.transaction():
                term = 'HunterDemoFalha' + secrets.token_hex(4)
                await conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,80,'https://example.com/demo-failure')", term)
                alert = await conn.fetchval('INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES ($1,$2,100) RETURNING id', demo['usuario_id'], term)
                await scan(conn)
                await conn.execute("UPDATE hunter_events SET payload=payload || '{\"_demo_failure\":true}'::jsonb WHERE alerta_id=$1", alert)
            print('Evento sintético de falha criado. O worker --demo-failures enviará à DLQ após o limite configurado.')
        elif action == 'duplicate':
            event = await conn.fetchval("SELECT id FROM hunter_events WHERE alerta_id=$1 ORDER BY generation DESC LIMIT 1", demo['alerta_id'])
            if not event:
                raise ValueError('Execute o agendador antes de duplicar o evento.')
            async with connect(settings) as broker:
                await broker.publish(event)
                await broker.publish(event)
            print('Mesmo evento publicado duas vezes. A notificação deve permanecer única.')
        elif action == 'status':
            events = await conn.fetch('''SELECT id,status,attempts,publish_attempts,last_error,
                created_at,published_at,processed_at FROM hunter_events WHERE usuario_id=$1 ORDER BY created_at''', demo['usuario_id'])
            for event in events:
                print(json.dumps(dict(event), default=str))
            print('Notificações:', await conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE usuario_id=$1', demo['usuario_id']))
            logs = await conn.fetch('''SELECT l.phase,l.attempt,l.status,l.error_code,l.started_at,l.finished_at
                FROM hunter_processing_log l JOIN hunter_events e ON e.id=l.event_id
                WHERE e.usuario_id=$1 ORDER BY l.id''', demo['usuario_id'])
            for row in logs:
                print(json.dumps(dict(row), default=str))
    finally:
        await conn.close()


if __name__ == '__main__':
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['seed','failure','duplicate','status'])
    try:
        asyncio.run(run(parser.parse_args().action))
    except Exception as exc:
        print('Demonstração não concluída: ' + type(exc).__name__ + '. Confira o ambiente isolado.')
        raise SystemExit(1) from None
