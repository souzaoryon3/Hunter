"""Coleta KaBuM limitada; importar o modulo nunca inicia navegador ou banco."""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraping.catalog_store import image_from_card, persist_sync


def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def parse_html(html, url, captured_at=None):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    stamp = captured_at or datetime.now(timezone.utc)
    # O HTML atual entrega Product/Offer tambem na listagem, mesmo sem cards.
    # Usa somente dados embutidos na resposta publica, sem endpoints internos.
    from urllib.parse import urlsplit
    hydration = {}
    node = soup.find('script', id='__NEXT_DATA__')
    if node:
        try:
            props = json.loads(node.get_text()).get('props', {}).get('pageProps', {})
            data = props.get('data', {})
            data = json.loads(data) if isinstance(data, str) else data
            rows = data.get('catalogServer', {}).get('data', []) if isinstance(data, dict) else []
            hydration = {str(row['code']): row for row in rows if isinstance(row, dict) and 'code' in row}
        except (ValueError, TypeError, AttributeError):
            pass
    single = '/produto/' in url
    seen = set()
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            document = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        if not isinstance(document, (dict, list)):
            continue
        nodes = document if isinstance(document, list) else document.get('@graph', [document])
        if not isinstance(nodes, list):
            continue
        for product in nodes:
            if not isinstance(product, dict) or product.get('@type') != 'Product':
                continue
            offer = product.get('offers')
            if (not isinstance(offer, dict) or offer.get('@type') != 'Offer'
                    or offer.get('priceCurrency') != 'BRL' or offer.get('price') is None):
                continue
            link = offer.get('url') or product.get('url') or (url if single else None)
            if not isinstance(link, str):
                continue
            target = urlsplit(link)
            if (target.scheme != 'https' or target.netloc != 'www.kabum.com.br'
                    or target.query or target.fragment or not re.match(r'^/produto/\d+/', target.path)):
                continue
            # Pagina pontual nao pode importar anuncios/recomendacoes de outro SKU.
            if single and re.search(r'/produto/(\d+)', url).group(1) != re.search(r'/produto/(\d+)', link).group(1):
                continue
            if link in seen:
                continue
            image = product.get('image')
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get('url') or image.get('contentUrl')
            stock = str(offer.get('availability', '')).endswith('/InStock')
            price, card_price, payment = str(offer['price']), None, None
            row = hydration.get(str(product.get('sku')))
            if row and row.get('name') == product.get('name'):
                # Pix normal exibido; nunca preco Prime, antigo, parcela ou cupom.
                stock = row.get('available') is True
                if row.get('priceWithDiscount') is not None:
                    price = str(row['priceWithDiscount'])
                    card_price = row.get('price')
                    payment = 'Pix; condicoes publicadas na loja'
            if not single and not stock:
                continue
            items.append(dict(nome=product.get('name'), preco=price, preco_cartao=card_price,
                pagamento=payment, link=link, imagem_url=image, coletado_em=stamp,
                disponivel=stock, fonte_coleta='html_publico_jsonld', fonte_url=url))
            seen.add(link)
    if items or single:
        return items
    for card in soup.find_all('article', class_=re.compile('productCard')):
        name = card.find('span', class_=re.compile('nameCard'))
        price = card.find('span', class_=re.compile('priceCard'))
        anchor = card.select_one('a[href]')
        if not name or not price or not anchor:
            continue
        text = re.sub(r'[^0-9,]', '', price.get_text())
        if not text:
            continue
        items.append(dict(nome=name.get_text(' ', strip=True), preco=text.replace(',', '.'),
                          link=urljoin(url, anchor['href']), imagem_url=image_from_card(card, url),
                          coletado_em=stamp, fonte_coleta='html_publico', fonte_url=url))
    return items


def index(max_paginas=1):
    if not 1 <= max_paginas <= 5:
        raise ValueError('Limite de uma a cinco paginas')
    # Dependencias do navegador so sao carregadas em coleta explicitamente solicitada.
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        for page in range(1, max_paginas + 1):
            url = f'https://www.kabum.com.br/perifericos?page_number={page}&page_size=20'
            driver.get(url)
            time.sleep(3)
            html = driver.page_source
            if re.search(r'captcha|access denied|just a moment', driver.title, re.I):
                raise ValueError('Pagina bloqueada; coleta interrompida')
            items = parse_html(html, url)
            if not items:
                raise ValueError('Nenhum produto reconhecido; confira o markup')
            persist_sync('KaBuM!', items)
    finally:
        driver.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-paginas', type=int, default=1)
    index(parser.parse_args().max_paginas)
