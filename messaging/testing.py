"""Bootstrap exclusivamente do ambiente Docker de teste. Nunca usar no banco real."""
import os
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
from config.settings import require_test_database


def require_isolated(settings):
    require_test_database(settings.database_url)
    for name in ('HUNTER_TEST_DATABASE_URL','DATABASE_URL','MIGRATION_DATABASE_URL'):
        if os.environ.get(name):
            require_test_database(os.environ[name])
    db, rabbit = urlsplit(settings.database_url), urlsplit(settings.rabbitmq_url)
    if (os.environ.get('HUNTER_QUEUE_TESTS') != '1'
            or db.hostname not in ('127.0.0.1', 'localhost') or db.port != 55432
            or db.path != '/hunter_test' or db.username != 'hunter_test'
            or rabbit.hostname not in ('127.0.0.1', 'localhost') or rabbit.port != 5673
            or rabbit.path != '/hunter_test' or rabbit.query or rabbit.fragment
            or not settings.prefix.startswith('hunter_test')):
        raise ValueError('Testes/demonstração exigem banco hunter_test:55432 e broker hunter_test:5673 isolados.')


async def bootstrap(settings):
    require_isolated(settings)
    conn = await asyncpg.connect(settings.database_url)
    try:
        if await conn.fetchval('SELECT current_database()') != 'hunter_test':
            raise ValueError('Banco de teste inválido.')
        from ops.bootstrap import ensure_base
        await ensure_base(conn,isolated=True)
    finally:
        await conn.close()
    # Usa o mesmo executor de migração da implantação.
    from messaging.migrate import migrate
    await migrate()
    await migrate('003')
    await migrate('004')
    await migrate('005')


if __name__ == '__main__':
    import asyncio
    from messaging.config import Settings
    asyncio.run(bootstrap(Settings.environment()))
