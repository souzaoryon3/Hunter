"""Ponta a ponta: processos reais, broker/DB isolados e frontend no Edge."""
import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import requests
from playwright.sync_api import sync_playwright, expect
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.browser_support import launch_browser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from messaging.config import Settings
from messaging.testing import require_isolated
from scraping.catalog_store import save_observations


async def fixture(settings, name):
    require_isolated(settings)
    conn = await asyncpg.connect(settings.database_url)
    try:
        marker = name
        name += ' atual'
        link = 'https://example.com/queue-test-' + marker
        await conn.execute('INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,90,$2)', name, link)
        stamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        await save_observations(conn, 'KaBuM!', [
            dict(nome=name, preco=120, link=link, coletado_em=stamp, fonte_coleta='fixture_browser'),
            dict(nome=name, preco=90, link=link, coletado_em=stamp+timedelta(minutes=1),
                 imagem_url='https://images.example.invalid/product.jpg', fonte_coleta='fixture_browser')])
        for i in range(30):
            await conn.execute('INSERT INTO produtos_kabum(nome,preco,link) VALUES($1,$2,$3)',
                               marker+' legado '+str(i),float(i+1),link+'/legacy/'+str(i))
    finally:
        await conn.close()


def main():
    settings = Settings.environment()
    require_isolated(settings)
    env = os.environ.copy()
    env['JWT_SECRET_KEY'] = secrets.token_hex(32)
    env['CORS_ORIGINS'] = 'http://127.0.0.1:5501'
    env['HUNTER_SCAN_SECONDS'] = '1'
    env['HUNTER_QUEUE_PREFIX'] = 'hunter_test_browser_' + secrets.token_hex(4)
    root = Path(__file__).resolve().parents[1]
    processes, logs = [], []
    try:
        for module, arguments in [('uvicorn', ['app:app','--host','127.0.0.1','--port','8001']),
                                  ('serve_frontend.py', ['--port','5501']),
                                  ('messaging.worker', []), ('messaging.scheduler', [])]:
            output = tempfile.TemporaryFile(mode='w+b')
            logs.append(output)
            command = [sys.executable, '-B'] + ([module] if module.endswith('.py') else ['-m',module]) + arguments
            processes.append(subprocess.Popen(command, cwd=root, env=env, stdout=output, stderr=output,
                                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
        for _ in range(40):
            try:
                if requests.get('http://127.0.0.1:8001/', timeout=1).ok and requests.get('http://127.0.0.1:5501/', timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(.25)
        else:
            raise AssertionError('Servidores isolados não iniciaram')
        marker = 'BrowserQueue' + secrets.token_hex(6)
        password = secrets.token_urlsafe(18)
        email = marker.lower() + '@example.com'
        assert requests.post('http://127.0.0.1:8001/cadastrar', json={'nome':'Teste Fila','email':email,'senha':password}, timeout=5).status_code == 201
        asyncio.run(fixture(settings, marker))
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            page = browser.new_page(viewport={'width':1280,'height':900})
            page.add_init_script("window.HUNTER_API_URL = 'http://127.0.0.1:8001'")
            for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
                page.route('https://' + host + '/**', lambda route: route.abort())
            page.route('https://images.example.invalid/**', lambda route: route.abort())
            page.goto('http://127.0.0.1:5501/buscar.html?q=' + marker)
            expect(page.locator('.product-card')).to_have_count(24)
            card = page.locator('.product-card').first
            expect(card).to_have_attribute('data-catalog-origin','observed')
            expect(card.locator('.product-image')).to_have_attribute('src', 'imgfeature/product-placeholder.svg')
            assert card.locator('.product-image').evaluate('(img) => img.complete && img.naturalWidth > 0')
            page.locator('.price-history summary').click()
            expect(page.locator('.price-history li')).to_have_count(2)
            expect(page.locator('.price-history li').first).to_contain_text('90,00')
            page.locator('#preferObserved').uncheck()
            expect(page.locator('[data-catalog-origin="observed"]')).to_have_count(0)
            page.reload()
            expect(page.locator('#preferObserved')).not_to_be_checked()
            expect(page.locator('[data-catalog-origin="observed"]')).to_have_count(0)
            page.locator('#preferObserved').check()
            expect(page.locator('.product-card').first).to_have_attribute('data-catalog-origin','observed')
            page.screenshot(path=str(Path(tempfile.gettempdir()) / 'hunter-catalog-history.png'), full_page=True)
            page.goto('http://127.0.0.1:5501/login.html?next=alertas.html')
            page.locator('#loginEmail').fill(email)
            page.locator('#loginSenha').fill(password)
            page.locator('#loginForm button[type=submit]').click()
            expect(page.locator('#protectedContent')).to_be_visible()
            page.locator('#produto').fill(marker+' atual')
            page.locator('#preco').fill('100')
            page.locator('#saveAlert').click()
            expect(page.locator('#alertsList')).to_contain_text(marker)
            for _ in range(40):
                page.locator('#refreshNotifications').click()
                if marker in page.locator('#notificationList').inner_text():
                    break
                page.wait_for_timeout(250)
            expect(page.locator('#notificationList')).to_contain_text(marker)
            expect(page.locator('#unreadCount')).to_have_text('1 não lidas')
            page.locator('#notificationList button').filter(has_text='Marcar como lida').click()
            expect(page.locator('#unreadCount')).to_have_text('0 não lidas')
            page.reload()
            expect(page.locator('#notificationList')).to_contain_text('Lida')
            page.set_viewport_size({'width':390,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            browser.close()
        regression_env = env.copy()
        regression_env['HUNTER_FRONTEND_URL'] = 'http://127.0.0.1:5501/'
        subprocess.run([sys.executable,'-B','tests/browser_ux.py'], cwd=root, env=regression_env, check=True)
        print('OK: imagem com fallback, historico real e preco mais recente; cadastro/login, alerta, agendador, publicação, worker, notificação persistida, leitura e frontend real. Regressão desktop/celular aprovada.')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for output in logs:
            output.close()


if __name__ == '__main__':
    main()
