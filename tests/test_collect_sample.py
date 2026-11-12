"""Coleta pequena: limites e recusas de acesso, sem chamadas externas."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.collect_sample import collect_sample


class RobotsEnabledTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'HUNTER_RESPECT_ROBOTS': '1'})
        env.start()
        self.addCleanup(env.stop)


class ControlledCollectionTests(RobotsEnabledTests):
    def session(self, responses):
        session = Mock()
        session.headers = {}
        session.get.side_effect = responses
        return session

    def test_robots_disallow_stops_before_product(self):
        session = self.session([SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /')])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('KaBuM!'),([], 'robots_nao_permite'))
        self.assertEqual(session.get.call_count,1)

    def test_blocked_page_is_not_retried(self):
        session = self.session([SimpleNamespace(status_code=404,text=''),SimpleNamespace(status_code=403)])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('KaBuM!'),([], 'pagina_http_403'))
        self.assertEqual(session.get.call_count,2)
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_small_limit_and_real_fields(self):
        html = ''.join(f'''<article class="productCard"><a href="/produto/{i}">
            <span class="nameCard">Mouse {i}</span><span class="priceCard">R$ 90,00</span>
            <img src="https://cdn.example.com/{i}.jpg"></a></article>''' for i in range(4))
        session = self.session([SimpleNamespace(status_code=404,text=''),
                               SimpleNamespace(status_code=200,text=html,url='https://www.kabum.com.br/perifericos')])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            items,status=collect_sample('KaBuM!',2)
        self.assertEqual(status,'ok')
        self.assertEqual(len(items),2)
        self.assertTrue(all(item['imagem_url'] and item['coletado_em'].tzinfo for item in items))
        with self.assertRaises(ValueError):
            collect_sample('KaBuM!',100)

    def test_cross_domain_redirect_is_not_imported(self):
        session = self.session([SimpleNamespace(status_code=404,text=''),
                               SimpleNamespace(status_code=200,url='https://auth.example.com/login')])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre'),([], 'redirecionamento_fora_da_loja'))


class RedirectAndRobotsTests(RobotsEnabledTests):
    session = ControlledCollectionTests.session
    def test_authentication_redirect_is_classified_and_not_followed(self):
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=302,headers={'Location':'https://www.mercadolivre.com.br/gz/account-verification?go=private'})])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            rows,status=collect_sample('Mercado Livre')
        self.assertEqual((rows,status),([], 'redirecionamento_autenticacao'))
        self.assertEqual(session.get.call_count,2)

    def test_safe_product_canonical_redirect_is_followed(self):
        import json
        url='https://www.mercadolivre.com.br/mouse/p/MLB123'
        final='https://www.mercadolivre.com.br/mouse-canonico/p/MLB123'
        product={'@type':'Product','name':'FICTICIO Mouse','image':'https://images.example.invalid/model.jpg',
                 'offers':{'@type':'Offer','priceCurrency':'BRL','price':99.90,'url':final,'availability':'https://schema.org/InStock'}}
        html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=301,headers={'Location':final}),
            SimpleNamespace(status_code=200,text=html,url=final)])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            rows,status=collect_sample('Mercado Livre',1,url)
        self.assertEqual(status,'ok')
        self.assertEqual(rows[0]['link'],final)
        self.assertEqual(session.get.call_count,3)

    def test_new_host_requires_its_own_robots(self):
        url='https://www.mercadolivre.com.br/mouse/p/MLB123'
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=302,headers={'Location':'https://produto.mercadolivre.com.br/MLB-123-mouse-_JM'}),
            SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /')])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre',1,url),([], 'robots_nao_permite'))
        self.assertEqual(session.get.call_count,3)

    def test_old_pagination_wildcard_is_not_bypassed(self):
        session=self.session([SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /*_Desde_')])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre',1,'https://lista.mercadolivre.com.br/mouse_Desde_50'),([], 'robots_nao_permite'))
        self.assertEqual(session.get.call_count,1)

    def test_robots_specificity_and_allow_tie(self):
        from scraping.public_sources import robots_allows
        policy='User-agent: OtherBot\nDisallow: /\nUser-agent: *\nDisallow: /private*\nAllow: /private/public$'
        self.assertTrue(robots_allows(policy,'HunterCatalog','https://example.invalid/private/public'))
        self.assertFalse(robots_allows(policy,'HunterCatalog','https://example.invalid/private/other'))
        policy='User-agent: HunterCatalog\nDisallow:\nUser-agent: *\nDisallow: /'
        self.assertTrue(robots_allows(policy,'HunterCatalog','https://example.invalid/product'))

    def test_redirect_to_foreign_host_or_cycle_stops(self):
        url='https://www.mercadolivre.com.br/mouse/p/MLB123'
        for location,expected in [('https://attacker.example.invalid/mouse','redirecionamento_fora_da_loja'),(url,'redirecionamento_circular')]:
            session=self.session([SimpleNamespace(status_code=404,text=''),SimpleNamespace(status_code=302,headers={'Location':location})])
            with patch('scraping.public_sources.transport.Session',return_value=session):
                self.assertEqual(collect_sample('Mercado Livre',1,url),([],expected))
            self.assertEqual(session.get.call_count,2)


    def test_cloudflare_challenge_is_not_parsed_or_retried(self):
        url='https://www.pichau.com.br/teclado-teste'
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=200,text='<title>Pagina</title>',url=url,headers={'CF-Mitigated':'challenge'})])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('Pichau',1,url),([], 'desafio_de_acesso'))
        self.assertEqual(session.get.call_count,2)

    def test_amazon_robot_check_is_not_parsed_or_retried(self):
        url = 'https://www.amazon.com.br/s?k=teclado'
        session = self.session([
            SimpleNamespace(status_code=404, text=''),
            SimpleNamespace(status_code=200, url=url, headers={},
                text='<title>Amazon.com.br: Robot Check</title><form action="/errors/validateCaptcha"><input id="captchacharacters"></form>'),
        ])
        with patch('scraping.public_sources.transport.Session', return_value=session):
            result = collect_sample('Amazon Brasil', 1, url)
        self.assertEqual(result, ([], 'desafio_de_acesso'))
        self.assertEqual(session.get.call_count, 2)
        session.close.assert_called_once()

    def test_scrapling_transport_disables_redirects_and_retries(self):
        from scraping.transport import Session
        with patch('scraping.transport.FetcherSession') as fetcher:
            manager = fetcher.return_value
            client = manager.__enter__.return_value
            client.get.return_value = SimpleNamespace(status=403, headers={'location': 'https://example.com/next'}, body=b'blocked',
                                                      encoding='utf-8', url='https://example.com')
            session = Session()
            response = session.get('https://example.com', timeout=(1, 2), allow_redirects=False)
            self.assertEqual(response.headers['Location'], 'https://example.com/next')
            kwargs = fetcher.call_args.kwargs
            self.assertEqual(kwargs['retries'], 1)
            self.assertFalse(kwargs['follow_redirects'])
            self.assertTrue(kwargs['stealthy_headers'])
            self.assertEqual(kwargs['impersonate'], 'chrome')
            self.assertFalse(client.get.call_args.kwargs['follow_redirects'])
            session.close()

    def test_robots_http_403_is_not_retried(self):
        session=self.session([SimpleNamespace(status_code=403,headers={})])
        with patch('scraping.public_sources.transport.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre'),([], 'robots_http_403'))
        self.assertEqual(session.get.call_count,1)


class DefaultRobotsPolicyTests(unittest.TestCase):
    def test_default_does_not_request_robots(self):
        from scraping.public_sources import fetch_public_html
        session = Mock()
        session.headers = {}
        url = 'https://www.kabum.com.br/perifericos'
        session.get.return_value = SimpleNamespace(status_code=200, text='<title>Catalogo</title>', url=url, headers={})
        with patch.dict(os.environ, {}, clear=True), patch('scraping.public_sources.transport.Session', return_value=session):
            self.assertEqual(fetch_public_html('KaBuM!', url)[2], 'ok')
        session.get.assert_called_once_with(url, timeout=(10,25), allow_redirects=False)
        session.close.assert_called_once()

class BrowserTransportTests(unittest.TestCase):
    def test_browser_renders_without_http_useragent_or_challenge_solver(self):
        from scraping.transport import BrowserSession
        with patch('scraping.transport.StealthySession') as factory:
            client = factory.return_value.__enter__.return_value
            client.fetch.return_value = SimpleNamespace(status=200, headers={}, body=b'<h1>Mouse</h1>', encoding='utf-8', url='https://site.fastshop.com.br/test')
            validate = Mock()
            session = BrowserSession(validate)
            session.headers['User-Agent'] = 'HunterCatalog'
            try:
                result = session.get('https://site.fastshop.com.br/test', timeout=(10,25))
                self.assertEqual(result.status_code, 200)
                self.assertEqual(client.fetch.call_args.kwargs['timeout'], 25000)
                self.assertFalse(factory.call_args.kwargs['solve_cloudflare'])
                self.assertEqual(factory.call_args.kwargs['retries'], 1)
                self.assertNotIn('useragent', factory.call_args.kwargs)
                self.assertNotIn('extra_headers', client.fetch.call_args.kwargs)
            finally:
                session.close()
            factory.return_value.__exit__.assert_called_once()

    def test_browser_blocks_navigation_outside_validator(self):
        from scraping.transport import BrowserSession
        with patch('scraping.transport.StealthySession') as factory:
            client = factory.return_value.__enter__.return_value
            def fetch(url, **kwargs):
                page = Mock()
                kwargs['page_setup'](page)
                guard = page.route.call_args.args[1]
                route = Mock()
                route.request.url = 'https://example.invalid/account'
                route.request.frame = page.main_frame
                route.request.is_navigation_request.return_value = True
                guard(route)
                route.abort.assert_called_once()
                route.continue_.assert_not_called()
                return SimpleNamespace(status=200, headers={}, body=b'', encoding='utf-8', url=url)
            client.fetch.side_effect = fetch
            session = BrowserSession(Mock(side_effect=ValueError('invalid')))
            try:
                result = session.get('https://site.fastshop.com.br/test')
                self.assertEqual(result.status_code,302)
                self.assertEqual(result.headers['Location'],'https://example.invalid/account')
            finally:
                session.close()

    def test_gk_block_is_classified_without_followup(self):
        from scraping.public_sources import fetch_public_html
        session = Mock()
        session.headers = {}
        session.get.return_value = SimpleNamespace(status_code=423,text='<title>Loja bloqueada</title>',headers={})
        with patch.dict(os.environ, {'HUNTER_RESPECT_ROBOTS':'0'}), patch('scraping.public_sources.transport.BrowserSession',return_value=session):
            result=fetch_public_html('GK InfoStore','https://www.gkinfostore.com.br',browser=True)
        self.assertEqual(result[2],'loja_indisponivel')
        session.get.assert_called_once()
        session.close.assert_called_once()

class BrowserSessionReuseTests(unittest.TestCase):
    def test_amazon_visits_home_once_and_keeps_same_session(self):
        from scraping.transport import BrowserSession
        with patch('scraping.transport.StealthySession') as factory:
            client = factory.return_value.__enter__.return_value
            client.fetch.return_value = SimpleNamespace(status=200,headers={},body=b'ok',encoding='utf-8',url='https://www.amazon.com.br/s?k=mouse')
            session = BrowserSession(Mock(), start_url='https://www.amazon.com.br/')
            try:
                session.get('https://www.amazon.com.br/s?k=mouse')
                session.get('https://www.amazon.com.br/s?k=teclado')
                urls = [call.args[0] for call in client.fetch.call_args_list]
                self.assertEqual(urls, ['https://www.amazon.com.br/', 'https://www.amazon.com.br/s?k=mouse', 'https://www.amazon.com.br/s?k=teclado'])
                factory.assert_called_once()
            finally:
                session.close()

    def test_borrowed_session_is_closed_by_owner(self):
        from scraping.public_sources import fetch_public_html
        session=Mock();session.headers={}
        url='https://site.fastshop.com.br/informatica-e-games/periferico'
        session.get.return_value=SimpleNamespace(status_code=200,headers={},text='<title>Perifericos</title>',url=url)
        with patch.dict(os.environ, {'HUNTER_RESPECT_ROBOTS':'0'}):
            self.assertEqual(fetch_public_html('Fast Shop',url,listing=True,browser=True,session=session)[2],'ok')
        session.close.assert_not_called()
