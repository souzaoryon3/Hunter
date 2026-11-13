"""Persistencia comum: observacoes datadas, sem imports que executam coleta."""
import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import asyncpg
from config.settings import database_url


def https_url(value, optional=False):
    if optional and not value:
        return None
    try:
        u = urlsplit(str(value))
        if (u.scheme != 'https' or not u.hostname or u.username or u.password
                or any(c.isspace() for c in str(value))):
            raise ValueError()
        _ = u.port
    except (ValueError, TypeError):
        raise ValueError('URL HTTPS publica invalida') from None
    return u._replace(fragment='').geturl()


def product_image(value, base=None):
    """Imagem declarada do produto; rejeita assets de interface e placeholders."""
    import re
    from urllib.parse import urljoin
    if isinstance(value, list):
        return next((image for entry in value if (image := product_image(entry, base))), None)
    if isinstance(value, dict):
        value = value.get('contentUrl') or value.get('url')
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        url = https_url(urljoin(base, value.strip()) if base else value.strip())
    except ValueError:
        return None
    path = urlsplit(url).path.lower()
    if (re.search(r'(?:^|[/_.-])(heart|wishlist|favorite|favourite|favorito|coracao|icon|icons|logo|sprite|placeholder|loading|spinner|pixel|spacer|banner|badge)(?:[/_.-]|$)', path)
            or path.endswith(('.svg', '.gif'))):
        return None
    return url


def image_from_card(card, base, product_link=None):
    """Nunca usa imagem de botao; ambiguidade resulta em imagem ausente."""
    import re
    from urllib.parse import urljoin
    candidates = {}
    for image in card.select('img'):
        ancestors = [image, *image.parents]
        rejected = False
        for node in ancestors:
            attrs = ' '.join(str(node.get(key, '')) for key in ('class', 'id', 'alt', 'aria-label', 'title'))
            if node.name == 'button' or node.get('role') == 'button' or re.search(
                    r'heart|wishlist|favou?rit|favorit|cora(?:cao|c[a\u00e3]o)|logo|icon|placeholder|banner|badge|spinner', attrs, re.I):
                rejected = True
                break
            if node is card:
                break
        if rejected:
            continue
        anchor = image.find_parent('a', href=True)
        if product_link and anchor and urljoin(base, anchor['href']).split('#')[0] != product_link.split('#')[0]:
            continue
        if any(str(image.get(key, '')).isdigit() and int(image[key]) < 80 for key in ('width', 'height')):
            continue
        value = image.get('data-src') or image.get('data-lazy-src') or image.get('src')
        url = product_image(value, base)
        if url:
            candidates[url] = True
    return next(iter(candidates)) if len(candidates) == 1 else None


def normalize(item):
    data = dict(item)
    data['nome'] = ' '.join(str(data.get('nome', '')).split())
    if not 2 <= len(data['nome']) <= 500:
        raise ValueError('Nome invalido')
    for key in ('preco', 'preco_cartao'):
        if key == 'preco_cartao' and data.get(key) is None:
            data[key] = None
            continue
        try:
            number = Decimal(str(data[key]))
            if (not number.is_finite() or not 0 < number < Decimal('10000000000')
                    or number != number.quantize(Decimal('.01'))):
                raise ValueError()
        except (InvalidOperation, ValueError, KeyError):
            raise ValueError('Preco invalido') from None
        data[key] = number
    stamp = data.get('coletado_em')
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError('Data real da observacao com fuso obrigatoria, sem futuro')
    data['link'] = https_url(data.get('link'))
    data['fonte_url'] = https_url(data.get('fonte_url') or data['link'])
    raw_image = data.get('imagem_url')
    if raw_image and https_url(raw_image, optional=True) is None:
        raise ValueError('URL de imagem HTTPS publica invalida')
    data['imagem_url'] = product_image(raw_image)
    if not str(data.get('fonte_coleta', '')).strip():
        raise ValueError('Origem obrigatoria')
    for key in ('disponivel', 'frete_gratis'):
        value = data.get(key, True if key == 'disponivel' else None)
        if type(value) is not bool and not (key == 'frete_gratis' and value is None):
            raise ValueError('Disponibilidade/frete invalidos')
        data[key] = value
    return data


async def save_observations(conn, store, products):
    extended=await conn.fetchval("SELECT to_regclass('hunter_catalog_shops') IS NOT NULL")
    valid=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_catalog_shops WHERE loja=$1)',store) if extended else store in ('KaBuM!', 'Mercado Livre', 'Pichau')
    if not valid:
        raise ValueError('Loja invalida')
    products = [normalize(item) for item in products]
    inserted = 0
    fields = ('nome', 'imagem_url', 'preco', 'preco_cartao', 'pagamento', 'frete_gratis',
              'frete_observacao', 'disponivel', 'coletado_em', 'fonte_coleta', 'fonte_url')
    if extended:
        fields += ('price_kind','promotion_terms')
    async with conn.transaction():
        for item in products:
            if extended:
                item.setdefault('price_kind','regular')
                item.setdefault('promotion_terms',None)
                if item.get('channel','retail') not in ('retail','b2b') or item['price_kind'] not in ('regular','promotional'):
                    raise ValueError('Canal ou condicao invalida')
                if item['price_kind']=='promotional' and not str(item.get('promotion_terms') or '').strip():
                    raise ValueError('Promocao exige condicoes explicitas')
            # Lock serializa importacoes concorrentes da mesma identidade.
            pid = await conn.fetchval('''INSERT INTO hunter_catalog_products(loja,link)
                VALUES($1,$2) ON CONFLICT(loja,link) DO UPDATE SET link=EXCLUDED.link RETURNING id''', store, item['link'])
            if extended:
                current=await conn.fetchrow('SELECT channel FROM hunter_catalog_products WHERE id=$1',pid)
                channel=item.get('channel','retail')
                # INSERT acima e compatibilidade historica; somente produto sem
                # observacoes pode receber seu canal inicial. Nunca troca um canal existente.
                has_history=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_price_observations WHERE produto_id=$1)',pid)
                if has_history and current['channel']!=channel:
                    raise ValueError('Mesmo link com canal divergente; requer oferta distinta')
                if not has_history:
                    await conn.execute('UPDATE hunter_catalog_products SET channel=$2 WHERE id=$1',pid,channel)
            old = await conn.fetchrow('''SELECT * FROM hunter_price_observations
                WHERE produto_id=$1 AND coletado_em=$2 AND fonte_coleta=$3''', pid, item['coletado_em'], item['fonte_coleta'])
            if old:
                if any(old[key] != item.get(key) for key in fields):
                    raise ValueError('Observacao repetida com conteudo divergente; nada sobrescrito')
                continue
            await conn.execute(f'''INSERT INTO hunter_price_observations(produto_id,{','.join(fields)})
                VALUES({','.join('$'+str(i) for i in range(1,len(fields)+2))})''',
                pid, *(item.get(key) for key in fields))
            inserted += 1
    return inserted


async def persist(store, products):
    dsn = database_url()
    conn = await asyncpg.connect(dsn)
    try:
        await save_observations(conn, store, products)
    finally:
        await conn.close()


def persist_sync(store, products):
    asyncio.run(persist(store, products))


def product_jsonld(soup, url, url_validator, *, single=False):
    """Product/Offer publico BRL, sem escolher lowPrice de varias ofertas."""
    import json
    from scrapling import Selector
    page = soup if isinstance(soup, Selector) else Selector(str(soup), url=url)
    nodes = []
    for raw in page.css('script[type="application/ld+json"]::text').getall():
        try:
            doc = json.loads(raw)
        except (ValueError, TypeError):
            continue
        stack = doc if isinstance(doc,list) else [doc]
        while stack:
            node = stack.pop()
            if not isinstance(node,dict):
                continue
            kind = node.get('@type',[])
            if kind == 'Product' or isinstance(kind,list) and 'Product' in kind:
                nodes.append(node)
            for key in ('@graph','itemListElement'):
                children = node.get(key,[])
                if isinstance(children,list):
                    stack.extend(children)
            if isinstance(node.get('item'),dict):
                stack.append(node['item'])
    canonical = url
    canonical_url = page.css('link[rel="canonical"]::attr(href)').get()
    if canonical_url:
        try:
            canonical = url_validator(canonical_url)
        except ValueError:
            pass
    result = []
    for node in nodes:
        if not isinstance(node.get('name'),str) or not node['name'].strip():
            continue
        offer = node.get('offers')
        if isinstance(offer,list):
            offer = offer[0] if len(offer)==1 else None
        if (not isinstance(offer,dict) or offer.get('@type')!='Offer'
                or offer.get('priceCurrency')!='BRL'
                or offer.get('availability') not in ('https://schema.org/InStock','http://schema.org/InStock','InStock')):
            continue
        link = offer.get('url') or node.get('url') or (canonical if single and len(nodes)==1 else None)
        if not isinstance(link,str) or not link:
            continue
        try:
            link = url_validator(link)
            if single and link not in (url_validator(url),canonical):
                continue
            image = product_image(node.get('image'), url)
            item = normalize(dict(nome=node.get('name'),preco=offer.get('price'),link=link,
                                  imagem_url=image,coletado_em=datetime.now(timezone.utc),disponivel=True,
                                  fonte_coleta='html_publico_jsonld',fonte_url=url))
        except (ValueError,TypeError,AttributeError):
            continue
        result.append(item)
    return list({row['link']:row for row in result}.values())
