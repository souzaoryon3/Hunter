"""Demonstra PLN e mineracao com processos/broker reais; somente banco isolado."""
import asyncio
import json
import os
import secrets
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from messaging.broker import connect
from messaging.config import Settings
from messaging.testing import require_isolated


async def demonstrate():
    settings = Settings.environment()
    require_isolated(settings)
    settings = replace(settings, prefix='hunter_test_nlp_demo_'+secrets.token_hex(6))
    env = dict(os.environ, HUNTER_QUEUE_PREFIX=settings.prefix)
    marker = 'NlpDemo'+secrets.token_hex(6)
    title = 'Teclado Mecânico para Jogos '+marker
    conn = await asyncpg.connect(settings.database_url)
    processes = []
    try:
        for module in ('nlp.streaming','data_mining.streaming'):
            processes.append(await asyncio.create_subprocess_exec(sys.executable, '-B', '-m', module,
                env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL))
        pid = await conn.fetchval('''INSERT INTO hunter_catalog_products(loja,link)
            VALUES('KaBuM!',$1) RETURNING id''', 'https://example.com/'+marker)
        identity = await conn.fetchval('''INSERT INTO hunter_price_observations(
            produto_id,nome,preco,coletado_em,fonte_coleta,fonte_url)
            VALUES($1,$2,100,$3,'http_publico','https://example.com/nlp-fixture') RETURNING id''',
            pid, title, datetime.now(timezone.utc)-timedelta(seconds=10))
        for _ in range(450):
            row = await conn.fetchrow('''SELECT n.*,a.mean_price FROM hunter_text_results n
                JOIN hunter_analytics_results a USING(observation_id)
                WHERE n.observation_id=$1''', identity)
            if row:
                break
            if any(p.returncode is not None for p in processes):
                raise RuntimeError('Consumidor encerrou antes do resultado')
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('PLN e mineracao nao integraram o evento em 45 segundos')
        assert row['category'] == 'teclado'
        assert 'mecanico' in row['tokens'] and 'para' not in row['tokens']
        assert not row['replay']
        async with connect(settings, purpose='nlp') as broker:
            await broker.publish(identity)
            await asyncio.sleep(1)
        count = await conn.fetchval('SELECT count(*) FROM hunter_text_results WHERE observation_id=$1', identity)
        assert count == 1
        return {'status':'aprovado','fixture_sintetica':True,'ambiente':'hunter_test isolado',
                'fila':settings.prefix+'.nlp','marker':marker,'titulo':title,
                'duplicata_sem_efeito':True,'resultado_integrado':dict(row)}
    finally:
        for process in processes:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 10)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        await conn.close()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(demonstrate()), default=str, ensure_ascii=False))
