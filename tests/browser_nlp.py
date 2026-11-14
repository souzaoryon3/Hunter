"""Autocomplete: API real, teclado, celular, XSS e respostas fora de ordem."""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_nlp import demonstrate
from scripts.browser_support import launch_browser


def main():
    fixture = asyncio.run(demonstrate())
    root = Path(__file__).resolve().parents[1]
    processes, logs = [], []
    env = dict(os.environ, CORS_ORIGINS='http://127.0.0.1:5505')
    try:
        for args in (['-m','uvicorn','app:app','--host','127.0.0.1','--port','8005'],
                     ['serve_frontend.py','--port','5505']):
            log = tempfile.TemporaryFile()
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-B']+args,cwd=root,env=env,
                stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        for _ in range(80):
            try:
                if requests.get('http://127.0.0.1:8005/',timeout=1).ok and requests.get('http://127.0.0.1:5505/',timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(.25)
        else:
            raise AssertionError('Servidores de teste indisponiveis')
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                page = browser.new_page(viewport={'width':1440,'height':1000})
                errors = []
                page.on('pageerror', lambda exc: errors.append(str(exc)))
                page.add_init_script("window.HUNTER_API_URL='http://127.0.0.1:8005'")
                for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
                    page.route('https://'+host+'/**',lambda route:route.abort())
                page.goto('http://127.0.0.1:5505/index.html')
                field = page.locator('#homeQuery')
                field.fill(fixture['marker'])
                expect(page.locator('#homeQuery-suggestions [role=option]')).to_have_text([fixture['titulo']])
                expect(field).to_have_attribute('aria-expanded','true')
                page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-nlp-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-nlp-mobile.png'),full_page=True)
                field.press('ArrowDown')
                expect(field).to_have_attribute('aria-activedescendant','homeQuery-suggestions-0')
                field.press('Enter')
                expect(page).to_have_url(__import__('re').compile('buscar.html\\?q='))
                expect(page.locator('#resultList')).to_contain_text(fixture['titulo'])
                search = page.locator('#productName')
                search.fill(fixture['marker'])
                expect(page.locator('#productName-suggestions [role=option]')).to_have_text([fixture['titulo']])
                search.press('Escape')
                expect(page.locator('#productName-suggestions')).to_be_hidden()
                # Simula transporte que nao respeita abort, para validar ticket de geracao.
                page.evaluate('''() => {
                    const original=window.HunterAPI.request;
                    window.HunterAPI.request=(path,options) => {
                        if(!path.startsWith('/sugestoes?')) return original(path,options);
                        const q=new URLSearchParams(path.split('?')[1]).get('q');
                        if(q==='falha') return Promise.reject(new Error('API indisponivel'));
                        const texto=q==='malicioso' ? '<img src=x onerror="window.injected=true">' : q;
                        return new Promise(resolve=>setTimeout(()=>resolve({sugestoes:[{texto}]}),q==='antigo'?700:10));
                    };
                }''')
                search.fill('antigo'); page.wait_for_timeout(300)
                search.fill('novo')
                expect(page.locator('#productName-suggestions [role=option]')).to_have_text(['novo'])
                page.wait_for_timeout(800)
                expect(page.locator('#productName-suggestions [role=option]')).to_have_text(['novo'])
                search.fill('malicioso')
                expect(page.locator('#productName-suggestions [role=option]')).to_contain_text('<img')
                expect(page.locator('#productName-suggestions img')).to_have_count(0)
                assert not page.evaluate('Boolean(window.injected)')
                search.fill('falha'); page.wait_for_timeout(350)
                expect(page.locator('#productName-suggestions')).to_be_hidden()
                expect(search).to_be_enabled()
                assert not errors, errors
            finally:
                browser.close()
        print('OK: PLN via RabbitMQ, autocomplete real, teclado, desktop/celular, Escape, respostas atrasadas, XSS e falha sem bloquear busca.')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
