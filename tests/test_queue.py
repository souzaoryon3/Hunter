import asyncio
import json
import os
import secrets
import unittest
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

from messaging.config import Settings
from messaging.service import dispatch, fingerprint, handle_message, process, scan
from messaging.testing import require_isolated


class QueueUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_fingerprint(self):
        self.assertEqual(fingerprint('Mouse', 100), fingerprint('Mouse', 100.0))
        self.assertNotEqual(fingerprint('Mouse', 100), fingerprint('Mouse', 99))

    def test_isolation_guard(self):
        with self.assertRaises(ValueError):
            require_isolated(Settings('postgresql://localhost/hunter_db', 'amqp://localhost/hunter'))

    async def test_db_outage_does_not_ack(self):
        pool, message = Mock(), AsyncMock()
        message.body = json.dumps({'version': 1, 'event_id': str(uuid.uuid4())}).encode()
        pool.acquire.side_effect = ConnectionError()
        with self.assertRaises(ConnectionError):
            await handle_message(message, pool, AsyncMock(), Settings('', ''))
        message.ack.assert_not_awaited()


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS') == '1', 'Ambiente isolado não configurado')
class QueueIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        from messaging.broker import connect
        self.settings = replace(Settings.environment(), prefix='hunter_test_' + secrets.token_hex(6), retry_seconds=1)
        require_isolated(self.settings)
        self.conn = await asyncpg.connect(self.settings.database_url)
        self.tx = self.conn.transaction()
        await self.tx.start()
        self.addAsyncCleanup(self.cleanup)
        self.marker = 'QueueTest' + secrets.token_hex(8)
        self.user = await self.conn.fetchval('''INSERT INTO usuarios(nome,email,senha) VALUES ('Teste',$1,'not-a-real-password') RETURNING id''', self.marker + '@example.com')
        self.alert = await self.conn.fetchval('''INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES ($1,$2,100) RETURNING id''', self.user, self.marker)
        self.product = await self.conn.fetchval('''INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,100,'https://example.com/offer') RETURNING id''', self.marker)
        self.broker_context = connect(self.settings)
        self.broker = await self.broker_context.__aenter__()
        class Pool:
            @asynccontextmanager
            async def acquire(inner):
                yield self.conn
        self.pool = Pool()

    async def cleanup(self):
        if hasattr(self, 'broker'):
            # Preserva as filas criadas nesta execução; não remove nem purga recursos.
            await self.broker_context.__aexit__(None, None, None)
        await self.tx.rollback()
        await self.conn.close()

    async def create_event(self):
        await scan(self.conn)
        return await self.conn.fetchval('SELECT id FROM hunter_events WHERE alerta_id=$1 ORDER BY generation DESC LIMIT 1', self.alert)

    async def delivery(self, fault=None):
        message = await self.broker.work.get(timeout=5)
        await handle_message(message, self.pool, self.broker, self.settings, fault)

    async def test_detection_equality_recross_and_edit(self):
        event = await self.create_event()
        self.assertIsNotNone(event)
        await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1', self.alert), 1)
        await self.conn.execute('UPDATE produtos_kabum SET preco=110 WHERE id=$1', self.product)
        await scan(self.conn)
        await self.conn.execute('UPDATE produtos_kabum SET preco=90 WHERE id=$1', self.product)
        await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1', self.alert), 2)
        await self.conn.execute('UPDATE alertas_preco SET preco=95 WHERE id=$1', self.alert)
        await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1', self.alert), 3)
        self.assertEqual(await process(self.conn, event, self.settings), 'cancelled')

    async def test_no_event_above_target_or_without_offer(self):
        await self.conn.execute('UPDATE produtos_kabum SET preco=101 WHERE id=$1', self.product)
        self.assertIsNone(await self.create_event())
        await self.conn.execute('UPDATE alertas_preco SET produto=$2 WHERE id=$1', self.alert, self.marker + ' ausente')
        self.assertIsNone(await self.create_event())

    async def test_publication_consumption_duplicate_and_logs(self):
        event = await self.create_event()
        self.assertEqual(await dispatch(self.conn, self.broker, self.settings), 1)
        await self.delivery()
        await self.broker.publish(event)
        await self.delivery()
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE event_id=$1', event), 1)
        row = await self.conn.fetchrow('SELECT status,attempts,processed_at FROM hunter_events WHERE id=$1', event)
        self.assertEqual((row['status'], row['attempts']), ('processed', 1))
        self.assertIsNotNone(row['processed_at'])
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_processing_log WHERE event_id=$1', event), 3)
        self.assertEqual(await self.conn.fetchval("SELECT count(*) FROM hunter_processing_log WHERE event_id=$1 AND status='duplicate'", event), 1)
        self.assertFalse(await self.conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_processing_log WHERE event_id=$1 AND finished_at < started_at)', event))

    async def test_publish_failure_preserves_outbox_and_recovers(self):
        event = await self.create_event()
        failed = AsyncMock()
        failed.publish.side_effect = ConnectionError('secret must never be persisted')
        self.assertEqual(await dispatch(self.conn, failed, self.settings), 0)
        row = await self.conn.fetchrow('SELECT status,last_error FROM hunter_events WHERE id=$1', event)
        self.assertEqual((row['status'], row['last_error']), ('pending', 'ConnectionError'))
        await self.conn.execute('UPDATE hunter_events SET next_attempt_at=now() WHERE id=$1', event)
        await dispatch(self.conn, self.broker, self.settings)
        await self.delivery()
        self.assertEqual(await self.conn.fetchval('SELECT status FROM hunter_events WHERE id=$1', event), 'processed')

    async def test_stale_publication_recovers_after_lost_ack(self):
        event = await self.create_event()
        await dispatch(self.conn, self.broker, self.settings)
        await self.conn.execute("UPDATE hunter_events SET updated_at=now()-interval '1 hour' WHERE id=$1", event)
        await dispatch(self.conn, self.broker, self.settings)
        await self.delivery()
        await self.delivery()
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE event_id=$1', event), 1)

    async def test_retry_limit_dlq_and_no_partial_notification(self):
        event = await self.create_event()
        def fail(_):
            raise RuntimeError('simulated failure without real data')
        for attempt in range(1, 4):
            await self.conn.execute('UPDATE hunter_events SET next_attempt_at=now() WHERE id=$1', event)
            await dispatch(self.conn, self.broker, self.settings)
            await self.delivery(fail)
            self.assertEqual(await self.conn.fetchval('SELECT attempts FROM hunter_events WHERE id=$1', event), attempt)
            self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE event_id=$1', event), 0)
        self.assertEqual(await self.conn.fetchval('SELECT status FROM hunter_events WHERE id=$1', event), 'dead_pending')
        await self.conn.execute('UPDATE hunter_events SET next_attempt_at=now() WHERE id=$1', event)
        await dispatch(self.conn, self.broker, self.settings)
        dead = await self.broker.dead.get(timeout=5)
        self.assertEqual(json.loads(dead.body)['event_id'], str(event))
        await dead.ack()
        self.assertEqual(await self.conn.fetchval('SELECT status FROM hunter_events WHERE id=$1', event), 'dead')
        self.assertEqual(await self.conn.fetchval('SELECT last_error FROM hunter_events WHERE id=$1', event), 'RuntimeError')

    async def test_transient_failure_then_success(self):
        event = await self.create_event()
        def fail(_):
            raise ValueError()
        self.assertEqual(await process(self.conn, event, self.settings, fail), 'retry')
        await self.conn.execute('UPDATE hunter_events SET next_attempt_at=now() WHERE id=$1', event)
        await dispatch(self.conn, self.broker, self.settings)
        await self.delivery()
        self.assertEqual(await self.conn.fetchval('SELECT attempts FROM hunter_events WHERE id=$1', event), 2)

    async def test_deleted_alert_cancels_event(self):
        event = await self.create_event()
        await self.conn.execute('DELETE FROM alertas_preco WHERE id=$1', self.alert)
        self.assertEqual(await process(self.conn, event, self.settings), 'cancelled')

    async def test_invalid_message_is_logged_and_quarantined(self):
        from aio_pika import Message
        await self.broker.channel.default_exchange.publish(Message(b'not-json'), routing_key=self.broker.work.name)
        await self.delivery()
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_message_rejections'), 1)
        dead = await self.broker.dead.get(timeout=5)
        self.assertIn('rejected_body_hash', json.loads(dead.body))
        await dead.ack()

    async def test_notifications_auth_ownership_and_read(self):
        from test_api import http
        import app as backend
        from auth import create_access_token
        async def test_db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db] = test_db
        try:
            event = await self.create_event()
            await process(self.conn, event, self.settings)
            token = create_access_token({'sub': str(self.user)})
            status, _ = await http('GET', '/notificacoes')
            self.assertEqual(status, 401)
            status, data = await http('GET', '/notificacoes', token=token)
            self.assertEqual((status, data['total'], data['nao_lidas']), (200, 1, 1))
            notification = data['notificacoes'][0]['id']
            other = await self.conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES ('Outro',$1,'hash') RETURNING id", self.marker+'other@example.com')
            other_token = create_access_token({'sub': str(other)})
            _, data = await http('GET', '/notificacoes', token=other_token)
            self.assertEqual(data['total'], 0)
            status, _ = await http('PUT', f'/notificacoes/{notification}/lida', token=other_token)
            self.assertEqual(status, 404)
            for _ in range(2):
                status, _ = await http('PUT', f'/notificacoes/{notification}/lida', token=token)
                self.assertEqual(status, 200)
            _, data = await http('GET', '/notificacoes', token=token)
            self.assertEqual(data['nao_lidas'], 0)
        finally:
            backend.app.dependency_overrides.clear()
