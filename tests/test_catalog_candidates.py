"""Fila inativa: fixtures exclusivamente no banco isolado; sem HTTP ou coletores."""
import asyncio
import os
import secrets
import unittest
from datetime import timedelta
from uuid import uuid4

import asyncpg

from catalog_expansion.repository import CandidateRepository, canonical_url
from messaging.config import Settings
from messaging.migrate import migrate
from messaging.testing import require_isolated


class CandidateURLTests(unittest.TestCase):
    def test_tracking_and_fragment_equivalence(self):
        self.assertEqual(canonical_url('https://SHOP.example:443/item?utm_source=x#photo', ['shop.example']),
                         'https://shop.example/item')

    def test_identity_query_preserved(self):
        self.assertNotEqual(canonical_url('https://shop.example/item?seller=1', ['shop.example']),
                            canonical_url('https://shop.example/item?seller=2', ['shop.example']))

    def test_reject_credentials_secrets_and_wrong_hosts(self):
        for url in ('http://shop.example/item','https://u:p@shop.example/item',
                    'https://evil.example/item','https://shop.example/item?access_token=secret',
                    'https://shop.example:8443/item','https://shop.example/item\n',
                    'https://shop.example/item?api_key=secret'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_url(url,['shop.example'])


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS') == '1', 'Exige ambiente isolado')
class CandidateDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = Settings.environment()
        require_isolated(self.settings)
        self.conn = await asyncpg.connect(self.settings.database_url)
        self.addAsyncCleanup(self.conn.close)
        # Concorrencia exige fixtures visiveis por conexoes diferentes. Permanecem
        # somente no banco isolado; demais testes fazem rollback.
        self.concurrent = self._testMethodName.startswith('test_concurrent')
        if not self.concurrent:
            tx = self.conn.transaction()
            await tx.start()
            async def rollback():
                await tx.rollback()
            self.addAsyncCleanup(rollback)
        self.repo = CandidateRepository(self.conn)
        self.code = 'test_' + secrets.token_hex(8)
        self.source = await self.repo.create_source(self.code, 'KaBuM!', 'manual', ['shop.example'])

    async def enabled(self):
        await self.conn.execute("UPDATE hunter_catalog_sources SET state='enabled' WHERE id=$1", self.source['id'])

    async def add(self, suffix='one', **kwargs):
        return await self.repo.add(self.source['id'],'https://shop.example/'+suffix, **kwargs)

    async def expired(self, candidate_id):
        # Simula passagem de tempo exclusivamente nas fixtures isoladas.
        await self.conn.execute('''UPDATE hunter_catalog_candidates
            SET lease_expires_at=clock_timestamp()-interval '1 second',
                next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=$1''', candidate_id)

    async def test_source_disabled_by_default(self):
        await self.add()
        self.assertEqual(self.source['state'],'disabled')
        self.assertEqual(await self.repo.list(eligible=True),[])
        self.assertEqual(await self.repo.claim('worker'),[])

    async def test_deduplicate_url_tracking(self):
        a = await self.add('one?utm_source=test')
        b = await self.add('one#photo')
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(a['original_url'],'https://shop.example/one?utm_source=test')

    async def test_external_identity_slug_and_variant(self):
        a = await self.add('old',external_id='sku1',variant='black')
        b = await self.add('new',external_id='sku1',variant='black')
        c = await self.add('white',external_id='sku1',variant='white')
        self.assertEqual(a['id'],b['id'])
        self.assertNotEqual(a['id'],c['id'])
        with self.assertRaises(ValueError):
            await self.add('old',external_id='other',variant='black')

    async def test_identity_collision_requires_review(self):
        await self.add('one',external_id='sku1')
        await self.add('two',external_id='sku2')
        with self.assertRaises(ValueError):
            await self.add('two',external_id='sku1')

    async def test_state_transitions_and_safe_errors(self):
        a = await self.add()
        with self.assertRaises(ValueError):
            await self.repo.transition(a['id'],'active')
        with self.assertRaises(ValueError):
            await self.repo.transition(a['id'],'rejected')
        with self.assertRaises(ValueError):
            await self.repo.transition(a['id'],'rejected','password=secret')
        row = await self.repo.transition(a['id'],'rejected','manual_rejection')
        self.assertEqual(row['error_code'],'manual_rejection')
        row = await self.repo.transition(a['id'],'pending')
        self.assertIsNone(row['error_code'])

    async def test_eligibility_and_attempt_count(self):
        a = await self.add()
        await self.enabled()
        self.assertIn(a['id'],[r['id'] for r in await self.repo.list(state='pending',eligible=True)])
        rows = await self.repo.claim('worker')
        row = next(r for r in rows if r['id']==a['id'])
        self.assertEqual(row['attempts'],1)
        self.assertGreaterEqual(row['next_attempt_at']-row['last_attempt_at'],timedelta(seconds=21600))
        self.assertEqual(await self.repo.claim('other'),[])
        with self.assertRaises(ValueError):
            await self.repo.transition(a['id'],'paused')

    async def test_success_run_timestamps_and_cooldown(self):
        await self.add(); await self.enabled()
        row = (await self.repo.claim('worker'))[0]
        done = await self.repo.finish(row['id'],row['lease_token'],'success',http_status=200,observations_inserted=2)
        self.assertEqual(done['state'],'active')
        self.assertIsNone(done['lease_token'])
        self.assertIsNotNone(done['last_verified_at'])
        run = (await self.repo.runs(row['id']))[0]
        self.assertIsNotNone(run['started_at'].tzinfo)
        self.assertGreaterEqual(run['finished_at'],run['started_at'])
        self.assertEqual(run['observations_inserted'],2)
        with self.assertRaises(ValueError):
            await self.repo.finish(row['id'],row['lease_token'],'success')

    async def test_failure_and_blocking(self):
        await self.add(); await self.enabled()
        row = (await self.repo.claim('worker'))[0]
        done = await self.repo.finish(row['id'],row['lease_token'],'failed',error='timeout')
        self.assertEqual(done['state'],'backoff')
        await self.conn.execute("UPDATE hunter_catalog_candidates SET next_attempt_at=clock_timestamp() WHERE id=$1",row['id'])
        row = (await self.repo.claim('worker'))[0]
        done = await self.repo.finish(row['id'],row['lease_token'],'blocked',http_status=403,error='access_denied')
        self.assertEqual(done['state'],'blocked')
        self.assertEqual(done['attempts'],2)
        self.assertEqual(await self.repo.claim('worker'),[])

    async def test_expiration_recovery_and_fencing(self):
        await self.add(); await self.enabled()
        old = (await self.repo.claim('old'))[0]
        await self.expired(old['id'])
        with self.assertRaises(ValueError):
            await self.repo.finish(old['id'],old['lease_token'],'success')
        new = (await self.repo.claim('new'))[0]
        self.assertNotEqual(old['lease_token'],new['lease_token'])
        self.assertEqual(new['attempts'],2)
        self.assertEqual({r['result'] for r in await self.repo.runs(old['id'])},{'expired','running'})
        with self.assertRaises(ValueError):
            await self.repo.finish(old['id'],old['lease_token'],'success')
        await self.repo.finish(new['id'],new['lease_token'],'success')

    async def test_invalid_results_do_not_finish_run(self):
        await self.add(); await self.enabled()
        row = (await self.repo.claim('worker'))[0]
        for kwargs in ({'result':'failed'}, {'result':'success','http_status':403},
                       {'result':'blocked','error':'network','observations_inserted':1},
                       {'result':'failed','error':'secret=abc'}):
            with self.assertRaises(ValueError):
                await self.repo.finish(row['id'],row['lease_token'],**kwargs)
        self.assertEqual((await self.repo.runs(row['id']))[0]['result'],'running')

    async def test_constraints_and_references(self):
        a = await self.add()
        for sql, args in (
            ("UPDATE hunter_catalog_candidates SET source_id=-1 WHERE id=$1",(a['id'],)),
            ("UPDATE hunter_catalog_candidates SET product_id=-1 WHERE id=$1",(a['id'],)),
            ("UPDATE hunter_catalog_candidates SET attempts=-1 WHERE id=$1",(a['id'],)),
            ("UPDATE hunter_catalog_candidates SET lease_token=$2 WHERE id=$1",(a['id'],uuid4())),
            ("UPDATE hunter_catalog_sources SET interval_seconds=1 WHERE id=$1",(self.source['id'],)),
        ):
            async with self.conn.transaction():
                with self.assertRaises(asyncpg.IntegrityConstraintViolationError):
                    async with self.conn.transaction():
                        await self.conn.execute(sql,*args)

    async def test_wrong_shop_product_rejected(self):
        product = await self.conn.fetchval("INSERT INTO hunter_catalog_products(loja,link) VALUES('Pichau',$1) RETURNING id",
                                          'https://shop.example/'+self.code)
        with self.assertRaises(ValueError):
            await self.add(product_id=product)

    async def test_existing_history_untouched(self):
        before = await self.conn.fetchrow('''SELECT (SELECT count(*) FROM hunter_catalog_products) products,
            (SELECT count(*) FROM hunter_price_observations) observations,
            (SELECT count(*) FROM alertas_preco) alerts''')
        await self.add(); await self.enabled()
        row = (await self.repo.claim('worker'))[0]
        await self.repo.finish(row['id'],row['lease_token'],'success')
        after = await self.conn.fetchrow('''SELECT (SELECT count(*) FROM hunter_catalog_products) products,
            (SELECT count(*) FROM hunter_price_observations) observations,
            (SELECT count(*) FROM alertas_preco) alerts''')
        self.assertEqual(before,after)

    async def test_migration_idempotent_official_executor(self):
        await migrate('004')
        await migrate('004')
        self.assertEqual(await self.conn.fetchval("SELECT count(*) FROM hunter_schema_migrations WHERE version='004'"),1)

    async def test_concurrent_admission_deduplicates(self):
        other = await asyncpg.connect(self.settings.database_url)
        self.addAsyncCleanup(other.close)
        a,b = await asyncio.gather(self.add(external_id='one'),
            CandidateRepository(other).add(self.source['id'],'https://shop.example/other',external_id='one'))
        self.assertEqual(a['id'],b['id'])

    async def test_concurrent_claim_skips_locked(self):
        a = await self.add(); await self.enabled()
        other = await asyncpg.connect(self.settings.database_url)
        self.addAsyncCleanup(other.close)
        async with self.conn.transaction():
            first = await self.repo.claim('worker1')
            second = await asyncio.wait_for(CandidateRepository(other).claim('worker2'),2)
            self.assertIn(a['id'],[r['id'] for r in first])
            self.assertNotIn(a['id'],[r['id'] for r in second])
        # Mantem fixture concluida e fonte desabilitada para nao interferir nas proximas suites.
        for row in first:
            await self.repo.finish(row['id'],row['lease_token'],'success')
        await self.conn.execute("UPDATE hunter_catalog_sources SET state='disabled' WHERE id=$1",self.source['id'])
