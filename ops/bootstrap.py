"""Bootstrap de banco VAZIO, separado do runtime e das migracoes ja aplicadas."""

import asyncio
import os
from pathlib import Path

import asyncpg
from config.settings import database_url

ROOT = Path(__file__).resolve().parents[1]


async def ensure_base(conn, *, isolated=False):
    if isolated:
        from config.settings import require_test_database

        require_test_database(database_url())
        if await conn.fetchval("SELECT current_database()") != "hunter_test":
            raise ValueError("Bootstrap isolado recusou destino real.")
    if not isolated and await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public')"
    ):
        raise ValueError("Bootstrap recusa banco com tabelas existentes.")
    async with conn.transaction():
        await conn.execute((ROOT / "ops/base_schema.sql").read_text(encoding="utf-8"))
        await conn.execute(
            (ROOT / "migrations/001_produtos_pichau.sql").read_text(encoding="utf-8")
        )


async def main():
    if os.environ.get("HUNTER_ALLOW_EMPTY_BOOTSTRAP") != "1":
        raise ValueError(
            "Bootstrap exige HUNTER_ALLOW_EMPTY_BOOTSTRAP=1 e banco vazio."
        )
    conn = await asyncpg.connect(database_url(migration=True))
    try:
        await ensure_base(conn)
    finally:
        await conn.close()
    from messaging.migrate import migrate

    for version in ("002", "003", "004", "005", "006"):
        await migrate(version)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(
            "Bootstrap recusado/falhou:",
            type(exc).__name__,
            "; confira destino e permissoes, sem repetir cegamente.",
        )
        raise SystemExit(1) from None
