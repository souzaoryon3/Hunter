"""Rotacao isolada: ofertas sinteticas explicitas, HTTP sempre simulado."""
import asyncio
import os
import secrets
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import AsyncMock,patch

import asyncpg

from catalog_expansion.adapters import FetchResult,retry_after
from catalog_expansion.heartbeat import SchedulerGuard,LOCK as SCHEDULER_LOCK
from catalog_expansion.repository import CandidateRepository
from catalog_expansion.rotation import collect_rotation,reserve,seed_existing
from messaging.config import Settings
from messaging.testing import require_isolated
from messaging.catalog import catalog_sql
from scraping.periodic import CollectionSettings,Journal
from scraping.catalog_store import save_observations


class AdapterTests(unittest.TestCase):
    def test_existing_adapter_cannot_enable_other_stores(self):
        from catalog_expansion.adapters import public_product
        with patch('catalog_expansion.adapters.collect_sample') as fetch:
            with self.assertRaises(ValueError):
                public_product({'loja':'Unapproved','integration_type':'public_page'},
                    {'canonical_url':'https://www.kabum.com.br/produto/1/test'})
            fetch.assert_not_called()

    def test_retry_after_seconds_and_http_date(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        self.assertEqual(retry_after('3600',now),now+timedelta(hours=1))
        self.assertEqual(retry_after('Fri, 02 Jan 2026 00:00:00 GMT',now),now+timedelta(days=1))
        self.assertIsNone(retry_after('invalid',now))


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS')=='1','Exige ambiente isolado')
class RotationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings=Settings.environment();require_isolated(self.settings)
        self.conn=await asyncpg.connect(self.settings.database_url)
        self.addAsyncCleanup(self.conn.close)
        self.tx=self.conn.transaction();await self.tx.start()
        async def rollback(): await self.tx.rollback()
        self.addAsyncCleanup(rollback)
        self.repo=CandidateRepository(self.conn)
        self.marker='rotation_'+secrets.token_hex(6)
        self.source=await self.repo.create_source(self.marker,self.marker,'manual',['shop.example'],request_limit=6)
        await self.conn.execute('''UPDATE hunter_catalog_sources SET state='enabled',adapter='fixture',
            permission_reference='synthetic_isolated_test' WHERE id=$1''',self.source['id'])
        await self.conn.execute("UPDATE hunter_collection_control SET next_round_at=clock_timestamp()-interval '1 second'")
        self.config=CollectionSettings(enabled=True)
        self.calls=[]
        self.sleep_patch=patch('catalog_expansion.rotation.asyncio.sleep',new=self.advance_request_delay)
        self.sleep_patch.start();self.addCleanup(self.sleep_patch.stop)

    async def advance_request_delay(self,*args):
        await self.conn.execute('UPDATE hunter_catalog_sources SET next_request_at=clock_timestamp() WHERE id=$1',self.source['id'])

    async def add(self,index,source=None):
        return await self.repo.add((source or self.source)['id'],f'https://shop.example/{self.marker}/{index}',external_id=str(index))

    def fetch(self,source,candidate):
        self.calls.append(candidate['id'])
        return FetchResult([dict(nome='Synthetic isolated mouse',preco='100.00',
            link=candidate['canonical_url'],imagem_url='https://shop.example/fixture.jpg',
            coletado_em=datetime.now(timezone.utc),fonte_coleta='fixture')],'ok',200)

    async def collect(self,fetch=None,**config):
        return await collect_rotation(self.conn,replace(self.config,**config),{'fixture':fetch or self.fetch})

    async def test_more_than_six_oldest_due_and_restart_cooldown(self):
        rows=[await self.add(i) for i in range(8)]
        await self.conn.execute('''UPDATE hunter_catalog_candidates SET next_attempt_at=
            clock_timestamp()-interval '1 day'+id*interval '1 second' WHERE source_id=$1''',self.source['id'])
        result=await self.collect()
        self.assertEqual(len(result),6)
        self.assertEqual(self.calls,[r['id'] for r in rows[:6]])
        self.assertTrue(all(r['result']=='success' for r in result))
        self.assertEqual(await self.collect(),[])
        # Simula uma rodada posterior sem tocar historico.
        await self.conn.execute("UPDATE hunter_collection_control SET next_round_at=clock_timestamp()")
        await self.conn.execute('''UPDATE hunter_catalog_sources SET window_started_at=clock_timestamp()-interval '7 hours'
            WHERE id=$1''',self.source['id'])
        self.assertEqual(len(await self.collect()),2)
        self.assertEqual(self.calls[-2:],[r['id'] for r in rows[6:]])

    async def test_source_product_and_http_quotas(self):
        for i in range(4): await self.add(i)
        await self.conn.execute('UPDATE hunter_catalog_sources SET request_limit=3,http_request_limit=4 WHERE id=$1',self.source['id'])
        self.assertEqual(len(await self.collect()),2)
        source=await self.conn.fetchrow('SELECT * FROM hunter_catalog_sources WHERE id=$1',self.source['id'])
        self.assertEqual(source['products_in_window'],2)
        self.assertEqual(source['http_in_window'],4)

    async def test_repeated_observation_does_not_duplicate_or_repeat_alert(self):
        from messaging.service import scan
        row=await self.add(1)
        stamp=datetime.now(timezone.utc)-timedelta(seconds=1)
        def fixed(source,candidate):
            result=self.fetch(source,candidate);result.items[0]['coletado_em']=stamp
            return result
        uid=await self.conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES($1,$2,'fixture') RETURNING id",self.marker,self.marker+'@example.test')
        aid=await self.conn.fetchval("INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES($1,'Synthetic isolated mouse',100) RETURNING id",uid)
        first=await self.collect(fixed)
        self.assertEqual(first[0]['observations'],1)
        await scan(self.conn)
        await self.conn.execute('UPDATE hunter_collection_control SET next_round_at=clock_timestamp()')
        await self.conn.execute('UPDATE hunter_catalog_candidates SET next_attempt_at=clock_timestamp() WHERE id=$1',row['id'])
        await self.conn.execute("UPDATE hunter_catalog_sources SET window_started_at=clock_timestamp()-interval '7 hours' WHERE id=$1",self.source['id'])
        second=await self.collect(fixed)
        self.assertEqual(second[0]['observations'],0)
        await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1',aid),1)

    async def test_retry_after_suspends_source(self):
        await self.add(1);await self.add(2)
        until=datetime.now(timezone.utc)+timedelta(days=2)
        result=await self.collect(lambda *args:FetchResult([],'pagina_http_429',429,until))
        self.assertEqual(len(result),1)
        source=await self.conn.fetchrow('SELECT * FROM hunter_catalog_sources WHERE id=$1',self.source['id'])
        self.assertGreaterEqual(source['suspended_until'],until)
        self.assertEqual(source['state'],'enabled')

    async def test_block_stops_source_without_other_requests(self):
        await self.add(1);await self.add(2)
        result=await self.collect(lambda *args:FetchResult([],'pagina_http_403',403))
        self.assertEqual(len(result),1)
        self.assertEqual(await self.conn.fetchval('SELECT state FROM hunter_catalog_sources WHERE id=$1',self.source['id']),'blocked')

    async def test_unapproved_or_unimplemented_source_not_called(self):
        await self.add(1)
        await self.conn.execute('UPDATE hunter_catalog_sources SET permission_reference=NULL WHERE id=$1',self.source['id'])
        self.assertEqual(await self.collect(),[])
        await self.conn.execute("UPDATE hunter_catalog_sources SET permission_reference='fixture',adapter='not_implemented' WHERE id=$1",self.source['id'])
        self.assertEqual(await self.collect(),[])
        self.assertEqual(self.calls,[])

    async def test_failed_fetch_keeps_history(self):
        await self.add(1)
        before=await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations')
        def fail(*args): raise RuntimeError('sensitive detail not persisted')
        result=await self.collect(fail)
        self.assertEqual(result[0]['result'],'failed')
        self.assertEqual(before,await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations'))
        self.assertEqual(await self.conn.fetchval('SELECT error_code FROM hunter_catalog_candidates WHERE id=$1',result[0]['candidate_id']),'network')

    async def test_wrong_url_or_missing_image_not_imported(self):
        await self.add(1)
        def wrong(source,candidate):
            result=self.fetch(source,candidate);result.items[0]['link']='https://shop.example/other'
            return result
        result=await self.collect(wrong)
        self.assertEqual(result[0]['result'],'failed')
        self.assertIsNone(await self.conn.fetchval('SELECT product_id FROM hunter_catalog_candidates WHERE id=$1',result[0]['candidate_id']))

    async def test_expired_lease_cannot_write_observations(self):
        row=await self.add(1)
        claimed=(await self.repo.claim('old'))[0]
        await self.conn.execute("UPDATE hunter_catalog_candidates SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1",row['id'])
        with self.assertRaises(ValueError):
            await self.repo.finish(row['id'],claimed['lease_token'],'success',observations_inserted=1)
        self.assertEqual(await self.collect(),[]) # cooldown still respected

    async def test_collection_lock_rejects_other_instance(self):
        from scraping.periodic import LOCK
        await self.add(1)
        other=await asyncpg.connect(self.settings.database_url)
        try:
            await other.fetchval('SELECT pg_advisory_lock($1::bigint)',LOCK)
            self.assertEqual(await self.collect(),[])
        finally: await other.close()

    async def test_lifetime_scheduler_guard_and_heartbeat(self):
        # Fixtures transacionais da tabela heartbeat nao podem bloquear outra
        # conexao: segunda instancia deve recusar antes de tentar escreve-la.
        guard=SchedulerGuard(self.conn)
        other=await asyncpg.connect(self.settings.database_url)
        try:
            self.assertTrue(await guard.start())
            self.assertFalse(await SchedulerGuard(other).start())
            with patch('catalog_expansion.heartbeat.wall_time',side_effect=[100,500]),patch(
                'catalog_expansion.heartbeat.monotonic_time',side_effect=[100,110]):
                await guard.tick();await guard.tick()
            row=await self.conn.fetchrow('SELECT * FROM hunter_scheduler_heartbeat')
            self.assertEqual(row['clock_drift_seconds'],390)
            self.assertGreaterEqual(row['max_gap_seconds'],400)
            await guard.stop()
            self.assertEqual(await self.conn.fetchval('SELECT state FROM hunter_scheduler_heartbeat'),'stopped')
        finally:
            await self.conn.fetchval('SELECT pg_advisory_unlock($1::bigint)',SCHEDULER_LOCK)
            await other.close()

    async def test_registered_shop_b2b_and_promotional_separation(self):
        item=dict(nome='Synthetic B2B',preco=90,link='https://shop.example/'+self.marker,
            imagem_url='https://shop.example/test.jpg',coletado_em=datetime.now(timezone.utc),
            fonte_coleta='fixture',channel='b2b')
        await save_observations(self.conn,self.marker,[item])
        sql=await catalog_sql(self.conn)
        self.assertFalse(await self.conn.fetchval(f'SELECT EXISTS(SELECT 1 FROM ({sql}) x WHERE loja=$1)',self.marker))
        with self.assertRaises(ValueError):
            await save_observations(self.conn,self.marker,[{**item,'channel':'retail'}])
        with self.assertRaises(ValueError):
            await save_observations(self.conn,self.marker,[{**item,'price_kind':'promotional'}])

    async def test_dynamic_shop_api(self):
        import app as backend
        from test_api import http
        async def db(): yield self.conn
        backend.app.dependency_overrides[backend.get_db]=db
        try:
            status,data=await http('GET','/lojas')
            self.assertEqual(status,200);self.assertIn(self.marker,data['lojas'])
            status,data=await http('GET','/buscar-produtos?nome=mouse&loja='+self.marker)
            self.assertEqual(status,200)
            status,data=await http('GET','/buscar-produtos?nome=mouse&loja=not_registered')
            self.assertEqual(status,422)
        finally: backend.app.dependency_overrides.clear()

    async def test_seed_existing_idempotent_preserves_ids_and_journal(self):
        # KaBuM fixture explicitamente sintetica, nunca no principal.
        link='https://www.kabum.com.br/produto/987654321/'+self.marker
        stamp=datetime.now(timezone.utc)-timedelta(hours=1)
        await save_observations(self.conn,'KaBuM!',[dict(nome='Synthetic seed',preco=100,link=link,
            imagem_url='https://shop.example/test.jpg',coletado_em=stamp,fonte_coleta='fixture')])
        with tempfile.TemporaryDirectory() as folder:
            import json
            path=Path(folder)/'targets.json'
            path.write_text(json.dumps({'targets':[dict(store='KaBuM!',url=link,enabled=True)]}))
            config=replace(self.config,targets_path=path)
            journal=Journal(Path(folder)/'state.json')
            target=config.targets()[0]
            cooldown=stamp+timedelta(days=1)
            journal.data['targets'][target['key']]={'next_due':cooldown.isoformat()}
            before=await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations')
            self.assertEqual(await seed_existing(self.conn,config,journal),1)
            self.assertEqual(await seed_existing(self.conn,config,journal),1)
            row=await self.conn.fetchrow('SELECT * FROM hunter_catalog_candidates WHERE canonical_url=$1',link)
            self.assertGreaterEqual(row['next_attempt_at'],cooldown)
            self.assertEqual(row['product_id'],await self.conn.fetchval('SELECT id FROM hunter_catalog_products WHERE link=$1',link))
            self.assertEqual(before,await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations'))
