"""Verificacao principal somente leitura apos rotacao autorizada."""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import asyncpg
import requests
from jose import jwt
from ops.secret_store import read
from ops.security import verify
from scripts.catalog_stage2 import fingerprint, inspect


async def main():
    state = read("security-stage.dpapi")
    runtime = read("runtime.dpapi")
    admin = read("administrator.dpapi")
    c = await asyncpg.connect(
        runtime["DATABASE_URL"], server_settings={"default_transaction_read_only": "on"}
    )
    try:
        assert await c.fetchval("SELECT current_database()") == "hunter_db"
        await verify(c)
        await inspect(c)
        assert await fingerprint(c) == state["fingerprint"]
        print(
            "Fingerprint preservado; candidatos=",
            await c.fetchval("SELECT count(*) FROM hunter_catalog_candidates"),
        )
        print(
            "Heartbeat:",
            dict(
                await c.fetchrow(
                    "SELECT state,process_id,clock_timestamp()-last_seen_at AS age FROM hunter_scheduler_heartbeat"
                )
            ),
        )
        print(
            "Sessoes:",
            [
                dict(r)
                for r in await c.fetch(
                    "SELECT usename,count(*) n FROM pg_stat_activity WHERE datname=current_database() GROUP BY usename"
                )
            ],
        )
        user = await c.fetchval("SELECT id FROM usuarios ORDER BY id LIMIT 1")
    finally:
        await c.close()
    # psql evita o erro de conexao fechada do asyncpg/Windows em auth negativa.
    psql = r"C:\Program Files\PostgreSQL\16\bin\psql.exe"
    for label, dsn, expected in [
        ("antiga", state["old_admin"], False),
        ("nova", admin["DATABASE_URL"], True),
    ]:
        u = urlsplit(dsn)
        env = os.environ.copy()
        env["PGPASSWORD"] = unquote(u.password or "")
        env["PGCONNECT_TIMEOUT"] = "5"
        r = subprocess.run(
            [
                psql,
                "-X",
                "-w",
                "-h",
                u.hostname,
                "-p",
                str(u.port or 5432),
                "-U",
                unquote(u.username or ""),
                "-d",
                "hunter_db",
                "-tAc",
                "SELECT 1",
            ],
            env=env,
            capture_output=True,
        )
        assert (r.returncode == 0) == expected, "Validacao PostgreSQL " + label
        if not expected:
            assert (
                b"password authentication failed" in r.stderr.lower()
                or b"falhou" in r.stderr.lower()
            )
        print(
            "Credencial PostgreSQL "
            + label
            + ": "
            + ("aceita" if expected else "recusada")
        )
    payload = {
        "sub": str(user),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, runtime["JWT_SECRET_KEY"], algorithm="HS256")
    headers = {"Authorization": "Bearer " + token}
    for path in (
        "/health/ready",
        "/lojas",
        "/analytics/estatisticas",
        "/analytics/agrupamentos",
        "/buscar-produtos?nome=mouse",
        "/usuario",
        "/alertas",
        "/notificacoes",
    ):
        assert (
            requests.get(
                "http://127.0.0.1:8000" + path, headers=headers, timeout=20
            ).status_code
            == 200
        ), path
    old_values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.queue.local").read_text().splitlines()
        if "=" in line
    )
    oldtoken = jwt.encode(
        payload, old_values["HUNTER_MAIN_JWT_SECRET"], algorithm="HS256"
    )
    assert (
        requests.get(
            "http://127.0.0.1:8000/usuario",
            headers={"Authorization": "Bearer " + oldtoken},
            timeout=10,
        ).status_code
        == 401
    )
    print("Endpoints publicos/autenticados200; JWT antigo401.")
    api = "http://127.0.0.1:15672/api"
    assert (
        requests.get(
            api + "/overview",
            auth=(state["old_broker_user"], state["old_broker_password"]),
            timeout=10,
        ).status_code
        == 401
    )
    auth = (admin["RABBIT_ADMIN_USER"], admin["RABBIT_ADMIN_PASSWORD"])
    r = requests.get(api + "/queues/hunter", auth=auth, timeout=10)
    r.raise_for_status()
    print(
        "Filas:",
        [
            {
                k: q[k]
                for k in ("name", "consumers", "messages", "messages_unacknowledged")
            }
            for q in r.json()
        ],
    )
    r = requests.get(api + "/users/hunter_app", auth=auth, timeout=10)
    r.raise_for_status()
    assert not r.json()["tags"]
    print(
        "RabbitMQ: senha administrativa antiga recusada; runtime sem tag administrativa."
    )


if __name__ == "__main__":
    asyncio.run(main())
