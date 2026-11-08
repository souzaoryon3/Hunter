"""Edge sobre a stack HTTPS isolada, com produtos reais copiados e login de teste."""
import asyncio
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from ops.secret_store import read
from scripts.browser_support import launch_browser
from smoke_simulation import products


def main():
    rows=asyncio.run(products(read('simulation.dpapi')))
    account=read('simulation-smoke.dpapi')
    verified=set();errors=[]
    with sync_playwright() as p:
        browser=launch_browser(p)
        # Excecao limitada a este contexto para CA local nao instalada no Windows.
        # As verificacoes requests/asyncpg validam a CA; producao nao deve ignorar TLS.
        context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000})
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
            page.route('https://'+host+'/**',lambda route:route.abort())
        page.goto('https://localhost:8443/login.html?next=buscar.html')
        page.locator('#loginEmail').fill(account['email'])
        page.locator('#loginSenha').fill(account['password'])
        page.locator('#loginForm button[type=submit]').click()
        page.wait_for_url('**/buscar.html')
        for term in ('teclado','mouse','ssd','monitor'):
            page.goto('https://localhost:8443/buscar.html?'+urlencode({'q':term,'loja':'KaBuM!'}))
            for row in [r for r in rows if term in r['nome'].lower()]:
                image=page.locator(f'[data-product-id="{row["id"]}"] .product-image')
                expect(image).to_be_visible();image.scroll_into_view_if_needed()
                page.wait_for_function('({id,url})=>{const i=document.querySelector(`[data-product-id="${id}"] .product-image`);return i&&i.src===url&&i.complete&&i.naturalWidth>0}',arg={'id':row['id'],'url':row['imagem_url']})
                verified.add(row['id'])
        assert len(verified)==6
        page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-simulation-search.png'))
        page.goto('https://localhost:8443/dashboard.html')
        expect(page.locator('#dashboardContent')).to_be_visible(timeout=30000)
        expect(page.locator('#sourceBadge')).to_contain_text('Dados reais')
        expect(page.locator('#produtosMetric')).to_have_text('6')
        expect(page.locator('#observacoesMetric')).to_have_text('12')
        expect(page.locator('#priceChart svg')).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-simulation-dashboard-mobile.png'))
        assert not errors,errors
        browser.close()
    print('Edge/containers: login real,6 imagens decodificadas na busca,dashboard6/12 e layout mobile aprovados.')


if __name__=='__main__':main()
