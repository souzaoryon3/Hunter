"""Prova executavel de streaming; fixtures apenas no PostgreSQL/RabbitMQ isolados."""
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


async def main():
    settings = Settings.environment()
    require_isolated(settings)
    settings = replace(settings, prefix='hunter_test_stream_demo_'+secrets.token_hex(6))
    env = dict(os.environ, HUNTER_QUEUE_PREFIX=settings.prefix)
    conn = await asyncpg.connect(settings.database_url)
    process = None
    try:
        pid = await conn.fetchval('''INSERT INTO hunter_catalog_products(loja,link)
            VALUES('KaBuM!',$1) RETURNING id''', 'https://example.com/stream-demo-'+secrets.token_hex(8))
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-B', '-m', 'data_mining.streaming', env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        results = []
        now = datetime.now(timezone.utc) - timedelta(seconds=2)
        for index, price in enumerate((100, 80)):
            identity = await conn.fetchval('''INSERT INTO hunter_price_observations(
                produto_id,nome,preco,coletado_em,fonte_coleta,fonte_url)
                VALUES($1,'DEMO SINTETICA STREAMING - SOMENTE BANCO ISOLADO',$2,$3,
                       'http_publico','https://example.com/stream-demo') RETURNING id''',
                pid, price, now + timedelta(seconds=index))
            result = None
            for _ in range(300):
                result = await conn.fetchrow('''SELECT * FROM hunter_analytics_results
                    WHERE observation_id=$1''', identity)
                if result:
                    break
                if process.returncode is not None:
                    raise RuntimeError('Consumidor encerrou antes do resultado')
                await asyncio.sleep(.1)
            if result is None:
                raise RuntimeError('Resultado nao chegou em 30 segundos')
            results.append(dict(result))
        assert results[-1]['change_percent'] == -20
        assert results[-1]['drop_detected'] is True
        assert results[-1]['window_size'] == 2
        assert all(not r['replay'] for r in results)
        async with connect(settings, purpose='analytics') as broker:
            await broker.publish(results[-1]['observation_id'])
            await asyncio.sleep(1)
        count = await conn.fetchval('''SELECT count(*) FROM hunter_analytics_results
            WHERE produto_id=$1''', pid)
        assert count == 2, 'Duplicata criou resultado adicional'
        print(json.dumps({'status':'aprovado','fixture_sintetica':True,
            'ambiente':'hunter_test isolado','fila':settings.prefix+'.analytics',
            'consumidor':'processo independente python -m data_mining.streaming',
            'produto_id':pid,'eventos_novos':2,'resultados_persistidos':count,
            'duplicata_sem_efeito':True,'resultados':results}, default=str, ensure_ascii=False))
    finally:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                process.kill()
                await process.wait()
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
