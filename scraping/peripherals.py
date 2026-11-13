"""Coleta multiloja de perifericos por categoria e paginacao publica."""
import re
import unicodedata
from collections import Counter
from urllib.parse import urlsplit, urljoin
from scrapling import Selector
from scraping.catalog_store import normalize
from scraping import transport
from scraping.public_sources import STORES, fetch_public_html, listing_url

CATEGORIES = ('mouse', 'teclado', 'monitor', 'fone', 'headset', 'webcam',
              'microfone', 'caixa-de-som', 'mousepad', 'controle')
BROWSER_STORES = frozenset(('Fast Shop', 'Amazon Brasil', 'Magalu', 'GK InfoStore'))


def category_url(store, category):
    roots = {
        'KaBuM!': 'https://www.kabum.com.br/busca/',
        'Mercado Livre': 'https://lista.mercadolivre.com.br/',
        'Pichau': 'https://www.pichau.com.br/perifericos/',
        'TerabyteShop': 'https://www.terabyteshop.com.br/perifericos/',
        'Amazon Brasil': 'https://www.amazon.com.br/s?k=',
        'Magalu': 'https://www.magazineluiza.com.br/busca/',
        'Fast Shop': 'https://site.fastshop.com.br/busca?q=',
        'GK InfoStore': 'https://www.gkinfostore.com.br/busca?q=',
    }
    if store == 'TerabyteShop':
        paths = {'monitor': '/monitores', 'fone': '/perifericos/fone-de-ouvido',
                 'headset': '/perifericos/fone-de-ouvido', 'controle': '/perifericos/joystick-e-controle',
                 'mousepad': '/perifericos'}
        if category in paths:
            return 'https://www.terabyteshop.com.br' + paths[category]
    if store == 'Fast Shop':
        paths = {'monitor': '/informatica-e-games/monitor', 'fone': '/audio/fone-de-ouvido',
                 'headset': '/audio/fone-de-ouvido', 'caixa-de-som': '/audio/caixa-de-som',
                 'controle': '/informatica-e-games/console-jogo-e-acessorio'}
        return 'https://site.fastshop.com.br' + paths.get(category, '/informatica-e-games/periferico')
    if store == 'Pichau' and category == 'monitor':
        return 'https://www.pichau.com.br/monitores'
    return roots[store] + category


def matches_category(name, category):
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    patterns = {'mouse': r'\bmouse\b(?!\s*pad)', 'teclado': r'\bteclado\b',
                'monitor': r'\bmonitor\b', 'fone': r'\b(fone|headphone|earphone|earbud)\w*',
                'headset': r'\bheadset\b', 'webcam': r'\bwebcam\b',
                'microfone': r'\bmicrofone\b', 'caixa-de-som': r'\bcaixa[s]? (?:de )?som\b|\bspeaker\w*',
                'mousepad': r'\bmouse\s*pad\b', 'controle': r'\b(controle|joystick|gamepad)\b'}
    return bool(re.search(patterns[category], text))


def next_page(store, html, url):
    page = Selector(html, url=url)
    candidates = page.css('a[rel="next"]::attr(href), link[rel="next"]::attr(href)').getall()
    for anchor in page.css('a[href]'):
        label = ' '.join((anchor.get_all_text(), anchor.attrib.get('aria-label', ''))).lower()
        if any(word in label for word in ('próxima', 'proxima', 'seguinte', 'next')):
            candidates.append(anchor.attrib['href'])
    for href in candidates:
        target = urljoin(url, href)
        if (store == 'Fast Shop' and urlsplit(target).netloc == urlsplit(url).netloc
                and urlsplit(target).path == '/[...slug]'):
            target = urlsplit(url)._replace(query=urlsplit(target).query).geturl()
        try:
            listing_url(store, target)
        except ValueError:
            continue
        source, dest = urlsplit(url), urlsplit(target)
        if (source.netloc == dest.netloc and target != url
                and source.path.split('_Desde_')[0].rstrip('/') == dest.path.split('_Desde_')[0].rstrip('/')):
            return target
    return None


def collect_peripherals(store, target=50, max_pages=5, request_delay=3, progress=None, browser=None):
    if store not in STORES or not 1 <= target <= 50 or not 1 <= max_pages <= 10:
        raise ValueError('Loja valida, 1..50 produtos e 1..10 paginas por categoria obrigatorios')
    use_browser = store in BROWSER_STORES if browser is None else browser
    session = None
    try:
        if use_browser:
            session = transport.BrowserSession(lambda value: listing_url(store, value),
                                               start_url='https://www.amazon.com.br/' if store == 'Amazon Brasil' else None)
        return _collect_peripherals(store, target, max_pages, request_delay, progress, use_browser, session)
    finally:
        if session is not None:
            session.close()


def _collect_peripherals(store, target, max_pages, request_delay, progress, use_browser, session):
    unique, requests, counts, reserve = {}, [], Counter(), {}
    cache = {}
    states = {c: {'url': category_url(store, c), 'seen': set()} for c in CATEGORIES}
    quota, remainder = divmod(target, len(CATEGORIES))
    quotas = {c: quota + (i < remainder) for i, c in enumerate(CATEGORIES)}
    stopped = None
    for _ in range(max_pages):
        for category, state in states.items():
            url = state['url']
            if not url or url in state['seen'] or counts[category] >= quotas[category]:
                continue
            state['seen'].add(url)
            cached = url in cache
            if cached:
                html, final, status, meta = cache[url]
                meta = dict(meta)
            else:
                html, final, status, meta = fetch_public_html(store, url, request_delay, listing=True,
                                                            browser=use_browser, session=session)
            if use_browser and status == 'pagina_http_503':
                # Uma unica repeticao para falha transitoria; nunca repete bloqueios.
                import time
                delay = str(meta.get('retry_after') or '5')
                time.sleep(min(30, max(5, int(delay))) if delay.isdigit() else 5)
                html, final, status, meta = fetch_public_html(store, url, request_delay, listing=True,
                                                            browser=True, session=session)
                meta['repeticoes_503'] = 1
            cache[url] = html, final, status, dict(meta)
            row = dict(categoria=category, url=url, status=status, cache=cached, **meta)
            requests.append(row)
            if progress:
                progress(row)
            if status != 'ok':
                state['url'] = None
                if (status.startswith(('robots_http_', 'rede_')) or status in ('desafio_de_acesso', 'loja_indisponivel')
                        or status in ('pagina_http_401', 'pagina_http_403', 'pagina_http_423', 'pagina_http_429',
                                      'pagina_http_500', 'pagina_http_502', 'pagina_http_503',
                                      'redirecionamento_autenticacao')):
                    stopped = status
                    break
                continue
            base = urlsplit(final)._replace(query='').geturl()
            try:
                for product in STORES[store][1](html, base):
                    try:
                        product = normalize(product)
                    except ValueError:
                        continue
                    if not matches_category(product['nome'], category):
                        continue
                    product.update(fonte_url=final, categoria=category)
                    link = product['link']
                    if link in unique:
                        continue
                    if counts[category] < quotas[category]:
                        unique[link] = product
                        reserve.pop(link, None)
                        counts[category] += 1
                    else:
                        reserve.setdefault(link, product)
            except ValueError:
                row['status'] = 'markup_ou_pagina_recusada'
            state['url'] = next_page(store, html, final)
        if stopped or len(unique) >= target:
            break
    while reserve and len(unique) < target:
        category = min({item['categoria'] for item in reserve.values()},
                       key=lambda c: (counts[c], CATEGORIES.index(c)))
        link = next(link for link, item in reserve.items() if item['categoria'] == category)
        product = reserve.pop(link)
        if link not in unique:
            unique[link] = product
            counts[category] += 1
    return dict(loja=store, meta=target, produtos=len(unique), categorias=dict(counts),
                transporte='browser' if use_browser else 'http',
                status='meta_atingida' if len(unique) == target else stopped or 'ofertas_insuficientes',
                paginas=requests, ofertas=list(unique.values()))
