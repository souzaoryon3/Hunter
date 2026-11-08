"""Rotacao autorizada: prepare antes de apply; valores ficam apenas no cofre DPAPI."""

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg
import requests
from ops import secret_store
from ops.security import provision, scram, verify
from ops.broker_permissions import permissions
from scripts.catalog_stage2 import main_dsn, backup, fingerprint, inspect


def login_url(dsn, user, password):
    u = urlsplit(dsn)
    return urlunsplit(
        (
            u.scheme,
            f"{quote(user)}:{quote(password)}@{u.hostname}:{u.port or 5432}",
            u.path,
            u.query,
            "",
        )
    )


async def prepare():
    dsn = main_dsn()
    c = await asyncpg.connect(
        dsn, server_settings={"default_transaction_read_only": "on"}
    )
    try:
        await inspect(c)
        if await c.fetchval("SELECT current_user") != "postgres":
            raise ValueError("Revisar administrador antes de rotacionar.")
        original = await fingerprint(c)
    finally:
        await c.close()
    path = backup(dsn)
    state = {
        "old_admin": dsn,
        "backup": str(path),
        "fingerprint": original,
        "app_password": secrets.token_urlsafe(36),
        "migration_password": secrets.token_urlsafe(36),
        "admin_password": secrets.token_urlsafe(36),
        "jwt": secrets.token_urlsafe(48),
        "phase": "prepared",
    }
    secret_store.write("security-stage.dpapi", state)
    print("Backup verificado e plano de rotacao salvo cifrado; nenhuma role alterada.")


async def apply():
    state = secret_store.read("security-stage.dpapi")
    if state["phase"] != "prepared" or not state.get("acl_validated"):
        raise ValueError("Exige preparacao e ACL validada na copia isolada.")
    c = await asyncpg.connect(state["old_admin"])
    try:
        if await c.fetchval("SELECT current_database()") != "hunter_db":
            raise ValueError("Banco principal nao confirmado.")
        if not await c.fetchval("SELECT pg_try_advisory_lock(281235)"):
            raise ValueError("Coleta ativa; handoff adiado.")
        if await fingerprint(c) != state["fingerprint"]:
            raise ValueError("Catalogo mudou desde o backup; preparar novo ponto.")
        await provision(
            c,
            expected_database="hunter_db",
            app_password=state["app_password"],
            migration_password=state["migration_password"],
        )
        runtime = {
            "DATABASE_URL": login_url(
                state["old_admin"], "hunter_app", state["app_password"]
            ),
            "JWT_SECRET_KEY": state["jwt"],
        }
        app = await asyncpg.connect(runtime["DATABASE_URL"])
        try:
            await verify(app)
            if await fingerprint(app) != state["fingerprint"]:
                raise ValueError("Fingerprint divergiu.")
        finally:
            await app.close()
        state["phase"] = "roles_ready"
        secret_store.write("security-stage.dpapi", state, replace=True)
        # Cofre de administrador separado, nunca carregado pelo runtime.
        secret_store.write(
            "administrator.dpapi",
            {
                "DATABASE_URL": login_url(
                    state["old_admin"], "postgres", state["admin_password"]
                )
            },
        )
        secret_store.write("runtime.dpapi", runtime)
        secret_store.write("migration.dpapi", {"MIGRATION_DATABASE_URL": login_url(state["old_admin"], "hunter_migration", state["migration_password"])})
        await c.execute(
            "ALTER ROLE postgres PASSWORD '" + scram(state["admin_password"]) + "'"
        )
        state["phase"] = "rotated"
        secret_store.write("security-stage.dpapi", state, replace=True)
        print(
            "Roles dedicadas e rotacao PostgreSQL/JWT concluidas; handoff dos processos pendente."
        )
    finally:
        await c.close()


async def broker():
    state = secret_store.read("security-stage.dpapi")
    if state["phase"] != "rotated":
        raise ValueError("Rotacao PostgreSQL pendente.")
    runtime = secret_store.read("runtime.dpapi")
    if "RABBITMQ_URL" in runtime:
        raise ValueError("Broker ja rotacionado; nao repetir.")
    old_user = os.environ["HUNTER_RABBIT_USER"]
    old_password = os.environ["HUNTER_RABBIT_PASSWORD"]
    api = "http://127.0.0.1:15672/api"
    auth = (old_user, old_password)
    existing = requests.get(api + "/users", auth=auth, timeout=10)
    existing.raise_for_status()
    if any(u["name"] == "hunter_app" for u in existing.json()):
        raise ValueError("Login de broker ja existe.")
    app_password = secrets.token_urlsafe(36)
    admin_password = secrets.token_urlsafe(36)
    admin = secret_store.read("administrator.dpapi")
    admin.update(RABBIT_ADMIN_USER=old_user, RABBIT_ADMIN_PASSWORD=admin_password)
    # Persistir recuperacao antes de qualquer troca no broker.
    state.update(
        old_broker_user=old_user,
        old_broker_password=old_password,
        broker_admin_password=admin_password,
        broker_app_password=app_password,
    )
    secret_store.write("security-stage.dpapi", state, replace=True)
    for path, body in [
        ("/users/hunter_app", {"password": app_password, "tags": ""}),
        ("/permissions/hunter/hunter_app", permissions()),
    ]:
        r = requests.put(api + path, auth=auth, json=body, timeout=10)
        r.raise_for_status()
    runtime.update(
        RABBITMQ_URL=f"amqp://hunter_app:{app_password}@127.0.0.1:5672/hunter",
    )
    secret_store.write("administrator.dpapi", admin, replace=True)
    secret_store.write("runtime.dpapi", runtime, replace=True)
    r = requests.put(
        api + "/users/" + quote(old_user, safe=""),
        auth=auth,
        json={"password": admin_password, "tags": "administrator"},
        timeout=10,
    )
    r.raise_for_status()
    r = requests.get(api + "/overview", auth=(old_user, admin_password), timeout=10)
    r.raise_for_status()
    print(
        "Broker principal: senha administrativa rotacionada e usuario runtime sem tag administrativa; filas preservadas."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "apply", "broker"])
    try:
        asyncio.run(globals()[parser.parse_args().action]())
    except Exception as exc:
        print(
            "Operacao interrompida:",
            type(exc).__name__,
            "(detalhes omitidos para proteger segredos)",
        )
        raise SystemExit(1) from None
