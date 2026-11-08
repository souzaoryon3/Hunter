"""Estatistica e K-Means com fixtures; integracao exclusivamente isolada."""
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import asyncpg

from data_mining.analysis import statistics, analytical_history, cluster_products
from data_mining.demo import demo_rows
from messaging.config import Settings
from messaging.testing import require_isolated
from scraping.catalog_store import save_observations
from test_api import http
import app as backend

NOW=datetime(2026,11,7,12,tzinfo=timezone.utc)


def sample(prices=(100,120,90),pid=1,days_ago=0):
    return [dict(id=pid*100+i,produto_id=pid,nome='Fixture demonstrativa',loja='Loja ficticia',
        preco=price,disponivel=True,coletado_em=NOW-timedelta(days=len(prices)-1-i+days_ago))
        for i,price in enumerate(prices)]


class MiningCalculationTests(unittest.TestCase):
    def test_statistics_and_opportunity(self):
        result=statistics(sample(),NOW)
        p=result['produtos'][0]
        self.assertAlmostEqual(p['preco_medio'],310/3)
        self.assertEqual((p['preco_minimo'],p['preco_maximo'],p['observacoes']),(90,120,3))
        self.assertAlmostEqual(p['variacao_percentual'],-10)
        self.assertAlmostEqual(p['queda_recente_percentual'],25)
        self.assertTrue(p['oportunidade'])

    def test_single_observation_not_a_trend(self):
        p=statistics(sample([90]),NOW)['produtos'][0]
        self.assertIsNone(p['variacao_percentual'])
        self.assertIsNone(p['volatilidade_percentual'])
        self.assertFalse(p['oportunidade'])
        self.assertEqual(cluster_products(sample([90]),now=NOW)['status'],'dados_insuficientes')

    def test_stale_unavailable_and_small_history_no_opportunity(self):
        self.assertFalse(statistics(sample(days_ago=30),NOW)['produtos'][0]['oportunidade'])
        rows=sample();rows[-1]['disponivel']=False
        self.assertFalse(statistics(rows,NOW)['produtos'][0]['oportunidade'])
        self.assertFalse(statistics(sample([120,90]),NOW)['produtos'][0]['oportunidade'])

    def test_cleaning_dedup_and_time_order(self):
        rows=sample()+[dict(sample()[0],id=999,preco=0),dict(sample()[0],id=998,preco=float('nan')),
                       dict(sample()[0],id=997,preco=float('inf')),
                       dict(sample()[0],id=996,coletado_em=NOW+timedelta(days=1))]
        rows.append(dict(sample()[0],id=995))
        result=statistics(list(reversed(rows)),NOW)
        self.assertEqual(result['resumo']['observacoes'],3)
        self.assertEqual(result['produtos'][0]['preco_atual'],90)

    def test_rolling_mean_and_empty(self):
        series=analytical_history(sample(),NOW)
        self.assertIsNone(series[0]['media_movel_3'])
        self.assertIsNone(series[1]['media_movel_3'])
        self.assertAlmostEqual(series[2]['media_movel_3'],310/3)
        self.assertEqual(statistics([],NOW)['resumo']['produtos'],0)
        self.assertEqual(analytical_history([],NOW),[])

    def test_kmeans_runs_reproducibly_on_explicit_demo(self):
        rows=demo_rows(NOW)
        result=cluster_products(rows,3,NOW)
        self.assertEqual(result['status'],'ok')
        self.assertEqual(len(result['grupos']),3)
        self.assertEqual(len(result['produtos']),9)
        self.assertEqual([p['grupo'] for p in result['produtos']],
                         [p['grupo'] for p in cluster_products(rows,3,NOW)['produtos']])
        self.assertTrue(all(r['fonte_coleta']=='sintetico_demo' for r in rows))

    def test_kmeans_rejects_low_diversity_and_same_day(self):
        identical=[r for pid in range(1,8) for r in sample(pid=pid)]
        self.assertEqual(cluster_products(identical,3,NOW)['status'],'dados_insuficientes')
        same_day=demo_rows(NOW)
        for i,r in enumerate(same_day):
            r['coletado_em']=NOW-timedelta(minutes=i)
        self.assertEqual(cluster_products(same_day,3,NOW)['status'],'dados_insuficientes')
        with self.assertRaises(ValueError):
            cluster_products(identical,1,NOW)


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS')=='1','Exige ambiente isolado')
class MiningEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        settings=Settings.environment();require_isolated(settings)
        self.conn=await asyncpg.connect(settings.database_url)
        self.tx=self.conn.transaction();await self.tx.start()
        self.addAsyncCleanup(self.cleanup)
        async def db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db]=db
        marker='MiningFixture'+secrets.token_hex(8)
        self.link='https://example.com/'+marker
        now=datetime.now(timezone.utc)-timedelta(seconds=10)
        rows=[dict(nome=marker,preco=price,link=self.link,coletado_em=now-timedelta(days=2-i),
                   fonte_coleta='html_publico') for i,price in enumerate((100,120,90))]
        await save_observations(self.conn,'KaBuM!',rows)
        # Fonte de fixture posterior nao pode contaminar as analises reais.
        await save_observations(self.conn,'KaBuM!',[dict(rows[-1],preco=1,fonte_coleta='fixture_browser')])
        self.pid=await self.conn.fetchval('SELECT id FROM hunter_catalog_products WHERE link=$1',self.link)

    async def cleanup(self):
        backend.app.dependency_overrides.clear()
        await self.tx.rollback();await self.conn.close()

    async def test_real_statistics_and_history_ignore_fixture_source(self):
        status,data=await http('GET',f'/analytics/estatisticas?produto_id={self.pid}')
        self.assertEqual(status,200)
        self.assertFalse(data['sintetico'])
        self.assertEqual(data['resumo']['observacoes'],3)
        self.assertEqual(data['produtos'][0]['preco_atual'],90)
        status,data=await http('GET',f'/analytics/historico/{self.pid}')
        self.assertEqual(status,200)
        self.assertEqual(len(data['serie']),3)
        self.assertAlmostEqual(data['serie'][-1]['media_movel_3'],310/3)

    async def test_demo_is_labelled_and_never_writes_database(self):
        before=await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations')
        status,data=await http('GET','/analytics/estatisticas?origem=demo')
        self.assertEqual(status,200)
        self.assertTrue(data['sintetico'])
        self.assertEqual(data['resumo']['produtos'],9)
        status,data=await http('GET','/analytics/agrupamentos?origem=demo&k=3')
        self.assertEqual(status,200)
        self.assertEqual(data['status'],'ok')
        self.assertTrue(data['sintetico'])
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations'),before)

    async def test_validation_missing_and_no_history(self):
        for path in ('/analytics/estatisticas?dias=0','/analytics/agrupamentos?k=1',
                     '/analytics/estatisticas?origem=outro'):
            self.assertEqual((await http('GET',path))[0],422)
        self.assertEqual((await http('GET','/analytics/historico/9223372036854775807'))[0],404)
        _,data=await http('GET',f'/analytics/estatisticas?produto_id={self.pid}&dias=1')
        self.assertEqual(data['resumo']['observacoes'],1)
        self.assertIsNone(data['produtos'][0]['variacao_percentual'])

    async def test_missing_migration_and_limit_are_clear(self):
        with patch('data_mining.api.observations',new=AsyncMock(side_effect=ValueError('Reduza o periodo'))):
            self.assertEqual((await http('GET','/analytics/estatisticas'))[0],413)
        fake=AsyncMock();fake.fetchval.return_value=False
        async def db():
            yield fake
        backend.app.dependency_overrides[backend.get_db]=db
        self.assertEqual((await http('GET','/analytics/estatisticas'))[0],503)
