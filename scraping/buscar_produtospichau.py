"""Coleta pública da Pichau e importação validada, sem execução ao importar.

Exige DATABASE_URL para gravar. Use --dry-run para somente conferir a coleta.
403/429, desafios e manutenção interrompem a carga; não há contorno de bloqueios.
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import asyncpg
import requests
from bs4 import BeautifulSoup

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraping.catalog_store import https_url, image_from_card, save_observations, product_jsonld, product_image

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.pichau.com.br'
USER_AGENT = 'HunterCatalog/1.0 (public product catalog)'


def public_url(value):
    url = urlsplit(urljoin(BASE, value))
    if (url.scheme != 'https' or url.netloc != 'www.pichau.com.br'
            or url.query or url.fragment or '%' in url.path or '..' in url.path
            or re.search(r'/(api|account|checkout|checkout-app|manager|customer|success|loginascustomer|preview)(/|$)', url.path)):
        raise ValueError('URL deve ser pública, HTTPS e da Pichau, sem parâmetros.')
    return url.geturl()


def money(value):
    text = str(value).replace('R$', '').replace('\u00a0', '').strip()
    # HTML brasileiro e conteúdo público que usa formato 1,429.99.
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.') if text.rfind(',') > text.rfind('.') else text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Preço inválido') from exc
    if not number.is_finite() or not 0 < number < Decimal('10000000000') or number != number.quantize(Decimal('.01')):
        raise ValueError('Preço inválido ou com mais de duas casas decimais')
    return number.quantize(Decimal('.01'))


def validate(item, source, captured_at):
    name = ' '.join(str(item.get('nome', '')).split())
    if not 2 <= len(name) <= 500:
        raise ValueError('Nome do produto inválido')
    shipping = item.get('frete_gratis')
    if shipping is not None and type(shipping) is not bool:
        raise ValueError('frete_gratis deve ser true, false ou null')
    available = item.get('disponivel', True)
    if type(available) is not bool:
        raise ValueError('disponivel deve ser booleano')
    note = str(item.get('frete_observacao') or 'Consulte o frete na loja conforme seu CEP.').strip()
    if shipping is True and re.search(r'sul|sudeste|regi[ãa]o|selecionad|acima|cep', note, re.I):
        raise ValueError('Frete condicionado não pode ser marcado como universal')
    payment = str(item.get('pagamento') or 'Condições na loja').strip()
    return dict(nome=name, preco=money(item['preco']), link=public_url(item['link']),
                preco_cartao=money(item['preco_cartao']) if item.get('preco_cartao') is not None else None,
                pagamento=payment, categoria=str(item.get('categoria', ''))[:255],
                frete_gratis=shipping, frete_observacao=note[:1000], disponivel=available,
                fonte_coleta=source, fonte_url=public_url(item.get('fonte_url') or item['link']),
                coletado_em=captured_at, imagem_url=product_image(item.get('imagem_url')))


def shipping_note(text):
    match = re.search(r'Frete Gr[áa]tis\s*:\s*([^\n]+)', text, re.I)
    if match:
        return 'Frete grátis: ' + match.group(1).strip() + '; confirme regras e CEP na loja.'
    return 'Consulte o frete na loja conforme seu CEP.'


def parse_html(html, url, category=''):
    """Extrai cartões públicos com preço Pix identificado e páginas de produto.

    Prefere o preço visível no Pix; nunca escolhe parcela ou preço riscado.
    Mudanças no markup sem preço reconhecido geram erro, não uma carga vazia.
    """
    url = public_url(url)
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text() if soup.title else ''
    if re.search(r'just a moment|access denied|manuten[çc][ãa]o|captcha', title, re.I):
        raise ValueError('Página bloqueada ou em manutenção; nenhuma oferta gravada.')
    # Pagina individual: dados estruturados e imagem da oferta, nao do cabecalho.
    listing = bool(re.match(r'^/(perifericos|hardware|computadores|notebooks|monitores|marca)(/|$)',urlsplit(url).path))
    structured = product_jsonld(soup,url,public_url,single=not listing)
    if structured:
        for item in structured:
            item.update(categoria=category,frete_observacao='Consulte o frete na loja conforme seu CEP.')
        return [validate(item,'html_publico_jsonld',item['coletado_em']) for item in structured]
    items, candidates = [], []
    if not listing and soup.h1:
        candidates = [(soup.select_one('main') or soup,soup.h1,url)]
    else:
        for anchor in soup.select('a[href]'):
            heading = anchor.select_one('h2, h3')
            if heading is None:
                continue
            try:
                link = public_url(urljoin(url,anchor['href']))
            except ValueError:
                continue
            candidates.append((anchor,heading,link))
    for card, heading, link in candidates:
        text = card.get_text('\n', strip=True)
        text = re.split(r'Características|INFORMAÇÕES ADICIONAIS|Veja as Avaliações', text, flags=re.I)[0]
        # Cartões: "por R$ ... À vista ... PIX"; produto: "à vista R$ ... no PIX".
        match = re.search(r'(?:por\s*:?\s*|[àa]\s*vista\s*)R\$\s*([\d.,]+)\s*(?:[Ààa]\s*vista\s*)?(?:\d+\s*%\s*de\s*desconto\s*)?no\s*PIX', text, re.I)
        if not match:
            continue
        tail = text[match.end():]
        credit = re.search(r'R\$\s*([\d.,]+)\s*em\s*at[ée]', tail, re.I)
        items.append(dict(nome=heading.get_text(' ', strip=True), preco=match.group(1),
                          imagem_url=(soup.select_one('meta[property="og:image"]').get('content')
                                      if not listing and soup.select_one('meta[property="og:image"]')
                                      else image_from_card(card, url, link) if listing or card.name in ('main','a') else None),
                          preco_cartao=credit.group(1) if credit else None, link=link,
                          categoria=category, pagamento='Pix', fonte_url=url,
                          frete_observacao=shipping_note(text), frete_gratis=None,
                          disponivel=not bool(re.search(r'produto indisponível|esgotado', text, re.I))))
    if not items:
        raise ValueError('Nenhum preço Pix reconhecido no HTML. Confira o markup; nada foi gravado.')
    captured_at = datetime.now(timezone.utc)
    return [validate(item, 'html_publico', captured_at) for item in items]


def load_snapshot(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    stamp = datetime.fromisoformat(doc['capturado_em'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError('Informe a data real da captura com fuso horário, sem data futura')
    if not doc.get('produtos') or doc.get('fonte_coleta') != 'captura_publica':
        raise ValueError('Captura pública vazia ou formato desconhecido')
    return [validate(item, 'captura_publica', stamp) for item in doc['produtos']]


def collect(urls):
    from scraping.public_sources import fetch_public_html
    items = []
    for url in urls:
        url = public_url(url)
        html, final_url, status, meta = fetch_public_html('Pichau',url,request_delay=2)
        if status != 'ok':
            code = meta.get('http_status')
            raise ValueError(('HTTP '+str(code)+': ' if code else '')+status+'; nenhuma oferta gravada')
        batch = parse_html(html,final_url,urlsplit(final_url).path.strip('/'))
        for item in batch:
            item['fonte_coleta'] = 'http_publico'
        items.extend(batch)
    return list({item['link']: item for item in items}.values())


async def save(conn, products):
    """Upsert transacional por URL; cargas antigas não sobrescrevem as novas."""
    fields = ('nome', 'preco', 'link', 'preco_cartao', 'pagamento', 'categoria', 'frete_gratis',
              'frete_observacao', 'disponivel', 'fonte_coleta', 'fonte_url', 'coletado_em')
    sql = f"""INSERT INTO produtos_pichau ({', '.join(fields)})
              VALUES ({', '.join('$' + str(i) for i in range(1, len(fields) + 1))})
              ON CONFLICT (link) DO UPDATE SET
              {', '.join(field + ' = EXCLUDED.' + field for field in fields if field != 'link')}
              WHERE EXCLUDED.coletado_em >= produtos_pichau.coletado_em"""
    async with conn.transaction():
        await conn.executemany(sql, [tuple(item[field] for field in fields) for item in products])
        if await conn.fetchval("SELECT to_regclass('hunter_price_observations') IS NOT NULL"):
            await save_observations(conn, 'Pichau', products)


async def persist(products, initialize=False):
    from config.settings import database_url
    dsn = database_url()
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            if initialize:
                await conn.execute((ROOT / 'migrations/001_produtos_pichau.sql').read_text(encoding='utf-8'))
            await save(conn, products)
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--snapshot', type=Path, help='JSON de captura pública, com data original')
    source.add_argument('--html', type=Path, help='HTML público salvo localmente')
    parser.add_argument('--url', action='append', help='URL pública; repita para até quatro categorias')
    parser.add_argument('--dry-run', action='store_true', help='Não conecta nem grava no banco')
    parser.add_argument('--init-db', action='store_true', help='Cria somente a tabela produtos_pichau, se ausente')
    args = parser.parse_args()
    try:
        urls = args.url or [BASE + '/perifericos/teclado']
        if len(urls) > 4:
            raise ValueError('Limite de quatro páginas por execução; sem paginação com parâmetros')
        if args.snapshot:
            products = load_snapshot(args.snapshot)
        elif args.html:
            products = parse_html(args.html.read_text(encoding='utf-8'), urls[0])
        else:
            products = collect(urls)
        products = list({item['link']: item for item in products}.values())
        if args.dry_run:
            print(json.dumps(products, ensure_ascii=False, default=str, indent=2))
        else:
            asyncio.run(persist(products, args.init_db))
            print(f'{len(products)} ofertas processadas, sem apagar produtos existentes.')
    except (ValueError, KeyError, requests.RequestException, asyncpg.PostgresError, OSError) as exc:
        # Não imprimir DSN, senha ou detalhes da conexão.
        print(f'Coleta interrompida ({type(exc).__name__}): ' + (str(exc) if isinstance(exc, ValueError) else 'Confira a fonte ou a conexão do banco.'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
