"""Publica um pedido na Azure Queue Storage: python -m cloud.enqueue exportar_catalogo."""
import argparse
import logging

from cloud import messages, storage, telemetry
from cloud.config import storage_settings

log = logging.getLogger("hunter.azure.enqueue")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tipo", choices=sorted(messages.KINDS))
    parser.add_argument("--origem", default="cli")
    args = parser.parse_args()
    settings = storage_settings()
    if settings is None:
        parser.error("Configure AZURE_STORAGE_CONNECTION_STRING.")
    logging.basicConfig(level=logging.WARNING)
    telemetry.quiet_sdk_logs()
    telemetry.configure("hunter-azure-enqueue")
    try:
        storage.ensure_resources(settings)
        message_id = storage.enqueue(settings, args.tipo, args.origem)
        log.info("Pedido publicado na fila", extra={"solicitacao": message_id, "tipo": args.tipo})
        print(f"Pedido {message_id} publicado em {settings.exports_queue}.")
    finally:
        telemetry.flush()


if __name__ == "__main__":
    main()
