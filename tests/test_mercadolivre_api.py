"""API oficial: fixtures ficticias em memoria e integracao apenas no banco isolado."""
import os
import secrets
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from decimal import Decimal
from datetime import datetime, timezone

from scraping.buscar_produtosmercadolivre import MercadoLivreAPI, MercadoLivreAPIError, save_api_batch


def response(data=None, status=200):
    r=Mock(status_code=status)
    r.json.return_value=data
    return r


def item(number='123', seller=10, **changes):
    data=dict(id='MLB'+number,site_id='MLB',status='active',currency_id='BRL',available_quantity=1,
              title='FICTICIO Teclado teste',seller_id=seller,price=99999,
              permalink='https://produto.mercadolivre.com.br/MLB-'+number+'-teclado-teste-_JM',
              pictures=[{'secure_url':'https://images.example.invalid/teclado.jpg'}],variations=[])
    return {**data,**changes}


class OfficialAPITests(unittest.TestCase):
    def client(self, responses):
        session=Mock()
        session.get.side_effect=responses
        return MercadoLivreAPI('fixture-token-not-a-real-secret',session),session

    def test_missing_token_stops_before_network(self):
        with patch.dict(os.environ,{},clear=True),patch('requests.Session') as session:
            with self.assertRaisesRegex(ValueError,'OAuth'):
                MercadoLivreAPI()
            session.assert_not_called()

    @patch('time.sleep')
    def test_general_discovery_has_no_own_seller_filter_and_uses_sale_price(self,sleep):
        client,session=self.client([response({'results':[{'id':'MLB123'},{'id':'MLB124'}]}),
            response(item()),response({'amount':99.90,'currency_id':'BRL'}),
            response(item('124',seller=20)),response({'amount':199.90,'currency_id':'BRL'})])
        rows=client.collect('teclado',2,'general')
        self.assertEqual({r['seller_id'] for r in rows},{10,20})
        self.assertEqual(rows[0]['preco'],Decimal('99.90'))
        self.assertNotIn('seller_id',session.get.call_args_list[0].kwargs['params'])
        self.assertEqual(session.get.call_args_list[2].kwargs['params'],{'context':'channel_marketplace'})
        self.assertEqual(rows[0]['fonte_coleta'],'api_oficial_mercadolivre')
        self.assertTrue(rows[0]['imagem_url'].startswith('https://'))
        self.assertTrue(rows[0]['coletado_em'].tzinfo)

    @patch('time.sleep')
    def test_catalog_model_without_authorized_winner_is_not_an_offer(self,sleep):
        client,session=self.client([response({'results':[{'id':'MLB100'}]}),
            response({'id':'MLB100','status':'active','name':'Modelo sem oferta','price':1})])
        self.assertEqual(client.collect('ssd',1,'catalog'),[])
        self.assertEqual(session.get.call_count,2)

    @patch('time.sleep')
    def test_catalog_winner_is_revalidated_as_individual_ad(self,sleep):
        client,session=self.client([response({'results':[{'id':'MLB100'}]}),
            response({'id':'MLB100','status':'active','buy_box_winner':{'item_id':'MLB123','price':1}}),
            response(item()),response({'amount':100,'currency_id':'BRL'})])
        row=client.collect('ssd',1,'catalog')[0]
        self.assertEqual(row['external_id'],'MLB123')
        self.assertEqual(row['preco'],Decimal('100'))
        self.assertIn('/items/MLB123',session.get.call_args_list[2].args[0])

    def test_forbidden_stops_without_retry_fallback_or_secret_in_error(self):
        client,session=self.client([response({'message':'DO NOT ECHO fixture-token-not-a-real-secret'},403)])
        with self.assertRaises(MercadoLivreAPIError) as caught:
            client.collect('ssd',1,'general')
        self.assertEqual(session.get.call_count,1)
        self.assertNotIn('fixture-token',str(caught.exception))
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    @patch('time.sleep')
    def test_forbidden_price_does_not_fall_back_to_legacy_item_price(self,sleep):
        client,session=self.client([response(item()),response({},403)])
        with self.assertRaises(MercadoLivreAPIError):client.item('MLB123')
        self.assertEqual(session.get.call_count,2)

    def test_unsafe_ids_and_paths_never_receive_bearer(self):
        client,session=self.client([])
        for invalid in ('MLA123','../secret','https://attacker.invalid/'):
            with self.assertRaises(ValueError):client.item(invalid)
        with self.assertRaises(ValueError):client.get('https://attacker.invalid/')
        session.get.assert_not_called()

    @patch('time.sleep')
    def test_inactive_foreign_or_ambiguous_offers_are_not_imported(self,sleep):
        for changes in ({'status':'paused'},{'site_id':'MLA'},{'currency_id':'USD'},
                        {'available_quantity':0},{'seller_id':None},{'variations':[{},{}]},
                        {'pictures':[{'url':'http://images.example.invalid/not-secure.jpg'}]}):
            client,session=self.client([response(item(**changes))])
            self.assertIsNone(client.item('MLB123'))
            self.assertEqual(session.get.call_count,1)

    def test_bad_json_and_redirect_are_rejected(self):
        client,session=self.client([response(status=302)])
        with self.assertRaises(MercadoLivreAPIError):client.get('/products/search')
        r=response();r.json.side_effect=ValueError('private detail')
        client,session=self.client([r])
        with self.assertRaisesRegex(ValueError,'nao JSON'):client.get('/products/search')


@unittest.skipUnless(os.environ.get('HUNTER_TEST_DATABASE_URL'),'Banco isolado nao configurado')
class APIStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_tables_preserve_idempotency_and_disabled_candidates(self):
        import asyncpg
        from config.settings import test_database_url
        from scraping.catalog_store import normalize
        code=str(secrets.randbelow(10**15)+10**15)
        row=normalize(dict(nome='FICTICIO API '+code,preco='99.90',
             link='https://produto.mercadolivre.com.br/MLB-'+code+'-fixture-_JM',
             imagem_url='https://images.example.invalid/fixture.jpg',coletado_em=datetime.now(timezone.utc),
             fonte_coleta='fixture_api_storage'))
        row.update(external_id='MLB'+code,seller_id=123)
        self.assertEqual(await save_api_batch([row],'hunter_test'),1)
        self.assertEqual(await save_api_batch([row],'hunter_test'),0)
        conn=await asyncpg.connect(test_database_url())
        try:
            pid=await conn.fetchval("SELECT id FROM hunter_catalog_products WHERE loja='Mercado Livre' AND link=$1",row['link'])
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM hunter_price_observations WHERE produto_id=$1',pid),1)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM hunter_catalog_candidates WHERE product_id=$1',pid),1)
            self.assertEqual(await conn.fetchval("SELECT state FROM hunter_catalog_sources WHERE code='mercadolivre_api'"),'disabled')
        finally:await conn.close()

    async def test_wrong_destination_is_refused_before_writes(self):
        with self.assertRaisesRegex(ValueError,'diverge'):
            await save_api_batch([],'not_the_test_database')
