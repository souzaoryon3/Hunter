"""Consumidor da Azure Queue Storage: exporta o catalogo analisado para o Blob.

Fluxo: python -m cloud.enqueue exportar_catalogo -> fila hunter-exportacoes ->
este worker -> exportacoes/catalogo/AAAA/MM/DD/<id>.json.gz no Blob Storage.
A mensagem so e apagada apos o upload; falhas voltam a fila pelo visibility
timeout e, apos AZURE_QUEUE_MAX_DEQUEUE tentativas, seguem para a fila -poison.
"""
import asyncio
import gzip
import json
import logging
import time
from datetime import datetime, timezone

import asyncpg

from cloud import messages, storage, telemetry
from cloud.config import storage_settings
from config.settings import database_url

log = logging.getLogger("hunter.azure.export")

EXPORT_SQL = """SELECT DISTINCT ON (o.produto_id)
        o.produto_id, p.loja, o.nome, o.preco, o.preco_cartao, o.disponivel,
        o.coletado_em, o.imagem_url, p.link, t.category AS categoria,
        a.change_percent AS variacao_percentual, a.drop_detected AS queda_detectada
    FROM hunter_price_observations o
    JOIN hunter_catalog_products p ON p.id = o.produto_id
    LEFT JOIN hunter_text_results t ON t.observation_id = o.id
    LEFT JOIN hunter_analytics_results a ON a.observation_id = o.id
    WHERE p.channel = 'retail'
    ORDER BY o.produto_id, o.coletado_em DESC, o.id DESC"""


def build_export(rows, message, now=None):
    now = now or datetime.now(timezone.utc)
    document = {
        "solicitacao": message["id"],
        "solicitado_em": message["solicitado_em"],
        "gerado_em": now.isoformat(),
        "total": len(rows),
        "produtos": [dict(row) for row in rows],
    }
    raw = json.dumps(document, ensure_ascii=False, default=str).encode("utf-8")
    name = f"catalogo/{now:%Y/%m/%d}/{now:%Y%m%dT%H%M%SZ}-{message['id']}.json.gz"
    return name, gzip.compress(raw, mtime=0)


async def fetch_catalog(dsn):
    conn = await asyncpg.connect(dsn)
    try:
        if not await conn.fetchval("SELECT to_regclass('hunter_text_results') IS NOT NULL"):
            raise RuntimeError("Exportacao exige migracao 009.")
        return await conn.fetch(EXPORT_SQL)
    finally:
        await conn.close()


class Metrics:
    def __init__(self):
        self.processed = self.poisoned = self.duration = None
        if telemetry.enabled():
            meter = telemetry.meter()
            self.processed = meter.create_counter("hunter_exportacoes_concluidas")
            self.poisoned = meter.create_counter("hunter_exportacoes_poison")
            self.duration = meter.create_histogram("hunter_exportacao_duracao_ms", unit="ms")


async def handle(item, queue, poison, settings, export, metrics):
    """Processa uma mensagem; retorna 'ok', 'poison' ou 'retry'."""
    if item.dequeue_count > settings.max_dequeue:
        await asyncio.to_thread(poison.send_message, item.content)
        await asyncio.to_thread(queue.delete_message, item)
        log.warning("Mensagem movida para poison apos tentativas",
                    extra={"tentativas": item.dequeue_count})
        if metrics.poisoned:
            metrics.poisoned.add(1, {"motivo": "tentativas"})
        return "poison"
    try:
        message = messages.parse(item.content)
    except messages.InvalidMessage as exc:
        await asyncio.to_thread(poison.send_message, item.content)
        await asyncio.to_thread(queue.delete_message, item)
        log.warning("Mensagem invalida movida para poison", extra={"motivo": str(exc)})
        if metrics.poisoned:
            metrics.poisoned.add(1, {"motivo": "invalida"})
        return "poison"
    started = time.perf_counter()
    try:
        result = await export(message)
    except Exception as exc:
        # Sem delete: a mensagem reaparece apos o visibility timeout.
        log.error("Falha na exportacao; nova tentativa pela fila",
                  extra={"solicitacao": message["id"], "erro": type(exc).__name__})
        return "retry"
    await asyncio.to_thread(queue.delete_message, item)
    elapsed = (time.perf_counter() - started) * 1000
    log.info("Exportacao concluida", extra={"solicitacao": message["id"], **result,
                                             "duracao_ms": round(elapsed)})
    if metrics.processed:
        metrics.processed.add(1)
        metrics.duration.record(elapsed)
    return "ok"


async def run(poll_seconds=5):
    settings = storage_settings()
    if settings is None:
        log.warning("AZURE_STORAGE_CONNECTION_STRING ausente; worker Azure desativado.")
        return
    await asyncio.to_thread(storage.ensure_resources, settings)
    queue = storage.queue_client(settings, settings.exports_queue)
    poison = storage.queue_client(settings, settings.poison_queue)
    dsn = database_url()
    metrics = Metrics()

    async def export(message):
        rows = await fetch_catalog(dsn)
        name, data = build_export(rows, message)
        info = await asyncio.to_thread(
            storage.upload_bytes, settings, settings.exports_container, data, name,
            {"solicitacao": message["id"], "produtos": str(len(rows))},
            "application/json", "gzip")
        return {"blob": info["blob"], "bytes": info["bytes"], "produtos": len(rows)}

    log.info("Worker Azure conectado; aguardando mensagens.",
             extra={"fila": settings.exports_queue})
    while True:
        items = await asyncio.to_thread(lambda: list(queue.receive_messages(
            messages_per_page=8, visibility_timeout=settings.visibility_seconds,
            max_messages=8)))
        for item in items:
            await handle(item, queue, poison, settings, export, metrics)
        if not items:
            await asyncio.sleep(poll_seconds)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    telemetry.quiet_sdk_logs()
    telemetry.configure("hunter-azure-export")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        telemetry.flush()


if __name__ == "__main__":
    main()
