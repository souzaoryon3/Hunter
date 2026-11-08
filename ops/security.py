"""Provisionamento explicito de roles; sem exclusao de dados ou migracao de schema."""

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scram(password):
    """Verifier SCRAM evita senha em texto em comandos SQL/log de DDL."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 4096)
    client = hmac.digest(salted, b"Client Key", "sha256")
    stored = hashlib.sha256(client).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")
    enc = lambda b: base64.b64encode(b).decode()
    return f"SCRAM-SHA-256$4096:{enc(salt)}${enc(stored)}:{enc(server)}"


async def provision(conn, *, expected_database, app_password, migration_password):
    actual = await conn.fetchval("SELECT current_database()")
    if (
        expected_database not in {"hunter_db", "hunter_sim", "hunter_test"}
        or actual != expected_database
    ):
        raise ValueError("Destino de provisionamento nao confirmado.")
    # Roles exclusivas; nao modificar silenciosamente uma conta preexistente.
    if await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('hunter_app','hunter_migration'))"
    ):
        raise ValueError("Logins dedicados ja existem; revisar antes de repetir.")
    template = (ROOT / "ops/postgres_roles.sql").read_text(encoding="utf-8")
    template = template.replace(
        "current_database() <> 'hunter_db'",
        f"current_database() <> '{expected_database}'",
    )
    template = template.replace(
        "ON DATABASE hunter_db", f'ON DATABASE "{expected_database}"'
    )
    # A transacao externa tambem inclui ownership e senhas; retire somente delimitadores.
    template = template.replace("BEGIN;\nDO", "DO", 1).replace("\nCOMMIT;", "")
    async with conn.transaction():
        await conn.execute(template)
        for name, password in (
            ("hunter_app", app_password),
            ("hunter_migration", migration_password),
        ):
            verifier = scram(password)
            await conn.execute(
                f"CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{verifier}'"
            )
        await conn.execute(
            "GRANT hunter_runtime TO hunter_app; GRANT hunter_owner TO hunter_migration"
        )
        await conn.execute("ALTER ROLE hunter_migration SET role TO 'hunter_owner'")
        # A transferencia e limitada aos objetos deste banco/schema, nunca REASSIGN OWNED.
        for row in await conn.fetch(
            "SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m') ORDER BY c.relkind='S',c.relname"
        ):
            name = '"' + row["relname"].replace('"', '""') + '"'
            kind = {"S": "SEQUENCE", "v": "VIEW", "m": "MATERIALIZED VIEW"}.get(
                row["relkind"], "TABLE"
            )
            await conn.execute(f"ALTER {kind} public.{name} OWNER TO hunter_owner")
        await conn.execute(
            "REVOKE CREATE ON SCHEMA public FROM PUBLIC, hunter_runtime, hunter_app"
        )
        # Nao conceder automaticamente DML em novas tabelas: cada migracao exige revisao.
        await conn.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE hunter_owner IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC"
        )


async def verify(conn):
    role = dict(
        await conn.fetchrow(
            "SELECT current_user AS name,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
    )
    if role["name"] != "hunter_app" or any(role[k] for k in role if k != "name"):
        raise ValueError("Runtime possui identidade/atributos indevidos.")
    if await conn.fetchval(
        "SELECT has_schema_privilege(current_user,'public','CREATE')"
    ):
        raise ValueError("Runtime pode criar objetos.")
    for table in ("hunter_price_observations", "hunter_processing_log"):
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            if await conn.fetchval(
                "SELECT has_table_privilege(current_user,$1,$2)", table, privilege
            ):
                raise ValueError("Runtime pode alterar/apagar historico.")
    if await conn.fetchval(
        "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user"
    ):
        raise ValueError("Runtime e owner de tabela.")
    return role
