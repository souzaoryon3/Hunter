"""Operacoes Azure Blob/Queue Storage. SDK importado sob demanda."""
import hashlib
from pathlib import Path

from cloud import messages


def blob_service(settings):
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(settings.connection_string)


def queue_client(settings, name):
    from azure.storage.queue import QueueClient, TextBase64DecodePolicy, TextBase64EncodePolicy
    # Base64 mantem compatibilidade com o portal e com Azure Functions.
    return QueueClient.from_connection_string(
        settings.connection_string, name,
        message_encode_policy=TextBase64EncodePolicy(),
        message_decode_policy=TextBase64DecodePolicy())


def ensure_resources(settings):
    """Cria containers e filas ausentes; nunca apaga ou sobrescreve."""
    from azure.core.exceptions import ResourceExistsError
    service = blob_service(settings)
    for name in (settings.backups_container, settings.exports_container):
        try:
            service.create_container(name)
        except ResourceExistsError:
            pass
    for name in (settings.exports_queue, settings.poison_queue):
        try:
            queue_client(settings, name).create_queue()
        except ResourceExistsError:
            pass


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_file(settings, container, path, blob_name, metadata, content_type):
    from azure.storage.blob import ContentSettings
    checksum = sha256_file(path)
    client = blob_service(settings).get_blob_client(container, blob_name)
    with Path(path).open("rb") as stream:
        # overwrite=False: um backup existente nunca e substituido.
        client.upload_blob(stream, overwrite=False, metadata={**metadata, "sha256": checksum},
                           content_settings=ContentSettings(content_type=content_type))
    return {"blob": blob_name, "bytes": Path(path).stat().st_size, "sha256": checksum}


def upload_bytes(settings, container, data, blob_name, metadata, content_type, encoding=None):
    from azure.storage.blob import ContentSettings
    checksum = hashlib.sha256(data).hexdigest()
    client = blob_service(settings).get_blob_client(container, blob_name)
    client.upload_blob(data, overwrite=False, metadata={**metadata, "sha256": checksum},
                       content_settings=ContentSettings(content_type=content_type,
                                                        content_encoding=encoding))
    return {"blob": blob_name, "bytes": len(data), "sha256": checksum}


def list_blobs(settings, container, prefix=""):
    items = blob_service(settings).get_container_client(container).list_blobs(
        name_starts_with=prefix, include=["metadata"])
    return sorted(items, key=lambda item: item.last_modified)


def download_verified(settings, container, blob_name, destination):
    """Baixa e confere o SHA-256 gravado nos metadados no upload."""
    client = blob_service(settings).get_blob_client(container, blob_name)
    expected = (client.get_blob_properties().metadata or {}).get("sha256")
    with Path(destination).open("wb") as stream:
        client.download_blob().readinto(stream)
    actual = sha256_file(destination)
    if not expected or actual != expected:
        raise ValueError("SHA-256 do blob baixado nao confere com os metadados.")
    return actual


def enqueue(settings, kind, requested_by="cli"):
    message = messages.build(kind, requested_by)
    queue_client(settings, settings.exports_queue).send_message(messages.encode(message))
    return message["id"]
