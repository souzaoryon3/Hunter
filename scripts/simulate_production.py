"""Stack isolada com copia real, TLS e segredos efemeros protegidos em DPAPI.

Comandos explicitos; restore recusa qualquer banco com tabelas. Nunca usa main_dsn.
"""

import argparse
import asyncio
import ipaddress
import os
import secrets
import ssl
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg
import requests
from ops import secret_store
from ops.security import provision, verify
from ops.broker_permissions import permissions


def environment(state):
    env = os.environ.copy()
    for key in (
        "HUNTER_QUEUE_TESTS",
        "HUNTER_TEST_DATABASE_URL",
        "MIGRATION_DATABASE_URL",
    ):
        env.pop(key, None)
    env.update(
        HUNTER_ENV="production",
        HUNTER_COLLECTION_ENABLED="0",
        DATABASE_URL=f"postgresql://hunter_app:{state['app']}@postgres:5432/hunter_sim?sslmode=verify-full&sslrootcert=/run/tls/ca.crt",
        RABBITMQ_URL=f"amqps://hunter_sim:{state['broker']}@rabbitmq:5671/hunter_sim",
        JWT_SECRET_KEY=state["jwt"],
        CORS_ORIGINS="https://localhost:8443",
        SIM_POSTGRES_PASSWORD=state["admin"],
        SIM_RABBIT_ADMIN_PASSWORD=state["broker_admin"],
        HUNTER_SIM_TLS=str(ROOT / ".secrets/simulation-tls").replace("\\", "/"),
    )
    return env


def compose(state, *args):
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.simulation.yaml",
            "--profile",
            "app",
            *args,
        ],
        cwd=ROOT,
        env=environment(state),
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # Docker output pode interpolar segredos: armazenar diagnostico somente cifrado.
        secret_store.write(
            "simulation-last-error.dpapi",
            {"output": result.stdout + result.stderr},
            replace=(ROOT / ".secrets/simulation-last-error.dpapi").exists(),
        )
        raise RuntimeError("Docker falhou; diagnostico protegido no cofre.")
    print("Compose:", " ".join(args), "OK")
    return result.stdout


def certificates():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Hunter Local Simulation CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    root = ROOT / ".secrets/simulation-tls"
    for service, hosts in [
        ("client", []),
        ("postgres", ["postgres", "localhost"]),
        ("rabbitmq", ["rabbitmq", "localhost"]),
        ("frontend", ["localhost"]),
    ]:
        folder = root / service
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        if not hosts:
            continue
        server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])])
        cert = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        *(x509.DNSName(h) for h in hosts),
                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256())
        )
        (folder / "server.crt").write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )
        (folder / "server.key").write_bytes(
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    # Chave CA nao persistida. Somente chaves servidor locais, ignoradas/ACL Windows.


def prepare():
    if (ROOT / ".secrets/simulation.dpapi").exists():
        raise ValueError("Simulacao ja preparada; nao sobrescrever segredos/volumes.")
    certificates()
    state = {
        name: secrets.token_urlsafe(36)
        for name in ("admin", "app", "migration", "broker", "broker_admin", "jwt")
    }
    state["phase"] = "prepared"
    secret_store.write("simulation.dpapi", state)
    source = (ROOT / "ops/nginx.conf").read_text(encoding="utf-8")
    source = source.replace(
        "listen 8080;",
        "listen 8443 ssl;\n    ssl_certificate /run/tls/server.crt;\n    ssl_certificate_key /run/tls/server.key;\n    ssl_protocols TLSv1.2 TLSv1.3;",
    )
    (ROOT / "ops/nginx.simulation.conf").write_text(source, encoding="utf-8")
    print("Simulacao preparada; cofre cifrado e certificados privados ignorados.")


async def admin_connection(state):
    context = ssl.create_default_context(
        cafile=str(ROOT / ".secrets/simulation-tls/client/ca.crt")
    )
    return await asyncpg.connect(
        host="127.0.0.1",
        port=55433,
        database="hunter_sim",
        user="postgres",
        password=state["admin"],
        ssl=context,
    )


async def restore(state):
    c = await admin_connection(state)
    try:
        if await c.fetchval(
            "SELECT current_database()"
        ) != "hunter_sim" or await c.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public')"
        ):
            raise ValueError("Restore exige hunter_sim:55433 vazio.")
    finally:
        await c.close()
    backup = Path(secret_store.read("security-stage.dpapi")["backup"])
    env = os.environ.copy()
    env["PGPASSWORD"] = state["admin"]
    result = subprocess.run(
        [
            r"C:\Program Files\PostgreSQL\16\bin\pg_restore.exe",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "-h",
            "127.0.0.1",
            "-p",
            "55433",
            "-U",
            "postgres",
            "-d",
            "hunter_sim",
            str(backup),
        ],
        env=env,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Restauracao isolada falhou; nao repetir sobre dados existentes."
        )
    c = await admin_connection(state)
    try:
        await provision(
            c,
            expected_database="hunter_sim",
            app_password=state["app"],
            migration_password=state["migration"],
        )
    finally:
        await c.close()
    await validate(state)


async def validate(state):
    app = await asyncpg.connect(
        host="127.0.0.1",
        port=55433,
        database="hunter_sim",
        user="hunter_app",
        password=state["app"],
    )
    try:
        await verify(app)
        await validate_acl(app)
    finally:
        await app.close()
    api = "http://127.0.0.1:55673/api"
    auth = ("simulation_admin", state["broker_admin"])
    for method, path, body in [
        ("put", "/users/hunter_sim", {"password": state["broker"], "tags": ""}),
        ("put", "/permissions/hunter_sim/hunter_sim", permissions()),
    ]:
        r = getattr(requests, method)(api + path, auth=auth, json=body, timeout=10)
        r.raise_for_status()
    state["phase"] = "restored"
    secret_store.write("simulation.dpapi", state, replace=True)
    main = secret_store.read("security-stage.dpapi")
    main["acl_validated"] = True
    secret_store.write("security-stage.dpapi", main, replace=True)
    print(
        "Backup restaurado; roles e ACL validadas na copia; broker runtime sem tag administrativa."
    )


async def validate_acl(c):
    # Dados sinteticos somente na copia, rollback integral. DDL proibido comprovado.
    tx = c.transaction()
    await tx.start()
    try:
        marker = "acl-" + secrets.token_hex(8)
        user = await c.fetchval(
            "INSERT INTO usuarios(nome,email,senha) VALUES('ACL',$1,'not-a-password') RETURNING id",
            marker + "@example.invalid",
        )
        await c.execute("UPDATE usuarios SET nome='ACL verificado' WHERE id=$1", user)
        await c.fetchval(
            "INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES($1,'ACL',1) RETURNING id",
            user,
        )
        await c.execute(
            "INSERT INTO feedbacks(usuario_id,nome,email,feedback) VALUES($1,'ACL',$2,'ACL')",
            user,
            marker + "@example.invalid",
        )
        await c.fetch("SELECT * FROM hunter_price_observations LIMIT 1")
        from messaging.service import scan

        await scan(c)
        from catalog_expansion.heartbeat import SchedulerGuard

        guard = SchedulerGuard(c)
        if not await guard.start():
            raise ValueError("Lock inesperado na copia.")
        await guard.tick()
        await guard.stop()
        nested = c.transaction()
        await nested.start()
        try:
            await c.execute("CREATE TABLE public.hunter_acl_forbidden(id int)")
        except asyncpg.InsufficientPrivilegeError:
            await nested.rollback()
        else:
            raise ValueError("Runtime pode criar tabelas!")
    finally:
        await tx.rollback()
    print("ACL: CRUD/auditoria, scan, heartbeat permitidos; DDL/historico protegidos.")


async def run(action):
    if action == "prepare":
        prepare()
        return
    state = secret_store.read("simulation.dpapi")
    if action == "infra":
        compose(state, "up", "-d", "--wait", "postgres", "rabbitmq")
    elif action == "restore":
        await restore(state)
    elif action == "validate":
        await validate(state)
    elif action == "up":
        if state["phase"] != "restored":
            raise ValueError("Restaure/valide antes de iniciar aplicacao.")
        compose(
            state,
            "up",
            "-d",
            "--build",
            "--wait",
            "api",
            "worker",
            "scheduler",
            "frontend",
        )
    elif action == "status":
        # Somente campos operacionais, sem docker inspect de ambiente.
        print(
            compose(
                state,
                "ps",
                "--format",
                "table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Ports}}",
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["prepare", "infra", "restore", "validate", "up", "status"]
    )
    try:
        asyncio.run(run(parser.parse_args().action))
    except Exception as exc:
        print("Simulacao interrompida:", type(exc).__name__, "(sem valores sensiveis)")
        raise SystemExit(1) from None
