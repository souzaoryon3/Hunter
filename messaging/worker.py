"""Worker independente. ACK somente após commit ou recuperação durável da falha."""
import argparse
import asyncio
import logging

import asyncpg
from messaging.broker import connect
from messaging.config import Settings
from messaging.service import handle_message
from messaging.runtime import configure_logging
from config.settings import assert_runtime_role

log = logging.getLogger('hunter.worker')


async def run(demo_failures=False):
    settings = Settings.environment()
    fault = None
    if demo_failures:
        from messaging.testing import require_isolated
        from messaging.demo import simulated_failure
        require_isolated(settings)
        fault = simulated_failure
    while True:
        try:
            async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=5) as pool:
                async with pool.acquire() as conn:
                    await assert_runtime_role(conn)
                async with connect(settings) as broker:
                    log.info('Worker conectado; aguardando mensagens.')
                    async with broker.work.iterator() as messages:
                        async for message in messages:
                            try:
                                await handle_message(message, pool, broker, settings, fault)
                            except Exception as exc:
                                log.error('Entrega sem ACK: %s', type(exc).__name__)
                                await asyncio.sleep(2)
                                if not message.processed:
                                    await message.nack(requeue=True)
        except Exception as exc:
            log.error('Conexão interrompida: %s; reconectando.', type(exc).__name__)
            await asyncio.sleep(5)


if __name__ == '__main__':
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo-failures', action='store_true', help='Falha simulada SOMENTE no ambiente isolado de teste')
    try:
        asyncio.run(run(parser.parse_args().demo_failures))
    except KeyboardInterrupt:
        pass
