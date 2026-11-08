"""python -m messaging.scheduler [--once]: verifica catálogo e despacha outbox."""
import argparse
import asyncio
import logging
import time

import asyncpg
from messaging.broker import connect
from messaging.config import Settings
from messaging.service import dispatch, scan
from messaging.runtime import configure_logging
from scraping.periodic import CollectionSettings, run_collection
from catalog_expansion.heartbeat import SchedulerGuard
from config.settings import assert_runtime_role

log = logging.getLogger('hunter.scheduler')


async def run(once=False):
    settings = Settings.environment()
    owner=await asyncpg.connect(settings.database_url)
    guard=SchedulerGuard(owner)
    try:
        await assert_runtime_role(owner)
        if not await guard.start():
            log.warning('Scheduler ja ativo neste banco; instancia adicional encerrada.')
            return
        await owned_run(settings,guard,once)
    finally:
        try:
            await guard.stop()
        finally:
            await owner.close()


async def owned_run(settings,guard,once=False):
    try:
        collection = CollectionSettings.environment()
        if collection.enabled:
            collection.targets()  # Configuracao invalida nao deve impedir alertas.
    except Exception as exc:
        log.error('Coleta desativada por configuracao: %s',type(exc).__name__)
        collection = CollectionSettings()
    task = None
    next_check = 0
    while True:
        # Falha da conexao guard encerra a instancia em vez de operar sem lock.
        await guard.tick()
        if task is not None and task.done():
            try:
                task.result()
            except Exception as exc:
                log.error('Coleta nao concluida: %s',type(exc).__name__)
            task = None
        if collection.enabled and task is None and time.monotonic()>=next_check:
            task = asyncio.create_task(run_collection(settings.database_url, collection))
            next_check = time.monotonic()+60
        if once and task is not None:
            try:
                await task
            except Exception as exc:
                log.error('Coleta nao concluida: %s',type(exc).__name__)
        try:
            conn = await asyncpg.connect(settings.database_url)
            try:
                created = await scan(conn)
                # A detecção já fez commit, independentemente da disponibilidade do broker.
                async with connect(settings) as broker:
                    sent = await dispatch(conn, broker, settings)
                log.info('Eventos criados=%s publicados=%s', created, sent)
            finally:
                await conn.close()
        except Exception as exc:
            log.error('Ciclo não concluído: %s; eventos persistidos serão retomados.', type(exc).__name__)
            if once:
                raise SystemExit(1) from None
        if once:
            return
        await asyncio.sleep(settings.interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    configure_logging()
    try:
        asyncio.run(run(parser.parse_args().once))
    except KeyboardInterrupt:
        pass
