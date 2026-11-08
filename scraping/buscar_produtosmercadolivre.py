import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup
import time
import re
import json
import os
import argparse

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraping.catalog_store import image_from_card, persist_sync, product_jsonld


# Identificacao explicita; sem disfarce para contornar verificacoes de acesso.
headers = {
    "User-Agent": 'HunterCatalog/1.0 (limited public catalog collection)',
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


PUBLIC_HOSTS = {'lista.mercadolivre.com.br', 'www.mercadolivre.com.br', 'produto.mercadolivre.com.br'}


def public_url(value):
    u = urlsplit(value)
    if (u.scheme != 'https' or u.netloc not in PUBLIC_HOSTS or u.username or u.password
            or u.query or '%' in u.path or '..' in u.path or any(c.isspace() for c in value) or re.search(r'/(gz|jms|auth|account|login|registration|checkout|cart|api|security|challenge)(/|$)', u.path, re.I)):
        raise ValueError('URL publica Mercado Livre invalida ou requer acesso privado')
    if u.hostname != 'lista.mercadolivre.com.br' and not re.search(r'/p/MLB[0-9]+(?:/|$)|/MLB-[0-9]+', u.path):
        raise ValueError('URL deve identificar produto publico ou listagem')
    return urlunsplit(u._replace(fragment=''))


def buscar_produtos(url: str):
    """
    Faz a requisição HTTP, interpreta o HTML e retorna
    uma lista de dicionários com produto / preço / link.
    """
    from scraping.public_sources import fetch_public_html
    html, final_url, status, _ = fetch_public_html('Mercado Livre', public_url(url), request_delay=3)
    if status != 'ok':
        print('[INFO] Coleta interrompida: ' + status)
        return []
    return parse_html(html, final_url)


def parse_html(html, url):
    soup = BeautifulSoup(html, "html.parser")
    url = public_url(url)
    single = urlsplit(url).hostname != 'lista.mercadolivre.com.br'
    structured = product_jsonld(soup,url,public_url,single=single)
    if structured:
        return structured
    if single:
        return []  # Nao interpretar recomendacoes/parcelas como a oferta principal.


    # Tenta localizar os "cards" de produto com vários seletores possíveis
    # porque o Mercado Livre vive mudando as classes.
    candidates = []
    candidates.extend(soup.select(".poly-card"))

    # Tentativa 1: layout antigo
    candidates.extend(soup.select("li.ui-search-layout__item"))

    # Tentativa 2: result wrapper mais novo
    candidates.extend(soup.select("li.ui-search-result__wrapper"))

    # Tentativa 3: qualquer <li> dentro de lista de resultados
    if not candidates:
        listas = soup.select("ol.ui-search-layout, ul.ui-search-layout")
        for lista in listas:
            candidates.extend(lista.find_all("li", recursive=False))

    print(f"[INFO] Produtos encontrados no HTML bruto: {len(candidates)}")

    itens = []

    seen = set()
    for li in candidates:
        # ------------ NOME E LINK ------------
        # tenta achar um <a> que represente o link do produto
        a_tag = (
            li.select_one("a.poly-component__title")
            or li.select_one(".poly-component__title-wrapper a")
            or li.select_one("a.ui-search-link")
            or li.select_one("a.ui-search-result__content")
            or li.find("a", href=True)
        )

        if not a_tag:
            continue

        heading = li.select_one('h2, h3')
        produto = heading.get_text(' ', strip=True) if heading else a_tag.get_text(strip=True)
        try:
            link = public_url(urljoin(url,a_tag.get('href','').strip()))
        except ValueError:
            continue
        if link in seen:
            continue

        # ------------ PREÇO ------------
        # tenta capturar parte fracionária do preço (ex: 1.234)
        price_box = (li.select_one('.poly-price__current')
                     or li.select_one('.ui-search-price__second-line') or li)
        fractions = price_box.select('span.ui-search-price__fraction, span.andes-money-amount__fraction, span.andes-money-amount__fraction--compact')
        preco_tag = next((tag for tag in fractions if not tag.find_parent(['s','del'])
                          and not tag.find_parent(class_='andes-money-amount--previous')),None)

        if preco_tag:
            preco_texto = preco_tag.get_text(strip=True)
            # remove separadores de milhar e troca vírgula por ponto
            cents = price_box.select_one('span.andes-money-amount__cents, span.ui-search-price__decimals')
            preco_texto = preco_texto.replace(".", "").replace(",", ".")
            if cents and '.' not in preco_texto:
                preco_texto += '.' + cents.get_text(strip=True)
        else:
            preco_texto = "0"

        try:
            preco = float(preco_texto)
        except ValueError:
            preco = 0.0

        if not produto or preco == 0.0 or not link:
            # pula entradas inválidas
            continue

        seen.add(link)
        itens.append({
            "produto": produto,
            "nome": produto,
            "preco": preco,
            "link": link,
            "imagem_url": image_from_card(li, url),
            "coletado_em": datetime.now(timezone.utc),
            "fonte_coleta": 'html_publico',
            "fonte_url": url,
        })

    print(f"[INFO] Itens válidos processados: {len(itens)}")
    return itens


def buscar_com_paginacao(url_base: str, max_paginas: int = 5):
    """
    Faz paginação na busca do Mercado Livre.
    max_paginas é um limite de segurança para não exagerar.
    """
    if not 1 <= max_paginas <= 5:
        raise ValueError('Limite de uma a cinco paginas')
    for page_number in range(1, max_paginas + 1):
        url = url_base if page_number == 1 else f"{url_base}_Desde_{(page_number - 1) * 50}"
        itens = buscar_produtos(url)
        if not itens:
            break
        persist_sync('Mercado Livre', itens)
        time.sleep(2)


class MercadoLivreAPIError(RuntimeError):
    """Erro sanitizado; nunca inclui token, headers ou corpo recebido."""
    def __init__(self, status, path):
        self.status = status
        self.path = path
        super().__init__(f'API Mercado Livre recusou {path}: HTTP {status}; confira OAuth/permissoes.')


class MercadoLivreAPI:
    """Cliente GET oficial; descoberta geral e catalogo sao modos explicitos."""
    BASE = 'https://api.mercadolibre.com'

    def __init__(self, token=None, session=None):
        token = token or os.environ.get('MERCADOLIVRE_ACCESS_TOKEN')
        if not token or token.startswith('REPLACE_'):
            raise ValueError('Configure MERCADOLIVRE_ACCESS_TOKEN apos criar a aplicacao e autorizar OAuth; nenhuma chamada executada.')
        self._token = token
        self.session = session or requests.Session()
        self.requests = 0

    def get(self, path, params=None):
        if not re.fullmatch(r'/sites/MLB/search|/products/search|/products/MLB[0-9]+|/items/MLB[0-9]+(?:/sale_price)?',path):
            raise ValueError('Recurso fora da integracao oficial de leitura.')
        if self.requests:
            time.sleep(3)
        self.requests += 1
        try:
            response = self.session.get(self.BASE+path,params=params,
                headers={'Authorization':'Bearer '+self._token,'User-Agent':headers['User-Agent']},
                timeout=(10,25),allow_redirects=False)
        except requests.RequestException:
            raise RuntimeError('Falha de rede na API Mercado Livre; sem repetir a solicitacao.') from None
        if response.status_code != 200:
            raise MercadoLivreAPIError(response.status_code,path)
        try:
            data = response.json()
        except ValueError:
            raise ValueError('API retornou conteudo nao JSON; nada importado.') from None
        if not isinstance(data,dict):
            raise ValueError('Resposta oficial inesperada; nada importado.')
        return data

    def item(self, item_id):
        from scraping.catalog_store import normalize
        if not re.fullmatch(r'MLB[0-9]+',str(item_id)):
            raise ValueError('ID de anuncio MLB invalido.')
        data = self.get('/items/'+item_id)
        if (data.get('id') != item_id or data.get('site_id') != 'MLB'
                or data.get('status') != 'active' or data.get('currency_id') != 'BRL'
                or type(data.get('available_quantity')) is not int or data['available_quantity'] <= 0
                or type(data.get('seller_id')) is not int or data['seller_id'] <= 0):
            return None
        if len(data.get('variations') or []) > 1:
            return None  # Nao combinar preco de variante incerta com outra imagem.
        title = data.get('title')
        if not isinstance(title,str) or not title.strip():
            return None
        link = public_url(data.get('permalink',''))
        image = next((p.get('secure_url') or p.get('url') for p in data.get('pictures',[])
                      if isinstance(p,dict) and str(p.get('secure_url') or p.get('url','')).startswith('https://')),None)
        if not image:
            return None
        price = self.get('/items/'+item_id+'/sale_price',{'context':'channel_marketplace'})
        if price.get('currency_id') != 'BRL':
            return None
        # Nao usa o price legado de /items nem preco minimo de um modelo de catalogo.
        row = normalize(dict(nome=title,preco=price.get('amount'),link=link,imagem_url=image,
            disponivel=True,coletado_em=datetime.now(timezone.utc),fonte_coleta='api_oficial_mercadolivre',
            fonte_url=self.BASE+'/items/'+item_id+'/sale_price?context=channel_marketplace',
            pagamento='canal marketplace; confirme condicoes na oferta',frete_gratis=None))
        row.update(external_id=item_id,seller_id=data.get('seller_id'))
        return row

    def collect(self, query, limit=5, mode='catalog'):
        if not isinstance(query,str) or not query.strip() or not 1<=limit<=25 or mode not in ('general','catalog'):
            raise ValueError('Informe termo,limite1..25 e modo general/catalog.')
        if mode == 'general':
            # Nenhum seller_id: este modo verifica explicitamente busca entre vendedores.
            search = self.get('/sites/MLB/search',{'q':query.strip(),'limit':limit,'offset':0})
        else:
            search = self.get('/products/search',{'site_id':'MLB','status':'active','q':query.strip(),'limit':limit})
        result, seen = [], set()
        for entry in search.get('results',[])[:limit]:
            if not isinstance(entry,dict):
                continue
            item_id = entry.get('id')
            if mode == 'catalog':
                if not re.fullmatch(r'MLB[0-9]+',str(item_id)):
                    continue
                product = self.get('/products/'+item_id)
                if product.get('id') != item_id or product.get('status') != 'active':
                    continue
                # Modelo sem anuncio vencedor visivel nao vira oferta com preco inventado.
                winner = product.get('buy_box_winner') or {}
                item_id = winner.get('item_id')
            if not re.fullmatch(r'MLB[0-9]+',str(item_id)) or item_id in seen:
                continue
            seen.add(item_id)
            item = self.item(item_id)
            if item:
                result.append(item)
        return result

    def close(self):
        self.session.close()


async def save_api_batch(products, expected_database):
    """Somente estruturas atuais. Nova fonte fica desabilitada ate validacao real."""
    import asyncpg
    from config.settings import database_url
    from scraping.catalog_store import save_observations
    from catalog_expansion.repository import CandidateRepository
    from catalog_expansion.constants import COLLECTION_LOCK
    if not expected_database:
        raise ValueError('--persist exige --expect-database.')
    conn = await asyncpg.connect(database_url())
    locked = False
    try:
        if await conn.fetchval('SELECT current_database()') != expected_database:
            raise ValueError('Banco destino diverge do confirmado.')
        locked = await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',COLLECTION_LOCK)
        if not locked:
            raise ValueError('Outra coleta esta ativa; gravacao adiada.')
        if not products:
            return 0
        async with conn.transaction():
            inserted = await save_observations(conn,'Mercado Livre',products)
            repo = CandidateRepository(conn)
            source = await conn.fetchrow("SELECT * FROM hunter_catalog_sources WHERE code='mercadolivre_api'")
            if not source:
                source = await repo.create_source('mercadolivre_api','Mercado Livre','official_api',
                    ['www.mercadolivre.com.br','produto.mercadolivre.com.br'],request_limit=6)
            for item in products:
                product_id = await conn.fetchval("SELECT id FROM hunter_catalog_products WHERE loja='Mercado Livre' AND link=$1",item['link'])
                await repo.add(source['id'],item['link'],external_id=item['external_id'],
                    seller=str(item['seller_id'] or ''),origin='official_api',product_id=product_id)
            return inserted
    finally:
        if locked:
            await conn.fetchval('SELECT pg_advisory_unlock($1::bigint)',COLLECTION_LOCK)
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description='Coletor Mercado Livre: HTML legado ou API oficial autorizada.')
    parser.add_argument('--api',action='store_true')
    parser.add_argument('--query',default='teclado')
    parser.add_argument('--mode',choices=('general','catalog'),default='catalog')
    parser.add_argument('--limit',type=int,default=5)
    parser.add_argument('--persist',action='store_true')
    parser.add_argument('--expect-database')
    args = parser.parse_args()
    if not args.api:
        buscar_com_paginacao('https://lista.mercadolivre.com.br/kit-para-computadores',max_paginas=5)
        return
    client = MercadoLivreAPI()
    try:
        products = client.collect(args.query,args.limit,args.mode)
        inserted = 0
        if args.persist:
            import asyncio
            inserted = asyncio.run(save_api_batch(products,args.expect_database))
        print(json.dumps({'origem':'API oficial','modo':args.mode,'produtos':len(products),
                          'com_imagem':sum(bool(p.get('imagem_url')) for p in products),
                          'vendedores_distintos':len({p['seller_id'] for p in products}),
                          'observacoes_gravadas':inserted,'requisicoes':client.requests}))
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1) from None
