"""Configuracao opcional do Azure; sem variaveis, o Hunter funciona como antes.

Erros nunca incluem a connection string nem chaves.
"""
import os
import re
from dataclasses import dataclass

# Regras comuns a containers Blob e filas: 3-63, minusculas, numeros e hifen simples.
NAME = re.compile(r"[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){2,62}")


@dataclass(frozen=True)
class StorageSettings:
    connection_string: str
    backups_container: str
    exports_container: str
    exports_queue: str
    poison_queue: str
    max_dequeue: int
    visibility_seconds: int


def resource_name(variable, default):
    value = os.environ.get(variable, default).strip()
    if not NAME.fullmatch(value):
        raise ValueError(f"Nome invalido em {variable}: use 3-63 minusculas, numeros e hifen.")
    return value


def bounded(variable, default, minimum, maximum):
    try:
        value = int(os.environ.get(variable, default))
    except (TypeError, ValueError):
        value = minimum - 1
    if not minimum <= value <= maximum:
        raise ValueError(f"Configuracao invalida: {variable}.")
    return value


def storage_settings():
    """Retorna None quando o Azure Storage nao esta configurado."""
    connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not connection:
        return None
    parts = dict(item.split("=", 1) for item in connection.split(";") if "=" in item)
    if not parts.get("AccountName") or not parts.get("AccountKey"):
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING incompleta (AccountName/AccountKey).")
    if parts.get("DefaultEndpointsProtocol", "https") != "https":
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING deve usar HTTPS.")
    queue = resource_name("AZURE_QUEUE_EXPORTS", "hunter-exportacoes")
    poison = queue + "-poison"
    if len(poison) > 63:
        raise ValueError("Nome de fila longo demais para a fila poison.")
    return StorageSettings(
        connection_string=connection,
        backups_container=resource_name("AZURE_BLOB_BACKUPS", "backups"),
        exports_container=resource_name("AZURE_BLOB_EXPORTS", "exportacoes"),
        exports_queue=queue,
        poison_queue=poison,
        max_dequeue=bounded("AZURE_QUEUE_MAX_DEQUEUE", 5, 1, 20),
        visibility_seconds=bounded("AZURE_QUEUE_VISIBILITY_SECONDS", 120, 30, 3600),
    )
