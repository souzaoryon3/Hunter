"""Backup do PostgreSQL dev para o Azure Blob Storage, com verificacao de restauracao.

Uso (no host, com .venv e .env.azure.local):
  python scripts/azure_backup.py backup --instance scrapling
  python scripts/azure_backup.py verify --instance scrapling   # baixa o ultimo e testa pg_restore
  python scripts/azure_backup.py list

Nunca apaga backups: a retencao fica com a politica de ciclo de vida do Storage.
"""
import argparse
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud import storage, telemetry  # noqa: E402
from cloud.config import storage_settings  # noqa: E402

log = logging.getLogger("hunter.azure.backup")
DATABASE = "hunter_dev"


def load_env(path=ROOT / ".env.azure.local"):
    """Carrega o arquivo ignorado sem sobrescrever variaveis ja definidas."""
    if not path.is_file():
        return
    from dotenv import dotenv_values
    for key, value in dotenv_values(path).items():
        if value is not None:
            os.environ.setdefault(key, value)


def container_name(instance):
    if instance and not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", instance):
        raise ValueError("Instancia invalida.")
    return f"hunter-dev{'-' + instance if instance else ''}-postgres-1"


def docker(*args, capture=False):
    result = subprocess.run(["docker", *args], check=True, text=True,
                            capture_output=capture)
    return result.stdout if capture else None


def count_tables(container, remote_path):
    listing = docker("exec", container, "pg_restore", "-l", remote_path, capture=True)
    return sum(1 for line in listing.splitlines() if " TABLE DATA " in line)


def backup(settings, instance):
    container = container_name(instance)
    if docker("exec", container, "psql", "-U", DATABASE, "-d", DATABASE, "-Atc",
              "SELECT current_database()", capture=True).strip() != DATABASE:
        raise ValueError("Banco de destino inesperado.")
    now = datetime.now(timezone.utc)
    remote = f"/tmp/hunter-backup-{now:%Y%m%dT%H%M%SZ}.dump"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "backup.dump"
        try:
            docker("exec", container, "pg_dump", "-U", DATABASE, "-d", DATABASE, "-Fc", "-f", remote)
            tables = count_tables(container, remote)
            if tables == 0:
                raise ValueError("Dump sem dados de tabelas; upload cancelado.")
            docker("cp", f"{container}:{remote}", str(local))
        finally:
            docker("exec", container, "rm", "-f", remote)
        name = f"{DATABASE}/{now:%Y/%m/%d}/{DATABASE}-{now:%Y%m%dT%H%M%SZ}.dump"
        info = storage.upload_file(settings, settings.backups_container, local, name,
                                   {"banco": DATABASE, "tabelas": str(tables),
                                    "formato": "pg_dump-custom", "instancia": instance or "padrao"},
                                   "application/octet-stream")
    log.info("Backup enviado ao Blob", extra={**info, "tabelas": tables})
    print(f"Backup {info['blob']}: {info['bytes']} bytes, {tables} tabelas, sha256 {info['sha256'][:16]}...")
    return info


def verify(settings, instance):
    container = container_name(instance)
    blobs = storage.list_blobs(settings, settings.backups_container, f"{DATABASE}/")
    if not blobs:
        raise ValueError("Nenhum backup encontrado no container.")
    latest = blobs[-1]
    remote = "/tmp/hunter-verify.dump"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "verify.dump"
        storage.download_verified(settings, settings.backups_container, latest.name, local)
        docker("cp", str(local), f"{container}:{remote}")
        try:
            tables = count_tables(container, remote)
        finally:
            docker("exec", container, "rm", "-f", remote)
    expected = int((latest.metadata or {}).get("tabelas", "0"))
    if tables != expected:
        raise ValueError(f"Restauracao listou {tables} tabelas; esperado {expected}.")
    log.info("Backup verificado", extra={"blob": latest.name, "tabelas": tables})
    print(f"Verificado {latest.name}: SHA-256 confere e pg_restore listou {tables} tabelas.")


def list_backups(settings):
    for blob in storage.list_blobs(settings, settings.backups_container, f"{DATABASE}/"):
        tier = getattr(blob, "blob_tier", None) or "-"
        print(f"{blob.last_modified:%Y-%m-%d %H:%M} {blob.size:>10} {tier:>5} {blob.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("backup", "verify", "list"))
    parser.add_argument("--instance", default="scrapling")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    telemetry.quiet_sdk_logs()
    load_env()
    settings = storage_settings()
    if settings is None:
        parser.error("Configure AZURE_STORAGE_CONNECTION_STRING em .env.azure.local.")
    telemetry.configure("hunter-azure-backup")
    try:
        storage.ensure_resources(settings)
        if args.action == "backup":
            backup(settings, args.instance)
        elif args.action == "verify":
            verify(settings, args.instance)
        else:
            list_backups(settings)
    except Exception as exc:
        log.error("Operacao de backup falhou", extra={"acao": args.action, "erro": type(exc).__name__})
        print(f"Falha: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from None
    finally:
        telemetry.flush()


if __name__ == "__main__":
    main()
