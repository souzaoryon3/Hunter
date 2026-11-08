"""Backup portavel cifrado e restore apenas em stack dev vazia; nunca escreve na origem."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
class TransferError(RuntimeError):
    """Diagnostico produzido pelo wrapper, sem saida das ferramentas."""


MAGIC = b"HUNTERDB1"
PRESERVE = ("produtos_backup", "produtos_kabum", "produtos_mercadolivre", "produtos_pichau",
            "hunter_catalog_products", "hunter_price_observations", "hunter_catalog_candidates",
            "hunter_schema_migrations")


def run(command, *, data=None, env=None):
    result = subprocess.run(command, input=data, capture_output=True, env=env, cwd=ROOT)
    if result.returncode:
        # Classifica erros sem expor SQL, nomes, DSNs ou stderr.
        print("Diagnostico seguro:", json.dumps({"tool": Path(command[0]).name,
              "operation": command[1] if len(command)>1 else "",
              "missing_object": b"does not exist" in result.stderr,
              "permission_denied": b"permission denied" in result.stderr.lower(),
              "restore_error": b"pg_restore:" in result.stderr,
              "connection_error": b"connection" in result.stderr.lower(),
              "sql_error": b"ERROR:" in result.stderr,
              "header_error": b"header" in result.stderr,
              "input_bytes": len(data) if data else 0}))
        raise TransferError("Ferramenta falhou: " + Path(command[0]).name + "; codigo=" + str(result.returncode))
    return result.stdout


def pg_tool(name):
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        path = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL/16/bin" / (name + ".exe")
        if path.is_file():
            return str(path)
    raise TransferError("Instale PostgreSQL client 16 no PATH para exportar; restore usa Docker.")


def dock(container, command, data=None):
    return run(["docker", "exec", "-i", container, *command], data=data)


def sql(container, statement):
    return dock(container, ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "hunter_dev",
                            "-d", "hunter_dev", "-At", "-c", statement]).decode().strip()


def table_hash(rows):
    # Multiconjunto canonico, independente da ordem fisica e do formatador JSON.
    values = [json.dumps(json.loads(row), ensure_ascii=True, sort_keys=True, separators=(",", ":")) for row in rows]
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def inventory(container):
    tables = sql(container, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
    result = {"counts": {}, "preserved_hashes": {}}
    for table in tables:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            raise TransferError("Tabela inesperada")
        result["counts"][table] = int(sql(container, f'SELECT count(*) FROM public."{table}"'))
        if table in PRESERVE:
            rows = sql(container, f'SELECT row_to_json(t)::text FROM public."{table}" t').splitlines()
            result["preserved_hashes"][table] = table_hash(rows)
    return result


async def source_snapshot():
    import asyncpg
    from ops import secret_store
    # Acesso somente leitura ao cofre existente; nao altera/rotaciona credenciais.
    dsn = secret_store.read("administrator.dpapi")["DATABASE_URL"]
    u = urlsplit(dsn)
    if u.hostname not in ("localhost", "127.0.0.1", "::1") or (u.port or 5432) != 5432 or u.path != "/hunter_db":
        raise TransferError("Origem principal nao confirmada")
    conn = await asyncpg.connect(dsn, server_settings={"default_transaction_read_only": "on", "timezone": "UTC"})
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            if await conn.fetchval("SELECT current_database()") != "hunter_db":
                raise TransferError("Origem invalida")
            snapshot = await conn.fetchval("SELECT pg_export_snapshot()")
            tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
            source = {"counts": {}, "preserved_hashes": {}}
            for record in tables:
                table = record["tablename"]
                if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
                    raise TransferError("Tabela inesperada")
                source["counts"][table] = await conn.fetchval(f'SELECT count(*) FROM public."{table}"')
                if table in PRESERVE:
                    rows = await conn.fetch(f'SELECT row_to_json(t)::text AS value FROM public."{table}" t')
                    source["preserved_hashes"][table] = table_hash([r["value"] for r in rows])
            env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
            env["PGPASSWORD"] = unquote(u.password or "")
            env["PGOPTIONS"] = "-c default_transaction_read_only=on"
            dump = run([pg_tool("pg_dump"), "-h", u.hostname, "-p", str(u.port or 5432),
                        "-U", unquote(u.username or ""), "-d", "hunter_db", "-Fc", "--schema=public",
                        "--no-owner", "--no-privileges", "--snapshot=" + snapshot], env=env)
            if not dump.startswith(b"PGDMP"):
                raise TransferError("Dump invalido")
            privacy = [r["value"] for r in await conn.fetch(
                "SELECT email AS value FROM usuarios UNION SELECT senha FROM usuarios UNION SELECT email FROM auditoria_usuarios UNION SELECT email FROM feedbacks")
                if r["value"] and len(r["value"]) >= 8]
            return dump, source, privacy
    finally:
        await conn.close()


# Atualiza apenas a COPIA, preservando IDs, FKs, contagens e todas as linhas.
SANITIZE = r"""
BEGIN;
ALTER TABLE usuarios DISABLE TRIGGER USER;
DO $$
DECLARE r record; t text; c text;
BEGIN
  FOR r IN SELECT nome,email FROM usuarios LOOP
    -- Remove identidades tambem dos campos livres vinculados a alertas/eventos.
    IF length(coalesce(r.email,'')) > 0 THEN
      UPDATE alertas_preco SET produto=replace(produto,r.email,'[identidade removida]');
      UPDATE hunter_events SET payload=replace(payload::text,r.email,'[identidade removida]')::jsonb;
      UPDATE hunter_notifications SET produto=replace(produto,r.email,'[identidade removida]');
    END IF;
    IF length(coalesce(r.nome,'')) >= 4 THEN
      UPDATE alertas_preco SET produto=replace(produto,r.nome,'[identidade removida]');
      UPDATE hunter_events SET payload=replace(payload::text,r.nome,'[identidade removida]')::jsonb;
      UPDATE hunter_notifications SET produto=replace(produto,r.nome,'[identidade removida]');
    END IF;
  END LOOP;
END $$;
UPDATE usuarios SET nome='Integrante transferido '||id,
    email='transfer-'||id||'@example.invalid', senha='!disabled-transfer-no-login!';
UPDATE auditoria_usuarios SET nome='Identidade removida',email='removed@example.invalid';
ALTER TABLE usuarios ENABLE TRIGGER USER;
UPDATE feedbacks SET nome='Identidade removida',email='removed@example.invalid',feedback='[conteudo pessoal removido na copia de transferencia]';
UPDATE hunter_events SET last_error=NULL,
  payload=(SELECT coalesce(jsonb_object_agg(key,value),'{}'::jsonb) FROM jsonb_each(payload)
           WHERE key IN ('produto','preco','preco_desejado','loja','link'));
UPDATE hunter_scheduler_heartbeat SET process_id=0,state='stopped';
COMMIT;
"""


def restore_dump(container, dump):
    # Banco vazio ja possui public: omite somente sua criacao no TOC.
    # Nao executa DROP nem ignora os demais erros de restauracao.
    listing = dock(container, ["pg_restore", "--list"], dump).decode()
    listing = "\n".join(line for line in listing.splitlines()
                        if not re.search(r"\bSCHEMA - public(?: |$)", line)) + "\n"
    listfile = "/tmp/hunter-restore-" + secrets.token_hex(8) + ".list"
    dock(container, ["sh", "-c", "cat > " + listfile], listing.encode())
    dock(container, ["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
                     "--no-privileges", "--use-list=" + listfile,
                     "-U", "hunter_dev", "-d", "hunter_dev"], dump)


def prepare():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    container = "hunter-transfer-stage-" + stamp.lower()
    password = secrets.token_hex(32)
    raw, source, private_values = asyncio.run(source_snapshot())
    # Sem portas publicadas, sem bind mounts, sem volumes do operador. Preservado ao fim.
    env = os.environ.copy()
    env["POSTGRES_PASSWORD"] = password
    run(["docker", "run", "-d", "--name", container, "-e", "POSTGRES_PASSWORD",
         "-e", "POSTGRES_USER=hunter_dev", "-e", "POSTGRES_DB=hunter_dev", "postgres:16-alpine"], env=env)
    import time
    for _ in range(60):
        ready = subprocess.run(["docker", "exec", container, "pg_isready", "-U", "hunter_dev", "-d", "hunter_dev"], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(.5)
    else:
        raise RuntimeError("Copia isolada nao iniciou")
    restore_dump(container, raw)
    del raw
    copied = inventory(container)
    if copied != source:
        raise TransferError("Restore de staging divergiu do snapshot de origem")
    sql(container, SANITIZE)
    after = inventory(container)
    # Catalogo, historico e candidatos devem ser identicos; contagens de tudo preservadas.
    if after != source:
        print("Divergencia sem valores:", json.dumps({group: [name for name in source[group] if source[group].get(name) != after[group].get(name)] for group in source}))
        raise TransferError("Sanitizacao mudou catalogo/candidatos/contagens; revisar antes de exportar")
    invalid = sql(container, "SELECT count(*) FROM usuarios WHERE email <> 'transfer-'||id||'@example.invalid' OR senha <> '!disabled-transfer-no-login!'")
    if invalid != "0":
        raise TransferError("Identidade nao sanitizada")
    dump = dock(container, ["pg_dump", "-Fc", "--schema=public", "--no-owner", "--no-privileges", "-U", "hunter_dev", "-d", "hunter_dev"])
    readable = dock(container, ["pg_restore", "--no-owner", "--no-privileges", "-f", "-"], dump)
    if any(value.encode() in readable for value in private_values):
        raise TransferError("Valor pessoal/credencial de origem permaneceu na copia; exportacao recusada")
    manifest = {"format": 1, "created_at": stamp, "postgres_major": 16, **after,
                "dump_sha256": hashlib.sha256(dump).hexdigest(), "privacy_value_check": "source_emails_and_password_hashes_absent",
                "privacy": ["Identidades substituidas mantendo IDs/FKs", "Senhas de usuarios invalidadas",
                            "Feedback e auditoria anonimizados somente na copia", "Payloads de eventos limitados a campos funcionais",
                            "Heartbeat marcado stopped", "Sem roles/senhas PostgreSQL, JWT, cofres ou filas RabbitMQ"],
                "staging_container": container}
    clear = io.BytesIO()
    with zipfile.ZipFile(clear, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("database.dump", dump)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    key, nonce = AESGCM.generate_key(bit_length=256), secrets.token_bytes(12)
    encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, clear.getvalue(), MAGIC)
    directory = ROOT / "local-data/transfers"
    directory.mkdir(parents=True, exist_ok=True)
    package = directory / ("hunter-database-" + stamp + ".enc")
    with package.open("xb") as f:
        f.write(encrypted)
    keys = ROOT / ".secrets"
    keys.mkdir(exist_ok=True)
    keyfile = keys / ("transfer-" + stamp + ".key")
    with keyfile.open("xb") as f:
        f.write(key)
    if os.name != "nt":
        keyfile.chmod(0o600)
    # Registro publico nao contem nomes, emails, payloads ou senhas.
    (directory / ("transfer-" + stamp + ".json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    run(["docker", "stop", container])
    print("Pacote cifrado preparado:", package.relative_to(ROOT))
    print("Chave SEPARADA (nao exibir nem enviar junto):", keyfile.relative_to(ROOT))
    print("Staging parado e preservado. Catalogo/candidatos/historico e contagens conferidos; origem somente leitura.")


def compose_config(instance):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", instance):
        raise TransferError("Use instancia dev nomeada, diferente da stack padrao")
    config = ROOT / (".env.dev." + instance + ".local")
    if not config.is_file():
        raise TransferError("Configure primeiro scripts/dev.py configure --instance NOME --http-port PORTA --management-port PORTA")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DEV_", "COMPOSE_"))}
    return ["docker", "compose", "-p", "hunter-dev-" + instance, "--env-file", str(config), "-f", str(ROOT / "compose.dev.yaml")], env


def restore(args):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    package = Path(args.package).read_bytes()
    key = Path(args.key_file).read_bytes()
    if not package.startswith(MAGIC) or len(key) != 32:
        raise TransferError("Formato/chave invalido")
    offset = len(MAGIC)
    clear = AESGCM(key).decrypt(package[offset:offset+12], package[offset+12:], MAGIC)
    with zipfile.ZipFile(io.BytesIO(clear)) as z:
        dump = z.read("database.dump")
        manifest = json.loads(z.read("manifest.json"))
    if hashlib.sha256(dump).hexdigest() != manifest["dump_sha256"]:
        raise TransferError("Hash do dump divergiu")
    command, env = compose_config(args.instance)
    run(command + ["up", "-d", "--wait", "postgres", "rabbitmq"], env=env)
    container = run(command + ["ps", "-q", "postgres"], env=env).decode().strip()
    # Nunca --clean/--create, DROP/TRUNCATE; um destino ja usado e recusado.
    if sql(container, "SELECT count(*) FROM pg_tables WHERE schemaname='public'") != "0":
        raise TransferError("Restore recusado: banco destino nao esta vazio; use outra instancia NOVA.")
    if sql(container, "SELECT current_database()") != "hunter_dev":
        raise TransferError("Destino inesperado")
    restore_dump(container, dump)
    if inventory(container) != {k: manifest[k] for k in ("counts", "preserved_hashes")}:
        raise TransferError("Restore divergiu do manifesto; nao iniciar aplicacao")
    # Servicos runtime nao foram iniciados: preserva estado para conferir antes de operar.
    print("Restore validado: todas as contagens e hashes de catalogo, imagens/URLs, precos, historicos, candidatos e migracoes iguais.")
    print("Usuarios preservados por ID, anonimizados e com login antigo desativado. Cadastre sua conta nova.")
    print("Proximo: python scripts/dev.py up --instance " + args.instance)


def activate_user(args):
    import getpass
    import bcrypt
    command, env = compose_config(args.instance)
    container = run(command + ["ps", "-q", "postgres"], env=env).decode().strip()
    if not container:
        raise TransferError("Inicie o PostgreSQL da instancia restaurada.")
    uid = args.user_id
    if uid <= 0:
        raise TransferError("ID invalido")
    # Somente contas anonimizadas da copia; nao permite destino do operador.
    eligible = sql(container, f"SELECT count(*) FROM usuarios WHERE id={uid} AND email='transfer-{uid}@example.invalid' AND senha='!disabled-transfer-no-login!'")
    if eligible != "1":
        raise TransferError("Conta nao e uma identidade transferida desativada")
    password = getpass.getpass("Nova senha local (nao sera exibida): ")
    if len(password) < 12 or password != getpass.getpass("Repita a senha: "):
        raise TransferError("Senha deve ter ao menos 12 caracteres e confirmacao igual")
    encoded = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    sql(container, f"UPDATE usuarios SET senha='{encoded}' WHERE id={uid} AND senha='!disabled-transfer-no-login!'")
    print(f"Conta local ativada: transfer-{uid}@example.invalid. Alertas/notificacoes vinculados ao ID preservados.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare-operator", help="Windows do operador; origem somente leitura via DPAPI existente")
    p = sub.add_parser("restore")
    p.add_argument("--package", required=True)
    p.add_argument("--key-file", required=True)
    p.add_argument("--instance", required=True)
    p = sub.add_parser("activate-user", help="Define senha propria para identidade anonimizada da copia")
    p.add_argument("--instance", required=True)
    p.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare-operator":
            prepare()
        elif args.action == "restore":
            restore(args)
        else:
            activate_user(args)
    except Exception as exc:
        print("Transferencia interrompida:", str(exc) if isinstance(exc, TransferError) else type(exc).__name__, "(valores privados omitidos).")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
