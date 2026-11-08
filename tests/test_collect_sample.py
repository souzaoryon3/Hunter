"""Coleta pequena: limites e recusas de acesso, sem chamadas externas."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.collect_sample import collect_sample


class ControlledCollectionTests(unittest.TestCase):
    def session(self, responses):
        session = Mock()
        session.headers = {}
        session.get.side_effect = responses
        return session

    def test_robots_disallow_stops_before_product(self):
        session = self.session([SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /')])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('KaBuM!'),([], 'robots_nao_permite'))
        self.assertEqual(session.get.call_count,1)

    def test_blocked_page_is_not_retried(self):
        session = self.session([SimpleNamespace(status_code=404,text=''),SimpleNamespace(status_code=403)])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('KaBuM!'),([], 'pagina_http_403'))
        self.assertEqual(session.get.call_count,2)
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_small_limit_and_real_fields(self):
        html = ''.join(f'''<article class="productCard"><a href="/produto/{i}">
            <span class="nameCard">Mouse {i}</span><span class="priceCard">R$ 90,00</span>
            <img src="https://cdn.example.com/{i}.jpg"></a></article>''' for i in range(4))
        session = self.session([SimpleNamespace(status_code=404,text=''),
                               SimpleNamespace(status_code=200,text=html,url='https://www.kabum.com.br/perifericos')])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            items,status=collect_sample('KaBuM!',2)
        self.assertEqual(status,'ok')
        self.assertEqual(len(items),2)
        self.assertTrue(all(item['imagem_url'] and item['coletado_em'].tzinfo for item in items))
        with self.assertRaises(ValueError):
            collect_sample('KaBuM!',100)

    def test_cross_domain_redirect_is_not_imported(self):
        session = self.session([SimpleNamespace(status_code=404,text=''),
                               SimpleNamespace(status_code=200,url='https://auth.example.com/login')])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre'),([], 'redirecionamento_fora_da_loja'))


class RedirectAndRobotsTests(unittest.TestCase):
    session = ControlledCollectionTests.session
    def test_authentication_redirect_is_classified_and_not_followed(self):
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=302,headers={'Location':'https://www.mercadolivre.com.br/gz/account-verification?go=private'})])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
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
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            rows,status=collect_sample('Mercado Livre',1,url)
        self.assertEqual(status,'ok')
        self.assertEqual(rows[0]['link'],final)
        self.assertEqual(session.get.call_count,3)

    def test_new_host_requires_its_own_robots(self):
        url='https://www.mercadolivre.com.br/mouse/p/MLB123'
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=302,headers={'Location':'https://produto.mercadolivre.com.br/MLB-123-mouse-_JM'}),
            SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /')])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre',1,url),([], 'robots_nao_permite'))
        self.assertEqual(session.get.call_count,3)

    def test_old_pagination_wildcard_is_not_bypassed(self):
        session=self.session([SimpleNamespace(status_code=200,text='User-agent: *\nDisallow: /*_Desde_')])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
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
            with patch('scripts.collect_sample.requests.Session',return_value=session):
                self.assertEqual(collect_sample('Mercado Livre',1,url),([],expected))
            self.assertEqual(session.get.call_count,2)


    def test_cloudflare_challenge_is_not_parsed_or_retried(self):
        url='https://www.pichau.com.br/teclado-teste'
        session=self.session([SimpleNamespace(status_code=404,text=''),
            SimpleNamespace(status_code=200,text='<title>Pagina</title>',url=url,headers={'CF-Mitigated':'challenge'})])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('Pichau',1,url),([], 'desafio_de_acesso'))
        self.assertEqual(session.get.call_count,2)

    def test_robots_http_403_is_not_retried(self):
        session=self.session([SimpleNamespace(status_code=403,headers={})])
        with patch('scripts.collect_sample.requests.Session',return_value=session):
            self.assertEqual(collect_sample('Mercado Livre'),([], 'robots_http_403'))
        self.assertEqual(session.get.call_count,1)
