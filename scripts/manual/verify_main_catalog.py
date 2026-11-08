"""Opt-in: verifica catalogo real e adiciona alerta ao usuario sintetico existente."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import asyncpg
import requests
from playwright.sync_api import sync_playwright, expect
from scripts.browser_support import launch_browser

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))


async def verify(existing_alert=None):
    from auth import create_access_token
    dsn=os.environ.get('DATABASE_URL','')
    u=urlsplit(dsn)
    assert u.path=='/hunter_db' and (u.port or 5432)==5432 and u.hostname in ('localhost','127.0.0.1')
    conn=await asyncpg.connect(dsn)
    try:
        assert await conn.fetchval('SELECT current_database()')=='hunter_db'
        products=await conn.fetch('''SELECT p.id,p.loja,p.link,o.nome,o.preco,o.imagem_url FROM hunter_catalog_products p
            JOIN LATERAL (SELECT * FROM hunter_price_observations WHERE produto_id=p.id
                ORDER BY coletado_em DESC,id DESC LIMIT 1) o ON TRUE WHERE o.disponivel ORDER BY p.id''')
        assert products,'Nao ha produtos reais observados'
        for product in products:
            result=requests.get('http://127.0.0.1:8000/buscar-produtos',params={'nome':product['nome']},timeout=10)
            assert result.status_code==200
            current=next(row for row in result.json()['produtos'] if row['produto_id']==product['id'])
            assert current['preco_atual']==float(product['preco']) and current['imagem_url']==product['imagem_url']
            history=requests.get(f"http://127.0.0.1:8000/produtos/{product['id']}/historico",timeout=10)
            assert history.status_code==200 and history.json()['historico'][0]['preco']==float(product['preco'])
        product=products[0]
        # Nunca usar conta real de usuario para a fixture.
        user=await conn.fetchval("SELECT id FROM usuarios WHERE nome='Teste controlado mensageria' AND email LIKE 'hunterintegracao%@example.com' ORDER BY id DESC LIMIT 1")
        assert user,'Usuario sintetico autorizado da integracao anterior ausente'
        token=create_access_token({'sub':str(user)})
        headers={'Authorization':'Bearer '+token}
        if existing_alert:
            assert await conn.fetchval('SELECT EXISTS(SELECT 1 FROM alertas_preco WHERE id=$1 AND usuario_id=$2 AND produto=$3)',existing_alert,user,product['nome'])
            alert=existing_alert
        else:
            r=requests.post('http://127.0.0.1:8000/alerta-preco',headers=headers,
                            json={'produto':product['nome'],'preco':float(product['preco'])-.01},timeout=10)
            assert r.status_code==201
            alert=r.json()['id']
            for _ in range(50):
                if await conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_alert_state WHERE alerta_id=$1)',alert):
                    break
                await asyncio.sleep(.5)
            else:
                raise AssertionError('Scheduler nao avaliou alerta')
            assert not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_events WHERE alerta_id=$1)',alert),'Preco antigo disparou alerta'
            r=requests.put(f'http://127.0.0.1:8000/alerta/{alert}',headers=headers,json={'preco':float(product['preco'])},timeout=10)
            assert r.status_code==200
        for _ in range(70):
            count=await conn.fetchval('''SELECT count(*) FROM hunter_notifications n JOIN hunter_events e ON e.id=n.event_id
                WHERE e.alerta_id=$1 AND e.status='processed' ''',alert)
            if count:
                break
            await asyncio.sleep(.5)
        assert count==1,'Notificacao ausente ou duplicada'
        print('OK: APIs de busca/historico, preco atual e scheduler/RabbitMQ/worker no principal; alerta sintetico preservado id='+str(alert))
    finally:
        await conn.close()
    return products,token


def verify_browser(products,token):
    with sync_playwright() as p:
        browser=launch_browser(p)
        try:
            page=browser.new_page(viewport={'width':1280,'height':900})
            for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
                page.route('https://'+host+'/**',lambda route:route.abort())
            page.add_init_script('localStorage.setItem("token",'+json.dumps(token)+')')
            image_results=[]
            for product in products:
                page.goto('http://127.0.0.1:5500/buscar.html?'+urlencode({'q':product['nome']}))
                card=page.locator('.product-card').filter(has=page.get_by_role('heading',name=product['nome'],exact=True)).first
                expect(card).to_be_visible()
                image=card.locator('.product-image')
                page.wait_for_function('(selector) => {const i=document.querySelector(selector);return i && i.complete && i.naturalWidth>0}',arg='.product-image')
                image_results.append({'produto_id':product['id'],'imagem_real':image.get_attribute('src')==product['imagem_url']})
                card.locator('.price-history summary').click()
                expect(card.locator('.price-history li').first).to_be_visible()
            page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-main-catalog003.png'),full_page=True)
            page.goto('http://127.0.0.1:5500/alertas.html')
            expect(page.locator('#notificationList')).to_contain_text(products[0]['nome'])
            print('BROWSER '+json.dumps(image_results))
            print('OK: imagens/fallback, historico e notificacao no frontend principal')
        finally:
            browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-main-alert',action='store_true')
    parser.add_argument('--existing-alert',type=int,help='Revalidar fixture existente sem criar outro alerta')
    args=parser.parse_args()
    if not args.allow_main_alert:
        raise SystemExit('Exige --allow-main-alert; preserva alerta sintetico no principal')
    products,token=asyncio.run(verify(args.existing_alert))
    verify_browser(products,token)
