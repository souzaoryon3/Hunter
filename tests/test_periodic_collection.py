"""Coleta periodica: HTTP simulado, PostgreSQL isolado e rollback."""
import asyncio
import json
import os
import secrets
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from contextlib import asynccontextmanager

import asyncpg

from scraping.periodic import CollectionSettings,Journal,collect_due,target_key
from messaging.config import Settings
from messaging.service import scan
from messaging.testing import require_isolated
from data_mining.repository import observations
from data_mining.analysis import statistics,cluster_products


class CollectionConfigTests(unittest.TestCase):
    def test_safe_defaults_and_rate_limits(self):
        with patch.dict(os.environ,{'HUNTER_COLLECTION_ENABLED':'0'},clear=True):
            self.assertFalse(CollectionSettings.environment().enabled)
        for setting in ({'HUNTER_COLLECTION_INTERVAL_SECONDS':'1'},{'HUNTER_COLLECTION_LIMIT':'100'},
                        {'HUNTER_COLLECTION_DELAY_SECONDS':'0'}):
            with patch.dict(os.environ,setting,clear=True),self.assertRaises(ValueError):
                CollectionSettings.environment()

    def test_target_validation_and_product_identity(self):
        self.assertEqual(target_key('KaBuM!','https://www.kabum.com.br/produto/123/a'),
                         target_key('KaBuM!','https://www.kabum.com.br/produto/123/b'))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'targets.json'
            path.write_text(json.dumps({'targets':[{'store':'KaBuM!','url':'https://evil.example/produto/1/a','enabled':True}]}))
            with self.assertRaises(ValueError):
                CollectionSettings(targets_path=path).targets()
            good='https://www.kabum.com.br/produto/123/a'
            path.write_text(json.dumps({'targets':[{'store':'KaBuM!','url':good,'enabled':True},
                                                   {'store':'KaBuM!','url':good,'enabled':True}]}))
            self.assertEqual(len(CollectionSettings(targets_path=path).targets()),1)

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';path.write_text('not json')
            with self.assertRaises(ValueError):
                Journal(path)


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS')=='1','Exige ambiente isolado')
class PeriodicDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings=Settings.environment();require_isolated(self.settings)
        self.conn=await asyncpg.connect(self.settings.database_url)
        self.tx=self.conn.transaction();await self.tx.start()
        self.folder=tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self.cleanup)
        self.stamp=datetime.now(timezone.utc)-timedelta(days=2)
        self.marker='PeriodicFixture'+secrets.token_hex(8)
        self.url='https://www.kabum.com.br/produto/123456/'+self.marker
        self.path=Path(self.folder.name)/'targets.json'
        self.path.write_text(json.dumps({'targets':[{'store':'KaBuM!','url':self.url,'enabled':True}]}))
        # delay zero so em testes; environment recusa esse valor em operacao.
        self.config=CollectionSettings(enabled=True,delay=0,targets_path=self.path)
        self.journal=Journal(Path(self.folder.name)/'state.json')

    async def cleanup(self):
        await self.tx.rollback();await self.conn.close();self.folder.cleanup()

    def item(self,price=90):
        return dict(nome=self.marker,preco=price,link=self.url,imagem_url='https://images.example.com/test.jpg',
                    coletado_em=self.stamp,fonte_coleta='html_publico_jsonld',disponivel=True)

    async def test_restart_same_run_and_freshness_prevent_duplicate(self):
        fetch=Mock(return_value=([self.item()],'ok'))
        first=await collect_due(self.conn,self.config,self.journal,fetch,self.stamp)
        self.assertEqual(first[0]['observations'],1)
        self.assertEqual(await collect_due(self.conn,self.config,Journal(self.journal.path),fetch,self.stamp),[])
        self.assertEqual(fetch.call_count,1)
        # Mesmo sem arquivo local, frescor no PostgreSQL impede nova requisicao.
        other=Journal(Path(self.folder.name)/'other.json')
        self.assertEqual(await collect_due(self.conn,self.config,other,fetch,self.stamp),[])
        self.assertEqual(fetch.call_count,1)

    async def test_unchanged_price_history_and_new_transition_alert(self):
        user=await self.conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES('Teste',$1,'unused') RETURNING id",self.marker+'@example.com')
        alert=await self.conn.fetchval('INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES($1,$2,100) RETURNING id',user,self.marker)
        for i,price in enumerate((90,90,110,80)):
            if i:self.stamp+=timedelta(seconds=self.config.interval)
            await collect_due(self.conn,self.config,self.journal,Mock(return_value=([self.item(price)],'ok')),self.stamp)
            await scan(self.conn)
            count=await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1',alert)
            self.assertEqual(count,2 if i==3 else 1)
        pid=await self.conn.fetchval('SELECT id FROM hunter_catalog_products WHERE link=$1',self.url)
        rows=await observations(self.conn,product_id=pid)
        self.assertEqual(len(rows),4)
        self.assertEqual(statistics(rows)['produtos'][0]['preco_atual'],80)
        self.assertEqual(cluster_products(rows)['status'],'dados_insuficientes')

    async def test_blocked_store_backoff_and_other_store_preserved(self):
        second='https://www.kabum.com.br/produto/99999/outro'
        self.path.write_text(json.dumps({'targets':[{'store':'KaBuM!','url':u,'enabled':True} for u in (self.url,second)]}))
        fetch=Mock(return_value=([],'pagina_http_403'))
        result=await collect_due(self.conn,self.config,self.journal,fetch,self.stamp)
        self.assertEqual(len(result),1)
        self.assertEqual(fetch.call_count,1)
        state=Journal(self.journal.path).data
        self.assertGreaterEqual(datetime.fromisoformat(state['stores']['KaBuM!']),self.stamp+timedelta(days=1))
        self.assertEqual(await collect_due(self.conn,self.config,self.journal,fetch,self.stamp+timedelta(hours=6)),[])

    async def test_network_failure_preserves_data_and_releases_lock(self):
        fetch=Mock(side_effect=ConnectionError())
        result=await collect_due(self.conn,self.config,self.journal,fetch,self.stamp)
        self.assertEqual(result[0]['status'],'failure_ConnectionError')
        other=await asyncpg.connect(self.settings.database_url)
        try:
            from scraping.periodic import LOCK
            self.assertTrue(await other.fetchval('SELECT pg_try_advisory_lock($1::bigint)',LOCK))
        finally:await other.close()

    async def test_concurrent_scheduler_skips_collection(self):
        from scraping.periodic import LOCK
        other=await asyncpg.connect(self.settings.database_url)
        try:
            await other.fetchval('SELECT pg_advisory_lock($1::bigint)',LOCK)
            fetch=Mock()
            self.assertEqual(await collect_due(self.conn,self.config,self.journal,fetch,self.stamp),[])
            fetch.assert_not_called()
        finally:await other.close()

    async def test_disabled_does_not_touch_network(self):
        fetch=Mock()
        self.assertEqual(await collect_due(self.conn,replace(self.config,enabled=False),self.journal,fetch,self.stamp),[])
        fetch.assert_not_called()

    async def test_slow_http_does_not_block_event_loop(self):
        entered=threading.Event();release=threading.Event()
        def slow_fetch(*args):
            entered.set();release.wait(timeout=3)
            return [self.item()],'ok'
        task=asyncio.create_task(collect_due(self.conn,self.config,self.journal,slow_fetch,self.stamp))
        try:
            for _ in range(100):
                if entered.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(entered.is_set())
            self.assertFalse(task.done())
            await asyncio.wait_for(asyncio.sleep(.01),timeout=.3)
        finally:
            release.set();await task


class SchedulerCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_scheduler_runs_collection_and_alert_cycle(self):
        from messaging.scheduler import run
        conn=Mock();conn.close=AsyncMock();conn.fetchval=AsyncMock(return_value=True);conn.execute=AsyncMock()
        @asynccontextmanager
        async def broker(settings):
            yield Mock()
        with patch('messaging.scheduler.Settings.environment',return_value=Settings('unused','unused')), \
             patch('messaging.scheduler.CollectionSettings.environment',return_value=CollectionSettings(enabled=True)), \
             patch('messaging.scheduler.run_collection',new_callable=AsyncMock) as collect, \
             patch('messaging.scheduler.asyncpg.connect',new=AsyncMock(return_value=conn)), \
             patch('messaging.scheduler.connect',new=broker), \
             patch('messaging.scheduler.scan',new_callable=AsyncMock) as scan_mock, \
             patch('messaging.scheduler.dispatch',new_callable=AsyncMock) as dispatch_mock:
            await run(once=True)
            collect.assert_awaited_once()
            scan_mock.assert_awaited_once_with(conn)
            dispatch_mock.assert_awaited_once()
