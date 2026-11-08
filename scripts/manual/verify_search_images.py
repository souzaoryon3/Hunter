"""Somente leitura: seis imagens reais em buscas amplas no Edge, sem fixtures."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import asyncpg
import requests
from playwright.sync_api import sync_playwright, expect
from scripts.browser_support import launch_browser


async def products():
    dsn=os.environ.get('DATABASE_URL','')
    u=urlsplit(dsn)
    if u.path!='/hunter_db' or (u.port or 5432)!=5432 or u.hostname not in ('localhost','127.0.0.1'):
        raise ValueError('Exige DATABASE_URL principal explicita hunter_db:5432')
    conn=await asyncpg.connect(dsn,server_settings={'default_transaction_read_only':'on'})
    try:
        assert await conn.fetchval('SELECT current_database()')=='hunter_db'
        return [dict(r) for r in await conn.fetch('''SELECT p.id,o.nome,o.imagem_url FROM hunter_catalog_products p
            JOIN LATERAL (SELECT * FROM hunter_price_observations WHERE produto_id=p.id
            ORDER BY coletado_em DESC,id DESC LIMIT 1) o ON TRUE WHERE p.loja='KaBuM!' AND o.disponivel ORDER BY p.id''')]
    finally:await conn.close()


def main():
    rows=asyncio.run(products())
    assert len(rows)==6 and all(r['imagem_url'] for r in rows)
    image_responses={};errors=[];failures=[];verified=set()
    with sync_playwright() as p:
        browser=launch_browser(p)
        try:
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.on('requestfailed',lambda req:failures.append(req.url) if req.url in {r['imagem_url'] for r in rows} else None)
            def response(r):
                if r.url in {p['imagem_url'] for p in rows}:
                    image_responses[r.url]=(r.status,r.headers.get('content-type',''))
            page.on('response',response)
            for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
                page.route('https://'+host+'/**',lambda route:route.abort())
            for term in ('teclado','mouse','ssd','monitor'):
                expected=[r for r in rows if term in r['nome'].lower()]
                result=requests.get('http://127.0.0.1:8000/buscar-produtos',params={'nome':term,'loja':'KaBuM!'},timeout=10)
                assert result.status_code==200
                actual=result.json()['produtos'][:len(expected)]
                assert {r['produto_id'] for r in actual}=={r['id'] for r in expected}
                page.goto('http://127.0.0.1:5500/buscar.html?'+urlencode({'q':term,'loja':'KaBuM!'}))
                for product in expected:
                    card=page.locator(f'.product-card[data-product-id="{product["id"]}"]')
                    expect(card).to_be_visible()
                    image=card.locator('.product-image');image.scroll_into_view_if_needed()
                    page.wait_for_function('({id,url})=>{const i=document.querySelector(`[data-product-id="${id}"] .product-image`);return i&&i.src===url&&i.complete&&i.naturalWidth>0;}',arg={'id':product['id'],'url':product['imagem_url']})
                    verified.add(product['id'])
                page.screenshot(path=str(Path(tempfile.gettempdir())/f'hunter-search-{term}-fixed.png'))
                print('OK: busca ampla '+term+'; fotos reais na primeira pagina='+str(len(expected)))
            page.goto('http://127.0.0.1:5500/buscar.html?q=mouse&loja=KaBuM%21&priorizar_observados=false')
            expect(page.locator('#preferObserved')).not_to_be_checked()
            expect(page.locator('[data-catalog-origin="observed"]')).to_have_count(0)
            page.locator('#preferObserved').check()
            expect(page.locator('[data-catalog-origin="observed"]')).to_have_count(2)
            assert not errors and not failures,(errors,failures)
        finally:browser.close()
    assert len(verified)==6
    assert len(image_responses)==6 and all(status==200 and mime.startswith('image/') for status,mime in image_responses.values())
    print('OK: seis imagens reais HTTP200/image/* decodificadas no Edge em buscar.html; sem erros JS/imagem; nenhum dado alterado')


if __name__=='__main__':
    main()
