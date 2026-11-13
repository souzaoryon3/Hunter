"""Cotas, duplicatas, paginacao e interrupcoes da coleta."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from scraping.peripherals import CATEGORIES, collect_peripherals, next_page, category_url
from scraping.public_sources import listing_url


def product(index):
    return dict(nome='Mouse Produto ' + str(index), preco='99.90',
                link=f'https://www.kabum.com.br/produto/{index}/teste',
                coletado_em=datetime.now(timezone.utc), fonte_coleta='fixture',
                fonte_url='https://www.kabum.com.br/busca/mouse')


class PeripheralsTests(unittest.TestCase):
    def test_fifty_products_spread_across_categories(self):
        def fetch(store, url, *args, **kwargs):
            return url, url, 'ok', {}
        def parse(html, url):
            offset = CATEGORIES.index(url.rsplit('/', 1)[-1]) * 10
            return [dict(product(offset + i), nome=url.rsplit('/', 1)[-1].replace('-', ' ') + ' Produto ' + str(i)) for i in range(10)]
        with patch('scraping.peripherals.fetch_public_html', side_effect=fetch), patch.dict(
                'scraping.peripherals.STORES', {'KaBuM!': ('https://www.kabum.com.br/perifericos', parse)}):
            result = collect_peripherals('KaBuM!', request_delay=0)
        self.assertEqual(result['produtos'], 50)
        self.assertEqual(result['categorias'], dict.fromkeys(CATEGORIES, 5))
        self.assertEqual(len({p['link'] for p in result['ofertas']}), 50)

    def test_more_than_three_pages_without_duplicates(self):
        def fetch(store, url, *args, **kwargs):
            from urllib.parse import parse_qs, urlsplit
            number = int(parse_qs(urlsplit(url).query).get('page_number', ['1'])[0])
            return f'<a rel="next" href="?page_number={number+1}">next</a>', url, 'ok', {}
        def parse(html, url):
            import re
            number = int(re.search(r'page_number=(\d+)', html)[1]) - 1
            return [product(1), product(number)]
        with patch('scraping.peripherals.fetch_public_html', side_effect=fetch) as fetcher, patch.dict(
                'scraping.peripherals.STORES', {'KaBuM!': ('https://www.kabum.com.br/perifericos', parse)}):
            result = collect_peripherals('KaBuM!', max_pages=5, request_delay=0)
        self.assertEqual(fetcher.call_count, 50)
        self.assertEqual(result['produtos'], 5)

    def test_block_stops_store(self):
        with patch('scraping.peripherals.fetch_public_html', return_value=(None, '', 'pagina_http_403', {})) as fetch:
            result = collect_peripherals('KaBuM!', request_delay=0)
        fetch.assert_called_once()
        self.assertEqual(result['status'], 'pagina_http_403')

    def test_listing_urls_and_pagination(self):
        for store in ('KaBuM!', 'Pichau', 'Amazon Brasil', 'Magalu', 'Fast Shop', 'GK InfoStore', 'TerabyteShop', 'Mercado Livre'):
            self.assertEqual(listing_url(store, category_url(store, 'mouse')), category_url(store, 'mouse'))
        url = 'https://www.pichau.com.br/perifericos/mouse'
        self.assertEqual(next_page('Pichau', '<a rel="next" href="?page=4">next</a>', url), url + '?page=4')
        self.assertIsNone(next_page('Pichau', '<a rel="next" href="https://example.invalid/?page=4">next</a>', url))
        for suffix in ('?page=0', '?page=2&page=3', '?token=secret'):
            with self.assertRaises(ValueError):
                listing_url('Pichau', url + suffix)


class StoreMarkupTests(unittest.TestCase):
    def test_pichau_discount_percent_in_separate_span(self):
        from scraping.buscar_produtospichau import parse_html
        html = '<a href="/mouse-teste"><h2>Mouse Teste</h2><del>R$ 199.90</del>por <b>R$ 107.99</b><span>&Agrave; vista</span><span>15</span>% de desconto no PIX <b>R$ 127.05</b> Em at&eacute; 12x</a>'
        rows = parse_html(html, 'https://www.pichau.com.br/perifericos/mouse')
        self.assertEqual(str(rows[0]['preco']), '107.99')

    def test_terabyte_pix_excludes_old_price_and_installment(self):
        from scraping.tech_stores import parse_html
        html = '<div class="product-item__box"><a class="product-item__name" href="/produto/123/mouse"><h2>Mouse Teste</h2></a><del>R$ 199,90</del><div class="product-item__new-price"><span>R$ 99,90</span><small>&Agrave; vista no Pix</small></div><div>12x de R$ 10,00</div></div>'
        rows = parse_html('TerabyteShop', html, 'https://www.terabyteshop.com.br/perifericos/mouse')
        self.assertEqual(rows[0]['preco'], '99.90')
        self.assertEqual(rows[0]['pagamento'], 'Pix')
        ambiguous = html.replace('<span>R$ 99,90</span>', '<span>R$ 99,90</span><span>R$ 89,90</span>')
        self.assertEqual(parse_html('TerabyteShop', ambiguous, 'https://www.terabyteshop.com.br/perifericos/mouse'), [])

    def test_category_matching_rejects_unrelated_products(self):
        from scraping.peripherals import matches_category
        self.assertFalse(matches_category('Mousepad Grande', 'mouse'))
        self.assertFalse(matches_category('Teclado Gamer', 'monitor'))
        self.assertTrue(matches_category('Caixa de Som USB', 'caixa-de-som'))

class BrowserStoreTests(unittest.TestCase):
    def test_fastshop_uses_visible_cash_price_instead_of_prime_or_installment(self):
        from scraping.tech_stores import parse_html
        html = '''<article data-fs-product-card="true"><h2 data-fs-product-card-title><a href="/mouse-logitech/p"><p>Mouse Logitech</p></a></h2>
        <div class="ValuePrimePrice">R$ 49,00</div><div class="Installments"><p><span data-testid="price-value">R$ 90,00</span> &agrave; vista ou em ate 12x <span data-testid="price-value">R$ 10,00</span> no cartao</p></div></article>'''
        rows = parse_html('Fast Shop', html, 'https://site.fastshop.com.br/informatica-e-games/periferico')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['preco'], '90.00')
        self.assertEqual(rows[0]['nome'], 'Mouse Logitech')
        self.assertEqual(rows[0]['fonte_coleta'], 'scrapling_browser_card')
        prime_only = html.replace('class="Installments"', 'class="Prime"')
        self.assertEqual(parse_html('Fast Shop', prime_only, 'https://site.fastshop.com.br/informatica-e-games/periferico'), [])

    def test_fastshop_pagination_preserves_real_category_path(self):
        url = 'https://site.fastshop.com.br/informatica-e-games/periferico'
        html = '<a href="/[...slug]?page=1" aria-label="Pr&oacute;xima p&aacute;gina">&gt;</a>'
        self.assertEqual(next_page('Fast Shop', html, url), url + '?page=1')

    def test_503_retries_once_but_403_does_not(self):
        with patch('scraping.peripherals.fetch_public_html', return_value=(None, '', 'pagina_http_503', {})) as fetch, patch('time.sleep') as sleep:
            result = collect_peripherals('Amazon Brasil', request_delay=0)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(5)
        self.assertEqual(result['status'], 'pagina_http_503')
        self.assertEqual(result['paginas'][0]['repeticoes_503'], 1)
        with patch('scraping.peripherals.fetch_public_html', return_value=(None, '', 'pagina_http_403', {})) as fetch:
            result = collect_peripherals('Magalu', request_delay=0)
        fetch.assert_called_once()
        self.assertEqual(result['status'], 'pagina_http_403')

    def test_provider_block_stops_store(self):
        with patch('scraping.peripherals.fetch_public_html', return_value=(None, '', 'loja_indisponivel', {'http_status':423})) as fetch:
            result = collect_peripherals('GK InfoStore', request_delay=0)
        fetch.assert_called_once()
        self.assertEqual(result['status'], 'loja_indisponivel')

class AmazonMarkupTests(unittest.TestCase):
    def test_amazon_canonical_identity_ignores_tracking_and_old_price(self):
        from scraping.tech_stores import parse_html
        html = '''<div data-component-type="s-search-result" data-asin="B01JPOLKDW"><h2><span>Mouse Logitech</span></h2>
        <a href="/Logitech/dp/B01JPOLKDW/ref=sr_1?tag=tracking">Mouse</a>
        <span class="a-price" data-a-color="base"><span class="a-offscreen">R$ 69,90</span></span>
        <span class="a-price a-text-price" data-a-color="base"><span class="a-offscreen">R$ 109,90</span></span>
        <img class="s-image" src="https://images.example.invalid/mouse.jpg"></div>'''
        rows = parse_html('Amazon Brasil', html, 'https://www.amazon.com.br/s')
        self.assertEqual(rows[0]['preco'], '69.90')
        self.assertEqual(rows[0]['link'], 'https://www.amazon.com.br/dp/B01JPOLKDW')
        self.assertEqual(rows[0]['imagem_url'], 'https://images.example.invalid/mouse.jpg')
        ambiguous = html.replace('</h2>', '</h2><span class="a-price" data-a-color="base"><span class="a-offscreen">R$ 50,00</span></span>')
        self.assertEqual(parse_html('Amazon Brasil', ambiguous, 'https://www.amazon.com.br/s'), [])
        missing_link = html.replace('/Logitech/dp/B01JPOLKDW/ref=sr_1?tag=tracking', '/not-a-product')
        self.assertEqual(parse_html('Amazon Brasil', missing_link, 'https://www.amazon.com.br/s'), [])

    def test_amazon_sponsored_link_requires_matching_observed_asin(self):
        from scraping.tech_stores import parse_html
        html = '''<div data-component-type="s-search-result" data-asin="B01JPOLKDW"><h2>Mouse Logitech</h2>
        <a href="/sspa/click?url=%2FLogitech%2Fdp%2FB01JPOLKDW%2Fref%3Dsr">Mouse</a>
        <span class="a-price" data-a-color="base"><span class="a-offscreen">R$ 69,90</span></span></div>'''
        self.assertEqual(len(parse_html('Amazon Brasil', html, 'https://www.amazon.com.br/s')), 1)
        mismatch = html.replace('%2FB01JPOLKDW%2F', '%2FB000000000%2F')
        self.assertEqual(parse_html('Amazon Brasil', mismatch, 'https://www.amazon.com.br/s'), [])

class BrowserCollectionLifecycleTests(unittest.TestCase):
    def test_collection_reuses_pages_and_always_closes_browser(self):
        with patch('scraping.peripherals.transport.BrowserSession') as factory, patch('scraping.peripherals.fetch_public_html', return_value=('<title>Empty</title>', 'https://site.fastshop.com.br/informatica-e-games/periferico', 'ok', {})) as fetch:
            result = collect_peripherals('Fast Shop', max_pages=1, request_delay=0)
        self.assertEqual(fetch.call_count,5)
        self.assertEqual(sum(row['cache'] for row in result['paginas']),5)
        self.assertTrue(all(call.kwargs['session'] is factory.return_value for call in fetch.call_args_list))
        factory.return_value.close.assert_called_once()
