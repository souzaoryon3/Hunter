"""Parser, bloqueios e armazenamento Pichau; integração sempre com rollback."""
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault('JWT_SECRET_KEY', secrets.token_hex(32))
import asyncpg
from config.settings import test_database_url
from scraping.buscar_produtospichau import collect, load_snapshot, money, parse_html, public_url, save, validate
from test_api import http
import app as backend

URL = 'https://www.pichau.com.br/teclado-teste'


class ParserTests(unittest.TestCase):
    def test_prices_and_cards(self):
        for value in ('R$ 1.429,99', '1,429.99', '1429.99'):
            self.assertEqual(money(value), Decimal('1429.99'))
        for value in ('nan', 'inf', '-1', '0', '12.345'):
            with self.assertRaises(ValueError):
                money(value)
        html = '''<title>Teclados</title><a href="/teclado-teste"><span>Frete Grátis: Sul e Sudeste</span>
        <h2>Teclado Teste</h2>de R$ 354,81 por R$ 269,99 À vista15% de desconto no PIX
        R$ 317,64 Em até 12x de R$ 26,47 Sem juros no cartão</a>'''
        product = parse_html(html, 'https://www.pichau.com.br/perifericos/teclado')[0]
        self.assertEqual(product['preco'], Decimal('269.99'))
        self.assertEqual(product['preco_cartao'], Decimal('317.64'))
        self.assertEqual(product['link'], URL)
        self.assertIsNone(product['frete_gratis'])
        self.assertIn('Sul e Sudeste', product['frete_observacao'])

    def test_product_page_and_empty(self):
        product = parse_html('<h1>Teclado Teste</h1>de R$ 164,69 por: à vista R$ 119,99 no PIX com 15% desconto R$ 141,16 em até 12x de R$ 11,76 sem juros no cartão', URL)[0]
        self.assertEqual(product['preco'], Decimal('119.99'))
        self.assertEqual(product['preco_cartao'], Decimal('141.16'))
        for html in ('<title>Just a moment...</title>', '<title>Site em Manutenção</title>', '<h1>Produto</h1>R$ 5,00 em parcelas'):
            with self.assertRaises(ValueError):
                parse_html(html, URL)

    def test_rejects_unsafe_urls_and_conditional_shipping(self):
        for url in ('https://example.com/a', 'https://www.pichau.com.br/api/a', URL + '?page=2', 'http://www.pichau.com.br/a'):
            with self.assertRaises(ValueError):
                public_url(url)
        with self.assertRaises(ValueError):
            validate(dict(nome='Teclado', link=URL, preco=10, frete_gratis=True,
                          frete_observacao='Sul e Sudeste'), 'html_publico', datetime.now(timezone.utc))
        products = load_snapshot('scraping/dados/pichau_captura_inicial.json')
        self.assertEqual(len(products), 6)
        self.assertTrue(all(p['fonte_coleta'] == 'captura_publica' and p['frete_gratis'] is None for p in products))

    def test_jsonld_product_image_and_aggregate_rejection(self):
        import json
        product={'@type':'Product','name':'FICTICIO Teclado','image':{'url':'https://images.example.invalid/keyboard.jpg'},
                 'offers':{'@type':'Offer','priceCurrency':'BRL','price':'119.99','availability':'https://schema.org/InStock'}}
        html='<img src="https://images.example.invalid/logo.jpg"><script type="application/ld+json">'+json.dumps(product)+'</script>'
        row=parse_html(html,URL)[0]
        self.assertEqual(row['imagem_url'],'https://images.example.invalid/keyboard.jpg')
        self.assertEqual(row['preco'],Decimal('119.99'))
        product['offers']['@type']='AggregateOffer'
        html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        with self.assertRaises(ValueError):parse_html(html,URL)

    def test_main_product_does_not_become_recommendation_or_logo(self):
        html='<meta property="og:image" content="https://images.example.invalid/correct.jpg"><img src="https://images.example.invalid/logo.jpg"><main><h1>Teclado principal</h1>por R$ 119,99 no PIX <a href="/mouse-outro"><h2>Mouse recomendado</h2>por R$ 1,00 no PIX</a></main>'
        row=parse_html(html,URL)[0]
        self.assertEqual(row['nome'],'Teclado principal')
        self.assertEqual(row['preco'],Decimal('119.99'))
        self.assertEqual(row['imagem_url'],'https://images.example.invalid/correct.jpg')

    def test_invalid_anchor_does_not_abort_valid_listing(self):
        html='<a href="/account/private"><h2>Conta</h2></a><a href="/teclado-teste"><h2>Teclado</h2>por R$ 119,99 no PIX<img src="https://images.example.invalid/k.jpg"></a>'
        self.assertEqual(len(parse_html(html,'https://www.pichau.com.br/perifericos/teclado')),1)

    def test_collect_uses_safe_canonical_redirect_and_closes_session(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        session=Mock();session.headers={}
        session.get.side_effect=[SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=301,headers={'Location':URL}),
            SimpleNamespace(status_code=200,url=URL,text='<h1>Teclado teste</h1>por R$ 119,99 no PIX')]
        with patch('scraping.buscar_produtospichau.requests.Session',return_value=session),patch('time.sleep'):
            self.assertEqual(collect([URL+'/'])[0]['link'],URL)
        self.assertEqual(session.get.call_count,3)
        session.close.assert_called_once()

    def test_jsonld_listing_never_uses_homepage_as_missing_product_url(self):
        import json
        product={'@type':'Product','name':'Teclado teste','image':'https://images.example.invalid/k.jpg',
                 'offers':{'@type':'Offer','priceCurrency':'BRL','price':100,'availability':'https://schema.org/InStock'}}
        html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        with self.assertRaises(ValueError):parse_html(html,'https://www.pichau.com.br/perifericos/teclado')

    def test_http_block_does_not_retry(self):
        with patch('scraping.buscar_produtospichau.requests.Session') as session:
            session.return_value.get.return_value.status_code = 403
            with self.assertRaisesRegex(ValueError, 'HTTP 403'):
                collect([URL])
            self.assertEqual(session.return_value.get.call_count, 1)


@unittest.skipUnless(os.environ.get('HUNTER_TEST_DATABASE_URL'), 'Banco não configurado')
class PichauDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_filter_and_rollback(self):
        conn = await asyncpg.connect(test_database_url())
        tx = conn.transaction()
        await tx.start()
        marker = 'HunterPichauTest' + secrets.token_hex(8)
        link = 'https://www.pichau.com.br/' + marker.lower()
        async def test_db():
            yield conn
        backend.app.dependency_overrides[backend.get_db] = test_db
        try:
            now = datetime.now(timezone.utc) - timedelta(seconds=10)
            product = validate(dict(nome=marker, preco='119.99', link=link, preco_cartao='141.16', pagamento='Pix'), 'html_publico', now)
            await save(conn, [product, product])
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM produtos_pichau WHERE link=$1', link), 1)
            updated = {**product, 'preco': Decimal('109.99'), 'coletado_em': now + timedelta(seconds=1)}
            await save(conn, [updated])
            await save(conn, [product])  # Uma captura mais antiga não reverte o preço.
            status, data = await http('GET', '/buscar-produtos?nome=' + marker + '&loja=Pichau')
            self.assertEqual(status, 200)
            self.assertEqual(data['total'], 1)
            self.assertEqual(data['produtos'][0]['preco'], 109.99)
            self.assertEqual(data['produtos'][0]['pagamento'], 'Pix')
            self.assertIsNone(data['produtos'][0]['frete_gratis'])
            _, data = await http('GET', '/buscar-produtos?nome=' + marker + '&frete_gratis=true')
            self.assertEqual(data['total'], 0)
            await save(conn, [{**updated, 'frete_gratis': True, 'frete_observacao': 'Frete grátis', 'coletado_em': now + timedelta(seconds=2)}])
            _, data = await http('GET', '/buscar-produtos?nome=' + marker + '&frete_gratis=true')
            self.assertEqual(data['total'], 1)
            await save(conn, [{**updated, 'disponivel': False, 'coletado_em': now + timedelta(seconds=3)}])
            _, data = await http('GET', '/buscar-produtos?nome=' + marker)
            self.assertEqual(data['total'], 0)
        finally:
            backend.app.dependency_overrides.clear()
            await tx.rollback()
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM produtos_pichau WHERE link=$1', link), 0)
            await conn.close()
