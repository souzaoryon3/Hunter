"""Inicializacao exclusiva do banco Docker de desenvolvimento; sem dados pessoais."""
import asyncio
import os
from urllib.parse import urlsplit

import asyncpg
from ops.bootstrap import ensure_base
from messaging.migrate import migrate


async def main():
    dsn = os.environ["MIGRATION_DATABASE_URL"]
    target = urlsplit(dsn)
    if (os.environ.get("HUNTER_ENV") != "local" or target.hostname != "postgres"
            or target.port != 5432 or target.path != "/hunter_dev"
            or target.username != "hunter_dev" or target.query):
        raise ValueError("Bootstrap dev recusou destino diferente de hunter_dev interno.")
    conn = await asyncpg.connect(dsn)
    try:
        if await conn.fetchval("SELECT current_database()") != "hunter_dev":
            raise ValueError("Banco dev invalido")
        # Serializa inicializacoes; migracoes mantem seus proprios locks/checksums.
        await conn.execute("SELECT pg_advisory_lock(281237)")
        empty = not await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public')")
        if empty:
            await ensure_base(conn)
        for version in ("002", "003", "004", "005"):
            await migrate(version)
        # Oferta ficticia para testar busca/alertas; nunca se passa por preco real.
        # O dashboard demo usa seu dataset em memoria, separado desta oferta.
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(281238)")
            link = "https://example.invalid/hunter-demo-keyboard"
            if empty and not await conn.fetchval("SELECT EXISTS(SELECT 1 FROM produtos_kabum WHERE link=$1)", link):
                await conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES($1,99.90,$2)",
                                   "DEMO FICTICIO - Teclado Hunter", link)
    finally:
        await conn.close()
    print("Banco dev inicializado, migracoes conferidas e oferta ficticia disponivel.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("Inicializacao dev falhou:", type(exc).__name__, "(valores omitidos).")
        raise SystemExit(1) from None
