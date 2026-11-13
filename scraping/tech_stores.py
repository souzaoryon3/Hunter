"""Lojas BR: Product/Offer JSON-LD e cartoes publicos validados."""
from datetime import datetime, timezone
from functools import partial
import re
from urllib.parse import urljoin, urlsplit, parse_qs

from scrapling import Selector
from scraping.catalog_store import product_image, product_jsonld


STORE_URLS = {
    'TerabyteShop': 'https://www.terabyteshop.com.br/hardware/',
    'Amazon Brasil': 'https://www.amazon.com.br/s?k=teclado',
    'Magalu': 'https://www.magazineluiza.com.br/busca/teclado/',
    'Fast Shop': 'https://site.fastshop.com.br/',
    'GK InfoStore': 'https://www.gkinfostore.com.br',
}


def public_url(store, value):
    u = urlsplit(value)
    if (u.scheme != 'https' or u.netloc != urlsplit(STORE_URLS[store]).netloc
            or u.username or u.password or u.fragment or '\\' in value
            or '%' in u.path or '..' in u.path or any(c.isspace() for c in value)
            or re.search(r'/(?:ap|gp|api|account|login|checkout|cart|customer|captcha|challenge|carrinho)(?:/|$)', u.path, re.I)):
        raise ValueError('URL fora da loja ou recurso privado')
    # A unica busca com query e o alvo publico e fixo da Amazon.
    if u.query and value != STORE_URLS[store]:
        raise ValueError('URL de produto deve estar sem parametros')
    return value


def _is_product_link(store, value):
    try:
        value = public_url(store, value)
    except (ValueError, TypeError):
        return False
    path = urlsplit(value).path
    if store == 'Amazon Brasil':
        return bool(re.search(r'/dp/[A-Z0-9]{10}(?:/|$)', path, re.I))
    if store == 'TerabyteShop':
        return bool(re.match(r'^/produto/\d+/', path))
    if store == 'Magalu':
        return bool(re.search(r'/(?:[^/]+/)?p/[A-Z0-9]+(?:/|$)', path, re.I))
    if path.rstrip('/') in ('', '/hardware', '/ofertas', '/perifericos') or re.search(
            r'/(?:busca|categoria|categorias|marcas|departamentos)(?:/|$)', path, re.I):
        return False
    return len([part for part in path.split('/') if part]) >= 1


def _text_values(element, selector):
    return [' '.join(value.split()) for value in element.css(selector).getall() if value.strip()]


def _product_card(store, anchor, base):
    href = urljoin(base, anchor.attrib.get('href', ''))
    if not _is_product_link(store, href):
        return None
    card = anchor
    for _ in range(6):
        links = {urljoin(base, link.attrib.get('href', '')) for link in card.css('a[href]')
                 if _is_product_link(store, urljoin(base, link.attrib.get('href', '')))}
        headings = list(dict.fromkeys(_text_values(card, 'h1::text, h2::text, h3::text')))
        prices = set(re.findall(r'R\$\s*([0-9.]+,[0-9]{2})', card.get_all_text(), re.I))
        if href in links and len(links) == 1 and len(headings) == 1 and len(prices) == 1:
            price = next(iter(prices)).replace('.', '').replace(',', '.')
            image = _product_card_image(card, href, base)
            return dict(nome=headings[0], preco=price, link=href, imagem_url=image)
        if card.parent is None or card.parent.tag in ('body', 'html'):
            break
        card = card.parent
    return None


def _product_card_image(card, product_href, base):
    candidates = set()
    for image in card.css('img'):
        node = image
        product_anchor = None
        rejected = False
        while node is not None:
            attrs = node.attrib
            details = ' '.join(str(attrs.get(key, '')) for key in ('class', 'id', 'alt', 'aria-label', 'title'))
            if (node.tag == 'button' or attrs.get('role') == 'button'
                    or re.search(r'heart|wishlist|favou?rit|favorit|cora(?:cao|c[a\u00e3]o)|logo|icon|placeholder|banner|badge|spinner', details, re.I)):
                rejected = True
                break
            if node.tag == 'a' and attrs.get('href'):
                product_anchor = urljoin(base, attrs['href'])
            if node is card:
                break
            node = node.parent
        if rejected or product_anchor != product_href:
            continue
        attrs = image.attrib
        if any(str(attrs.get(key, '')).isdigit() and int(attrs[key]) < 80 for key in ('width', 'height')):
            continue
        raw = attrs.get('data-src') or attrs.get('data-lazy-src') or attrs.get('src')
        safe = product_image(raw, base)
        if safe:
            candidates.add(safe)
    return next(iter(candidates)) if len(candidates) == 1 else None


def _structured_products(page, store, url):
    path = urlsplit(url).path.rstrip('/')
    listing = (url == STORE_URLS[store] or '/busca/' in path or '/categoria/' in path
               or path in ('/hardware', '/ofertas', '/perifericos'))
    single = bool(page.css('h1::text').get()) and not listing
    return product_jsonld(page, url, partial(public_url, store), single=single)


def _similar_product_links(page, store, base):
    """Use Scrapling structural similarity to find changed card markup."""
    anchors = page.css('a[href]')
    seeds = [anchor for anchor in anchors
             if _is_product_link(store, urljoin(base, anchor.attrib.get('href', '')))
             and _text_values(anchor, 'h2::text, h3::text')
             and re.search(r'R\$\s*[0-9.]+,[0-9]{2}', anchor.get_all_text(), re.I)]
    candidates = list(seeds)
    for seed in seeds[:3]:
        candidates.extend(seed.find_similar(ignore_attributes=('href', 'title'))[:30])
    seen = set()
    for anchor in candidates:
        href = urljoin(base, anchor.attrib.get('href', ''))
        if href in seen:
            continue
        seen.add(href)
        yield anchor


def _terabyte_cards(page, url):
    rows = []
    for card in page.css('.product-item__box'):
        anchor = card.css('a.product-item__name').get()
        if not anchor:
            continue
        node = card.css('a.product-item__name')[0]
        link = urljoin(url, node.attrib.get('href', ''))
        names = list(dict.fromkeys(_text_values(node, 'h2::text')))
        prices = list(dict.fromkeys(_text_values(card, '.product-item__new-price span::text')))
        terms = ' '.join(card.css('.product-item__new-price')[0].get_all_text().split()) if prices else ''
        if not _is_product_link('TerabyteShop', link) or len(names) != 1 or len(prices) != 1 or 'pix' not in terms.lower():
            continue
        match = re.fullmatch(r'R\$\s*([0-9.]+,[0-9]{2})', prices[0])
        if not match:
            continue
        rows.append(dict(nome=names[0], preco=match[1].replace('.', '').replace(',', '.'),
                         link=link, imagem_url=_product_card_image(card, link, url), pagamento='Pix',
                         coletado_em=datetime.now(timezone.utc), fonte_url=url,
                         fonte_coleta='scrapling_public_card'))
    return rows


def _fastshop_cards(page, url):
    rows = []
    for card in page.css('article[data-fs-product-card]'):
        anchors = card.css('[data-fs-product-card-title] a[href]')
        if len(anchors) != 1:
            continue
        anchor = anchors[0]
        link = urljoin(url, anchor.attrib['href'])
        if not _is_product_link('Fast Shop', link) or not urlsplit(link).path.endswith('/p'):
            continue
        # O preco Prime e condicionado a assinatura; usa apenas o valor
        # explicitamente acompanhado de "a vista", fora do bloco Prime.
        amounts = []
        for paragraph in card.css('[class*="Installments"] p'):
            text = paragraph.get_all_text()
            if not re.search(r'[a\u00e0]\s+vista', text, re.I):
                continue
            prices = paragraph.css('[data-testid="price-value"]')
            if prices:
                amounts.append(prices[0].get_all_text().strip())
        amounts = list(dict.fromkeys(amounts))
        if len(amounts) != 1:
            continue
        match = re.fullmatch(r'R\$\s*([0-9.]+(?:,[0-9]{2})?)', amounts[0])
        if not match:
            continue
        name = ' '.join(anchor.get_all_text().split())
        image = _product_card_image(card, link, url)
        if image is None:
            # Fast Shop coloca a foto fora do link do titulo. Aceita apenas
            # imagens marcadas do mesmo card e com descricao exata do produto.
            candidates = set()
            for photo in card.css('img[data-fs-product-card-image]'):
                if photo.xpath('ancestor::button | ancestor::*[@role="button"]'):
                    continue
                if ' '.join(photo.attrib.get('alt', '').split()) != name:
                    continue
                raw = photo.attrib.get('data-src') or photo.attrib.get('src')
                safe = product_image(raw, url)
                if safe:
                    candidates.add(safe)
            if len(candidates) == 1:
                image = candidates.pop()
        rows.append(dict(nome=name,
                         preco=match[1].replace('.', '').replace(',', '.'), link=link,
                         imagem_url=image,
                         pagamento='A vista; consulte condicoes e CEP na loja',
                         coletado_em=datetime.now(timezone.utc), fonte_url=url,
                         fonte_coleta='scrapling_browser_card'))
    return rows


def _amazon_cards(page, url):
    rows = []
    for card in page.css('[data-component-type="s-search-result"][data-asin]'):
        asin = card.attrib.get('data-asin', '')
        headings = card.css('h2')
        if not re.fullmatch(r'[A-Z0-9]{10}', asin) or len(headings) != 1:
            continue
        observed = False
        for anchor in card.css('a[href]'):
            target = urlsplit(urljoin(url, anchor.attrib['href']))
            if target.netloc != 'www.amazon.com.br':
                continue
            if target.path == '/sspa/click':
                target = urlsplit(urljoin(url, parse_qs(target.query).get('url', [''])[0]))
            if target.netloc == 'www.amazon.com.br' and re.search(r'/dp/' + asin + r'(?:/|$)', target.path):
                observed = True
                break
        if not observed:
            continue
        amounts = list(dict.fromkeys(_text_values(
            card, '.a-price[data-a-color="base"]:not(.a-text-price) .a-offscreen::text')))
        if len(amounts) != 1:
            continue
        match = re.fullmatch(r'R\$\s*([0-9.]+(?:,[0-9]{2})?)', amounts[0])
        if not match:
            continue
        images = {product_image(raw, url) for raw in card.css('img.s-image::attr(src)').getall()}
        images.discard(None)
        rows.append(dict(nome=' '.join(headings[0].get_all_text().split()),
                         preco=match[1].replace('.', '').replace(',', '.'),
                         link='https://www.amazon.com.br/dp/' + asin,
                         imagem_url=next(iter(images)) if len(images) == 1 else None,
                         pagamento='Preco anunciado; confirme vendedor, frete e condicoes',
                         coletado_em=datetime.now(timezone.utc), fonte_url=url,
                         fonte_coleta='scrapling_browser_card'))
    return rows


def parse_html(store, html, url):
    url = public_url(store, url)
    page = html if isinstance(html, Selector) else Selector(html, url=url)
    structured = _structured_products(page, store, url)
    if structured:
        return structured
    rows = (_terabyte_cards(page, url) if store == 'TerabyteShop' else
            _fastshop_cards(page, url) if store == 'Fast Shop' else
            _amazon_cards(page, url) if store == 'Amazon Brasil' else [])
    if rows:
        return list({row['link']: row for row in rows}.values())
    stamp_source = url
    for anchor in _similar_product_links(page, store, url):
        item = _product_card(store, anchor, url)
        if item:
            item.update(coletado_em=datetime.now(timezone.utc),
                        fonte_coleta='scrapling_public_card', fonte_url=stamp_source)
            rows.append(item)
    return list({row['link']: row for row in rows}.values())


STORES = {name: (url, partial(parse_html, name)) for name, url in STORE_URLS.items()}
