"""Calculos, contrato e fluxo real isolado; nunca usa o banco da aplicacao."""
import asyncio
import json
import os
import secrets
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import asyncpg

from data_mining.streaming import (
    event_id, rolling_metrics, process_event, publish_pending, handle_message, publishing, consuming,
)
from messaging.broker import connect
from messaging.config import Settings
from messaging.testing import require_isolated


class StreamingMetricsTests(unittest.TestCase):
    def test_first_event_does_not_invent_change_or_anomaly(self):
        result = rolling_metrics([100])
        self.assertEqual(result['mean_price'], 100)
        self.assertIsNone(result['change_percent'])
        self.assertIsNone(result['anomaly'])
        self.assertFalse(result['drop_detected'])

    def test_drop_and_mean(self):
        result = rolling_metrics([100, 120, 90])
        self.assertEqual(result['window_size'], 3)
        self.assertEqual(result['change_percent'], -25)
        self.assertTrue(result['drop_detected'])
        self.assertEqual(result['mean_price'], Decimal(310) / 3)

    def test_anomaly_uses_previous_values_only(self):
        self.assertTrue(rolling_metrics([99, 100, 101, 99, 101, 150])['anomaly'])
        self.assertIsNone(rolling_metrics([100] * 5 + [150])['anomaly'])
        self.assertIsNone(rolling_metrics([99, 100, 101, 150])['anomaly'])

    def test_rejects_invalid_windows(self):
        for prices in ([], [1] * 21, [0], [-1], ['NaN'], ['Infinity']):
            with self.subTest(prices=prices), self.assertRaises(ValueError):
                rolling_metrics(prices)

    def test_contract(self):
        self.assertEqual(event_id(b'{"version":1,"event_id":"42"}'), 42)
        for payload in (b'[]', b'null', b'bad', b'x'*4097,
                        b'{"version":true,"event_id":1}', b'{"version":2,"event_id":1}',
                        b'{"version":1,"event_id":true}', b'{"version":1,"event_id":1.5}',
                        b'{"version":1,"event_id":0}', b'{"version":1,"event_id":"01"}',
                        b'{"version":1,"event_id":9223372036854775808}'):
            with self.subTest(payload=payload[:60]), self.assertRaises(ValueError):
                event_id(payload)


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS') == '1', 'Exige banco e broker isolados')
class StreamingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = Settings.environment()
        require_isolated(self.settings)
        self.conn = await asyncpg.connect(self.settings.database_url)
        self.addAsyncCleanup(self.conn.close)
        self.tx = self.conn.transaction()
        await self.tx.start()
        self.addAsyncCleanup(self.rollback)
        self.pid = await self.conn.fetchval('''INSERT INTO hunter_catalog_products(loja,link)
            VALUES('KaBuM!',$1) RETURNING id''', 'https://example.com/stream-fixture-'+secrets.token_hex(8))
        self.now = datetime.now(timezone.utc) - timedelta(minutes=1)

    async def rollback(self):
        await self.tx.rollback()

    async def commit_fixture(self):
        await self.tx.commit()
        self.tx = self.conn.transaction()
        await self.tx.start()

    async def observation(self, price, minute, source='http_publico'):
        return await self.conn.fetchval('''INSERT INTO hunter_price_observations(
            produto_id,nome,preco,coletado_em,fonte_coleta,fonte_url)
            VALUES($1,'FIXTURE STREAMING ISOLADA',$2,$3,$4,'https://example.com/stream-fixture')
            RETURNING id''', self.pid, price, self.now + timedelta(minutes=minute), source)

    async def test_trigger_atomic_rollback_and_excludes_demo(self):
        async with self.conn.transaction():
            identity = await self.observation(100, 0)
            self.assertFalse(await self.conn.fetchval(
                'SELECT replay FROM hunter_analytics_events WHERE observation_id=$1', identity))
        demo = await self.observation(90, -1, 'sintetico_demo')
        self.assertFalse(await self.conn.fetchval(
            'SELECT EXISTS(SELECT 1 FROM hunter_analytics_events WHERE observation_id=$1)', demo))
        nested = self.conn.transaction()
        await nested.start()
        aborted = await self.observation(80, -2)
        await nested.rollback()
        self.assertFalse(await self.conn.fetchval(
            'SELECT EXISTS(SELECT 1 FROM hunter_analytics_events WHERE observation_id=$1)', aborted))

    async def test_scrapling_sources_reach_streaming_and_original_analytics(self):
        from data_mining.repository import observations
        for minute, source in enumerate(('scrapling_browser_card','scrapling_public_card')):
            identity = await self.observation(100, minute-2, source)
            self.assertTrue(await self.conn.fetchval('''SELECT EXISTS(SELECT 1
                FROM hunter_analytics_events WHERE observation_id=$1)''', identity))
            self.assertEqual(await process_event(self.conn, identity), 'processed')
        self.assertEqual(len(await observations(self.conn, product_id=self.pid)), 2)

    async def test_late_events_bounded_window_and_duplicate(self):
        identities = [await self.observation(100+i, i-25) for i in range(25)]
        self.assertEqual(await process_event(self.conn, identities[-1]), 'processed')
        self.assertEqual(await process_event(self.conn, identities[0]), 'processed')
        self.assertEqual(await process_event(self.conn, identities[-1]), 'duplicate')
        rows = await self.conn.fetch('''SELECT * FROM hunter_analytics_results
            WHERE produto_id=$1 ORDER BY event_time''', self.pid)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['window_size'], 1)
        self.assertEqual(rows[1]['window_size'], 20)
        self.assertEqual(rows[1]['min_price'], 105)
        self.assertEqual(rows[1]['mean_price'], Decimal('114.5'))
        self.assertEqual(rows[1]['price'], 124)

    async def test_future_event_rolls_back_result(self):
        identity = await self.observation(100, 10)
        with self.assertRaises(ValueError):
            await process_event(self.conn, identity)
        self.assertEqual(await self.conn.fetchval(
            'SELECT status FROM hunter_analytics_events WHERE observation_id=$1', identity), 'pending')

    async def test_api_reads_persisted_results_without_recomputing(self):
        import app as backend
        from test_api import http
        identity = await self.observation(100, 0)
        await process_event(self.conn, identity)
        async def db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db] = db
        try:
            code, data = await http('GET', f'/analytics/streaming?produto_id={self.pid}&limite=1')
            self.assertEqual(code, 200)
            self.assertEqual(data['resultados'][0]['observation_id'], identity)
            self.assertFalse(data['resultados'][0]['replay'])
            self.assertEqual(data['resultados'][0]['price'], 100)
            self.assertEqual((await http('GET', '/analytics/streaming?limite=101'))[0], 422)
        finally:
            backend.app.dependency_overrides.clear()

    async def test_real_rabbitmq_ack_and_duplicate_after_commit(self):
        # Esta fixture e commitada exclusivamente no banco isolado e preservada.
        identity = await self.observation(100, 0)
        await self.commit_fixture()
        settings = replace(self.settings, prefix='hunter_test_stream_'+secrets.token_hex(6))
        async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=2) as pool:
            async with connect(settings, purpose='analytics') as broker:
                self.assertGreaterEqual(await publish_pending(pool, broker, settings), 1)
                while await publish_pending(pool, broker, settings):
                    pass
                async def receive(target):
                    # Outras fixtures pendentes podem estar na outbox compartilhada.
                    for _ in range(1000):
                        message = await broker.work.get(timeout=10, fail=False)
                        self.assertIsNotNone(message)
                        current = event_id(message.body)
                        await handle_message(message, pool, broker, settings)
                        if current == target:
                            return
                    self.fail('Evento nao recebido')
                await receive(identity)
                self.assertEqual(await self.conn.fetchval('''SELECT count(*)
                    FROM hunter_analytics_results WHERE observation_id=$1''', identity), 1)
                await broker.publish(identity)
                await receive(identity)
                self.assertEqual(await self.conn.fetchval('''SELECT count(*)
                    FROM hunter_analytics_results WHERE observation_id=$1''', identity), 1)
                malformed = AsyncMock(body=b'not-json')
                await handle_message(malformed, pool, broker, settings)
                malformed.ack.assert_awaited_once()
                dead = await broker.dead.get(timeout=10)
                self.assertIn('rejected_body_hash', json.loads(dead.body))
                await dead.ack()

    async def test_publish_failure_preserves_outbox(self):
        identity = await self.observation(100, 0)
        await self.commit_fixture()
        broker = AsyncMock()
        broker.publish.side_effect = ConnectionError('simulacao sem dados sensiveis')
        async with asyncpg.create_pool(self.settings.database_url, min_size=1, max_size=2) as pool:
            with self.assertRaises(ConnectionError):
                await publish_pending(pool, broker, self.settings)
        self.assertEqual(await self.conn.fetchval('''SELECT status FROM hunter_analytics_events
            WHERE observation_id=$1''', identity), 'pending')
        self.assertEqual(await self.conn.fetchval('''SELECT publications FROM hunter_analytics_events
            WHERE observation_id=$1''', identity), 0)

    async def test_data_error_retry_and_confirmed_dead_letter(self):
        identity = await self.observation(100, 10)
        await self.commit_fixture()
        settings = replace(self.settings, max_attempts=2, retry_seconds=0)
        broker = AsyncMock()
        body = json.dumps({'version':1,'event_id':str(identity)}).encode()
        async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=2) as pool:
            for attempt in (1, 2):
                message = AsyncMock(body=body)
                await handle_message(message, pool, broker, settings)
                message.ack.assert_awaited_once()
                self.assertEqual(await self.conn.fetchval('''SELECT failures
                    FROM hunter_analytics_events WHERE observation_id=$1''', identity), attempt)
            self.assertEqual(await self.conn.fetchval('''SELECT status
                FROM hunter_analytics_events WHERE observation_id=$1''', identity), 'dead_pending')
            await publish_pending(pool, broker, settings)
            broker.publish.assert_any_await(identity, dead=True)
            self.assertEqual(await self.conn.fetchval('''SELECT status
                FROM hunter_analytics_events WHERE observation_id=$1''', identity), 'dead')
            self.assertFalse(await self.conn.fetchval('''SELECT EXISTS(SELECT 1
                FROM hunter_analytics_results WHERE observation_id=$1)''', identity))

    async def test_continuous_pipeline_receives_new_observations(self):
        settings = replace(self.settings, prefix='hunter_test_live_'+secrets.token_hex(6))
        async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=3) as pool:
            async with connect(settings, purpose='analytics') as broker:
                tasks = [asyncio.create_task(publishing(pool, broker, settings)),
                         asyncio.create_task(consuming(pool, broker, settings))]
                try:
                    for price, minute in ((100, -1), (80, 0)):
                        identity = await self.observation(price, minute)
                        await self.commit_fixture()
                        result = None
                        for _ in range(150):
                            result = await self.conn.fetchrow('''SELECT * FROM hunter_analytics_results
                                WHERE observation_id=$1''', identity)
                            if result:
                                break
                            await asyncio.sleep(.1)
                        self.assertIsNotNone(result, 'Consumidor continuo nao persistiu o evento')
                        self.assertFalse(result['replay'])
                    self.assertEqual(result['window_size'], 2)
                    self.assertEqual(result['change_percent'], -20)
                    self.assertTrue(result['drop_detected'])
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
