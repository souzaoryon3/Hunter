"""Integracao Azure sem rede: configuracao, contrato da fila, exportacao e poison."""
import asyncio
import gzip
import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from cloud import messages, telemetry
from cloud.config import storage_settings
from cloud.export_worker import Metrics, build_export, handle

CONN = ("DefaultEndpointsProtocol=https;AccountName=conta;AccountKey=Y2hhdmU=;"
        "EndpointSuffix=core.windows.net")


class SettingsTests(unittest.TestCase):
    def test_disabled_without_connection_string(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(storage_settings())
            self.assertFalse(telemetry.enabled())

    def test_defaults_and_poison_queue(self):
        with mock.patch.dict(os.environ, {"AZURE_STORAGE_CONNECTION_STRING": CONN}, clear=True):
            settings = storage_settings()
        self.assertEqual(settings.exports_queue, "hunter-exportacoes")
        self.assertEqual(settings.poison_queue, "hunter-exportacoes-poison")
        self.assertEqual((settings.backups_container, settings.exports_container),
                         ("backups", "exportacoes"))

    def test_rejects_invalid_names_http_and_incomplete_string(self):
        cases = [
            {"AZURE_STORAGE_CONNECTION_STRING": CONN, "AZURE_BLOB_BACKUPS": "Backups"},
            {"AZURE_STORAGE_CONNECTION_STRING": CONN, "AZURE_QUEUE_EXPORTS": "a--b"},
            {"AZURE_STORAGE_CONNECTION_STRING": CONN.replace("https", "http")},
            {"AZURE_STORAGE_CONNECTION_STRING": "AccountName=conta"},
            {"AZURE_STORAGE_CONNECTION_STRING": CONN, "AZURE_QUEUE_MAX_DEQUEUE": "0"},
        ]
        for env in cases:
            with self.subTest(env=sorted(env)), mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError) as error:
                    storage_settings()
                self.assertNotIn("Y2hhdmU", str(error.exception))


class MessageTests(unittest.TestCase):
    def test_roundtrip(self):
        message = messages.build("exportar_catalogo", "teste")
        self.assertEqual(messages.parse(messages.encode(message)), message)

    def test_rejects_unknown_malformed_and_large(self):
        valid = messages.build("exportar_catalogo")
        for text in ("nao json", json.dumps({**valid, "tipo": "apagar_tudo"}),
                     json.dumps({**valid, "id": "x"}), json.dumps({**valid, "origem": ""}),
                     json.dumps({**valid, "origem": "x" * 3000}), json.dumps([valid])):
            with self.subTest(text=text[:30]), self.assertRaises(messages.InvalidMessage):
                messages.parse(text)
        with self.assertRaises(messages.InvalidMessage):
            messages.build("apagar_tudo")


class ExportTests(unittest.TestCase):
    def test_export_is_gzip_json_with_decimals_and_dates(self):
        message = messages.build("exportar_catalogo")
        now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
        rows = [{"produto_id": 1, "preco": Decimal("99.90"), "coletado_em": now, "nome": "Mouse"}]
        name, data = build_export(rows, message, now)
        self.assertTrue(name.startswith("catalogo/2026/11/16/20261116T120000Z-"))
        document = json.loads(gzip.decompress(data))
        self.assertEqual(document["total"], 1)
        self.assertEqual(document["produtos"][0]["preco"], "99.90")
        self.assertEqual(document["solicitacao"], message["id"])


class FakeQueue:
    def __init__(self):
        self.sent, self.deleted = [], []

    def send_message(self, content):
        self.sent.append(content)

    def delete_message(self, item):
        self.deleted.append(item)


class HandleTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(max_dequeue=3)
        self.queue, self.poison = FakeQueue(), FakeQueue()
        self.metrics = Metrics.__new__(Metrics)
        self.metrics.processed = self.metrics.poisoned = self.metrics.duration = None

    def run_handle(self, item, export):
        return asyncio.run(handle(item, self.queue, self.poison, self.settings, export, self.metrics))

    def test_success_deletes_after_export(self):
        content = messages.encode(messages.build("exportar_catalogo"))
        item = SimpleNamespace(content=content, dequeue_count=1)

        async def export(message):
            self.assertEqual(self.queue.deleted, [])
            return {"blob": "b", "bytes": 1, "produtos": 1}
        self.assertEqual(self.run_handle(item, export), "ok")
        self.assertEqual(self.queue.deleted, [item])
        self.assertEqual(self.poison.sent, [])

    def test_failure_keeps_message_for_retry(self):
        item = SimpleNamespace(content=messages.encode(messages.build("exportar_catalogo")),
                               dequeue_count=1)

        async def export(message):
            raise ConnectionError("indisponivel")
        self.assertEqual(self.run_handle(item, export), "retry")
        self.assertEqual((self.queue.deleted, self.poison.sent), ([], []))

    def test_invalid_and_exhausted_messages_go_to_poison(self):
        async def export(message):
            self.fail("nao deveria exportar")
        invalid = SimpleNamespace(content="{}", dequeue_count=1)
        exhausted = SimpleNamespace(content=messages.encode(messages.build("exportar_catalogo")),
                                    dequeue_count=4)
        self.assertEqual(self.run_handle(invalid, export), "poison")
        self.assertEqual(self.run_handle(exhausted, export), "poison")
        self.assertEqual(self.queue.deleted, [invalid, exhausted])
        self.assertEqual(self.poison.sent, [invalid.content, exhausted.content])


class DevScriptTests(unittest.TestCase):
    def test_compose_profile_keeps_stack_working_without_azure(self):
        from pathlib import Path
        compose = (Path(__file__).resolve().parents[1] / "compose.dev.yaml").read_text(encoding="utf-8")
        self.assertIn("profiles: [azure]", compose)
        self.assertIn("${AZURE_APPINSIGHTS_CONNECTION_STRING:-}", compose)


if __name__ == "__main__":
    unittest.main()
