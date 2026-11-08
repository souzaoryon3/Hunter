"""Catalogo e historico: somente fixtures sinteticas e rollback isolado."""
import os
import secrets
import unittest
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode

import asyncpg
from bs4 import BeautifulSoup

from scraping.catalog_store import image_from_card, normalize, save_observations
from scraping.buscar_produtoskabum import parse_html as kabum_html
from scraping.buscar_produtosmercadolivre import parse_html as ml_html
from scraping.buscar_produtospichau import parse_html as pichau_html
from messaging.config import Settings
from messaging.testing import require_isolated
from messaging.service import scan, dispatch, handle_message
from messaging.broker import connect
from test_api import http
import app as backend


class CatalogParserTests(unittest.TestCase):
    def test_image_urls_and_lazy_loading(self):
        for value in ('javascript:alert(1)', 'data:image/png;base64,xx', 'http://example.com/a', 'https://user:pass@example.com/a'):
            card = BeautifulSoup('<img>', 'html.parser')
            card.img['data-src'] = value
            self.assertIsNone(image_from_card(card, 'https://example.com'))
        card = BeautifulSoup('<img data-src="/photo.jpg" src="data:image/png,x">', 'html.parser')
        self.assertEqual(image_from_card(card, 'https://example.com/item'), 'https://example.com/photo.jpg')

    def test_kabum_product_link_and_image(self):
        items = kabum_html('''<article class="productCard"><a href="/produto/123/mouse">
            <img src="https://cdn.example.com/mouse.jpg"><span class="nameCard">Mouse</span>
            <span class="priceCard">R$ 1.299,90</span></a></article>''', 'https://www.kabum.com.br/perifericos')
        self.assertEqual(items[0]['link'], 'https://www.kabum.com.br/produto/123/mouse')
        self.assertEqual(normalize(items[0])['preco'], Decimal('1299.90'))
        self.assertTrue(items[0]['imagem_url'].endswith('mouse.jpg'))

    def test_mercadolivre_cents_and_image(self):
        items = ml_html('''<li class="ui-search-layout__item"><a class="ui-search-link" href="https://produto.mercadolivre.com.br/MLB-123-mouse-_JM"><h2>Mouse</h2></a>
            <img data-src="https://cdn.example.com/a.jpg"><span class="andes-money-amount__fraction">99</span>
            <span class="andes-money-amount__cents">95</span></li>''', 'https://lista.mercadolivre.com.br/mouse')
        self.assertEqual(items[0]['preco'], 99.95)
        self.assertTrue(items[0]['imagem_url'].endswith('a.jpg'))

    def test_kabum_public_product_jsonld(self):
        import json
        product = {'@type':'Product','name':'Teclado real','image':['https://cdn.example.com/a.jpg'],
                   'offers':{'@type':'Offer','priceCurrency':'BRL','price':129.9,'availability':'https://schema.org/InStock'}}
        html = '<script type="application/ld+json">'+json.dumps(product)+'</script>'
        row = normalize(kabum_html(html,'https://www.kabum.com.br/produto/123/teclado')[0])
        self.assertEqual(row['preco'],Decimal('129.9'))
        self.assertTrue(row['disponivel'])
        self.assertEqual(row['imagem_url'],'https://cdn.example.com/a.jpg')
        product['offers']['@type']='AggregateOffer'
        html = '<script type="application/ld+json">'+json.dumps(product)+'</script>'
        self.assertEqual(kabum_html(html,'https://www.kabum.com.br/produto/123/teclado'),[])

    def test_kabum_listing_jsonld_and_public_hydration(self):
        import json
        product={'@type':'Product','sku':'123','name':'Mouse publico',
                 'image':'https://images.example.com/123.jpg',
                 'offers':{'@type':'Offer','url':'https://www.kabum.com.br/produto/123/mouse',
                           'priceCurrency':'BRL','price':120}}
        data={'catalogServer':{'data':[{'code':123,'name':'Mouse publico','available':True,
               'price':120,'priceWithDiscount':100,'primePriceWithDiscount':70,'oldPrice':500}]}}
        hydration={'props':{'pageProps':{'data':json.dumps(data)}}}
        html='<script type="application/ld+json">'+json.dumps([product])+'</script>'
        html+='<script id="__NEXT_DATA__">'+json.dumps(hydration)+'</script>'
        row=normalize(kabum_html(html,'https://www.kabum.com.br/perifericos')[0])
        self.assertEqual(row['preco'],Decimal('100'))
        self.assertEqual(row['preco_cartao'],Decimal('120'))
        self.assertIn('/produto/123/mouse',row['link'])
        self.assertTrue(row['disponivel'])
        self.assertEqual(row['imagem_url'],'https://images.example.com/123.jpg')

    def test_kabum_listing_does_not_invent_links_or_stock(self):
        import json
        product={'@type':'Product','name':'Mouse publico','image':'https://images.example.com/123.jpg',
                 'offers':{'@type':'Offer','priceCurrency':'BRL','price':120}}
        html='<script type="application/ld+json">'+json.dumps([product])+'</script>'
        self.assertEqual(kabum_html(html,'https://www.kabum.com.br/perifericos'),[])
        product['offers']['url']='https://www.kabum.com.br/produto/123/mouse'
        html='<script type="application/ld+json">'+json.dumps([product])+'</script>'
        self.assertEqual(kabum_html(html,'https://www.kabum.com.br/perifericos'),[])

    def test_kabum_product_ignores_recommended_other_sku(self):
        import json
        products=[{'@type':'Product','name':'Recomendado','image':'https://images.example.com/123.jpg',
                   'offers':{'@type':'Offer','url':'https://www.kabum.com.br/produto/999/outro',
                             'priceCurrency':'BRL','price':120,'availability':'https://schema.org/InStock'}}]
        html='<script type="application/ld+json">'+json.dumps(products)+'</script>'
        self.assertEqual(kabum_html(html,'https://www.kabum.com.br/produto/123/mouse'),[])

    def test_mercadolivre_modern_price_and_duplicate_wrappers(self):
        html='<li class="ui-search-layout__item"><div class="poly-card"><a class="poly-component__title" href="https://www.mercadolivre.com.br/mouse/p/MLB123#tracking"><h3>Mouse teste</h3></a><s><span class="andes-money-amount__fraction">999</span></s><div class="poly-price__current"><span class="andes-money-amount__fraction">99</span><span class="andes-money-amount__cents">90</span></div><img src="https://images.example.invalid/mouse.jpg"></div></li>'
        rows=ml_html(html,'https://lista.mercadolivre.com.br/mouse')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['preco'],99.9)
        self.assertEqual(rows[0]['link'],'https://www.mercadolivre.com.br/mouse/p/MLB123')

    def test_mercadolivre_jsonld_product_and_unsafe_prices(self):
        import json
        product={'@type':'Product','name':'Mouse teste','image':['https://images.example.invalid/mouse.jpg'],
                 'offers':{'@type':'Offer','priceCurrency':'BRL','price':99.9,'availability':'https://schema.org/InStock'}}
        html='<script type="application/ld+json">'+json.dumps({'@graph':[product]})+'</script>'
        row=ml_html(html,'https://www.mercadolivre.com.br/mouse/p/MLB123')[0]
        self.assertEqual(row['imagem_url'],'https://images.example.invalid/mouse.jpg')
        product['offers']={'@type':'AggregateOffer','priceCurrency':'BRL','lowPrice':1}
        html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        self.assertEqual(ml_html(html,'https://www.mercadolivre.com.br/mouse/p/MLB123'),[])

    def test_pichau_image(self):
        items = pichau_html('''<a href="/mouse"><img src="https://cdn.example.com/m.jpg"><h2>Mouse Pichau</h2>
            por R$ 90,00 À vista no PIX</a>''', 'https://www.pichau.com.br/mouse')
        self.assertEqual(items[0]['imagem_url'], 'https://cdn.example.com/m.jpg')

    def test_reject_invalid_observation(self):
        item = dict(nome='Mouse', preco=10, link='https://example.com/item',
                    fonte_coleta='fixture', coletado_em=datetime.now(timezone.utc))
        for changes in ({'preco': float('nan')}, {'preco': 0}, {'preco': '1.001'},
                        {'coletado_em': datetime.now()},
                        {'coletado_em': datetime.now(timezone.utc)+timedelta(days=1)},
                        {'imagem_url': 'javascript:bad'}, {'fonte_coleta': ''}):
            with self.assertRaises(ValueError):
                normalize({**item, **changes})


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS') == '1', 'Exige ambiente isolado')
class CatalogIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = replace(Settings.environment(), prefix='hunter_test_catalog_'+secrets.token_hex(6))
        require_isolated(self.settings)
        self.conn = await asyncpg.connect(self.settings.database_url)
        self.tx = self.conn.transaction()
        await self.tx.start()
        self.addAsyncCleanup(self.cleanup)
        self.marker = 'CatalogTest'+secrets.token_hex(8)
        self.stamp = datetime.now(timezone.utc)-timedelta(hours=1)
        self.link = 'https://example.com/'+self.marker
        async def db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db] = db

    async def cleanup(self):
        backend.app.dependency_overrides.clear()
        await self.tx.rollback()
        await self.conn.close()

    def item(self, price=90, seconds=0, **extra):
        return dict(nome=self.marker, preco=price, link=self.link, imagem_url='https://cdn.example.com/current.jpg',
                    coletado_em=self.stamp+timedelta(seconds=seconds), fonte_coleta='fixture', **extra)

    async def search(self):
        status, data = await http('GET', '/buscar-produtos?'+urlencode({'nome': self.marker}))
        self.assertEqual(status, 200, data)
        return data['produtos']

    async def test_latest_not_cheapest_out_of_order_and_history(self):
        await self.conn.execute('INSERT INTO produtos_mercadolivre(nome,preco,link) VALUES($1,1,$2)', self.marker,self.link)
        await save_observations(self.conn, 'Mercado Livre', [self.item(150,20),self.item(50)])
        await save_observations(self.conn, 'Mercado Livre', [self.item(150,20)])
        products = await self.search()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['preco_atual'], 150)
        self.assertEqual(products[0]['imagem_url'], 'https://cdn.example.com/current.jpg')
        pid = products[0]['produto_id']
        status, history = await http('GET', f'/produtos/{pid}/historico?limite=1')
        self.assertEqual(status, 200)
        self.assertEqual(history['total'], 2)
        self.assertEqual(history['historico'][0]['preco'], 150)
        _, history = await http('GET', f'/produtos/{pid}/historico?limite=1&pagina=2')
        self.assertEqual(history['historico'][0]['preco'], 50)
        with self.assertRaises(ValueError):
            await save_observations(self.conn, 'Mercado Livre', [self.item(200,20)])

    async def test_unavailable_does_not_resurrect_legacy_offer(self):
        await self.conn.execute('INSERT INTO produtos_kabum(nome,preco,link) VALUES($1,1,$2)', self.marker,self.link)
        await save_observations(self.conn, 'KaBuM!', [self.item(), self.item(100,20,disponivel=False)])
        self.assertEqual(await self.search(), [])

    async def test_legacy_latest_row_and_unknown_date(self):
        for price, suffix in ((10, ' antigo'), (120, ' atual')):
            await self.conn.execute('INSERT INTO produtos_mercadolivre(nome,preco,link) VALUES($1,$2,$3)',self.marker+suffix,price,self.link)
        products = await self.search()
        self.assertEqual(len(products),1)
        self.assertEqual(products[0]['preco'],120)
        self.assertFalse(products[0]['preco_verificado'])
        self.assertIsNone(products[0]['coletado_em'])
        self.assertFalse(products[0]['historico_disponivel'])

    async def test_batch_rollback_and_identity_per_store(self):
        await save_observations(self.conn,'KaBuM!',[self.item()])
        await save_observations(self.conn,'Mercado Livre',[self.item(110)])
        self.assertEqual(len(await self.search()),2)
        with self.assertRaises(ValueError):
            await save_observations(self.conn,'KaBuM!',[self.item(70,10),self.item(40)])
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_price_observations o JOIN hunter_catalog_products p ON p.id=o.produto_id WHERE p.link=$1',self.link),2)

    async def test_new_price_rabbitmq_alert(self):
        user = await self.conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES('Teste',$1,'unused') RETURNING id",self.marker+'@example.com')
        alert = await self.conn.fetchval('INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES($1,$2,100) RETURNING id',user,self.marker)
        await save_observations(self.conn,'KaBuM!',[self.item(50),self.item(150,10)])
        await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1',alert),0)
        await save_observations(self.conn,'KaBuM!',[self.item(90,20)])
        await scan(self.conn)
        class Pool:
            @asynccontextmanager
            async def acquire(inner):
                yield self.conn
        async with connect(self.settings) as broker:
            await dispatch(self.conn,broker,self.settings)
            message = await broker.work.get(timeout=5)
            await handle_message(message,Pool(),broker,self.settings)
            # Mesma varredura nao repete o efeito.
            await scan(self.conn)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_events WHERE alerta_id=$1',alert),1)
        self.assertEqual(await self.conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE usuario_id=$1',user),1)

    async def test_missing_product_and_legacy_rollout(self):
        status, _ = await http('GET','/produtos/9223372036854775807/historico')
        self.assertEqual(status,404)
        from messaging.catalog import catalog_sql, CATALOGO
        from unittest.mock import AsyncMock
        conn=AsyncMock();conn.fetchval.return_value=False
        self.assertEqual(await catalog_sql(conn),CATALOGO)

    async def test_search_prioritizes_observed_before_pagination_without_hiding_legacy(self):
        # Mais de uma pagina de precos legados baixos reproduz o defeito real.
        for i in range(30):
            await self.conn.execute('INSERT INTO produtos_kabum(nome,preco,link) VALUES($1,$2,$3)',
                                    self.marker+' antigo '+str(i),float(i+1),self.link+'/legacy/'+str(i))
        await save_observations(self.conn,'KaBuM!',[self.item(900)])
        await save_observations(self.conn,'Mercado Livre',[{**self.item(800),'link':self.link+'/ml'}])
        query='/buscar-produtos?'+urlencode({'nome':self.marker,'limite':2})
        status,data=await http('GET',query)
        self.assertEqual(status,200)
        self.assertEqual(data['total'],32)
        self.assertTrue(data['priorizar_observados'])
        self.assertEqual([p['preco'] for p in data['produtos']],[800,900])
        self.assertTrue(all(p['imagem_url'] for p in data['produtos']))
        _,data=await http('GET',query+'&pagina=2')
        self.assertTrue(all(p['produto_id'] is None for p in data['produtos']))
        _,data=await http('GET',query+'&ordem=priceDesc')
        self.assertEqual([p['preco'] for p in data['produtos']],[900,800])
        _,data=await http('GET',query+'&priorizar_observados=false')
        self.assertEqual([p['preco'] for p in data['produtos']],[1,2])
        _,data=await http('GET',query+'&loja=KaBuM%21&preco_max=10')
        self.assertTrue(all(p['preco']<=10 for p in data['produtos']))
        self.assertEqual(data['total'],10)
