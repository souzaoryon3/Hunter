"""Troca dos processos locais sob lock de coleta; nao inicia coleta diretamente."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncpg
from ops.secret_store import read


async def main():
    values = read("runtime.dpapi")
    c = await asyncpg.connect(values["DATABASE_URL"])
    try:
        if await c.fetchval("SELECT current_database()") != "hunter_db":
            raise ValueError("Destino divergente.")
        if not await c.fetchval("SELECT pg_try_advisory_lock(281235)"):
            raise ValueError("Coleta em andamento; nao interromper.")
        env = os.environ.copy()
        env.update(values)
        env["HUNTER_SECURITY_HANDOFF"] = "1"
        p = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(ROOT / "ops/handoff_security.ps1"),
            env=env,
        )
        if await p.wait():
            raise RuntimeError("Handoff nao concluido; conferir inventario.")
    finally:
        await c.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("Handoff interrompido:", type(exc).__name__, "(sem detalhes sensiveis)")
        raise SystemExit(1) from None
