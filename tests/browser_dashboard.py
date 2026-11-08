"""Dashboard no Edge com API/PostgreSQL isolados e demo somente em memoria."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, expect
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.browser_support import launch_browser

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from messaging.config import Settings
from messaging.testing import require_isolated


def main():
    require_isolated(Settings.environment())
    root=Path(__file__).resolve().parents[1]
    processes=[];logs=[]
    env=os.environ.copy();env['CORS_ORIGINS']='http://127.0.0.1:5503'
    try:
        for args in (['-m','uvicorn','app:app','--host','127.0.0.1','--port','8003'],['serve_frontend.py','--port','5503']):
            log=tempfile.TemporaryFile();logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-B']+args,cwd=root,env=env,stdout=log,stderr=log,
                                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        for _ in range(80):
            try:
                if requests.get('http://127.0.0.1:8003/',timeout=1).ok and requests.get('http://127.0.0.1:5503/dashboard.html',timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(.25)
        else:
            raise AssertionError('Servidores isolados indisponiveis')
        with sync_playwright() as p:
            browser=launch_browser(p)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
                page.add_init_script("window.HUNTER_API_URL='http://127.0.0.1:8003'")
                for host in ('fonts.googleapis.com','fonts.gstatic.com','vlibras.gov.br'):
                    page.route('https://'+host+'/**',lambda route:route.abort())
                page.goto('http://127.0.0.1:5503/dashboard.html')
                expect(page.locator('#dashboardContent')).to_be_visible()
                expect(page.locator('#sourceBadge')).to_contain_text('Dados reais')
                page.locator('#dataOrigin').select_option('demo')
                expect(page.locator('#sourceBadge')).to_contain_text('sintéticos')
                expect(page.locator('#produtosMetric')).to_have_text('9')
                expect(page.locator('#observacoesMetric')).to_have_text('72')
                expect(page.locator('#priceChart svg')).to_be_visible()
                expect(page.locator('#clusterChart circle')).to_have_count(9)
                page.locator('#productSelect').select_option('4')
                expect(page.locator('#historyBody tr')).to_have_count(8)
                page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-dashboard-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Overflow no celular'
                page.screenshot(path=str(Path(tempfile.gettempdir())/'hunter-dashboard-mobile.png'),full_page=True)
                page.locator('#clusterCount').select_option('5')
                expect(page.locator('#clusterNote')).to_contain_text('pelo menos 10')
                expect(page.locator('#clusterChart circle')).to_have_count(0)
                # Erro e recuperacao, sem tocar no banco nem alterar a API.
                page.route('**/analytics/**',lambda route:route.fulfill(status=503,content_type='application/json',body='{}',headers={'Access-Control-Allow-Origin':'*'}))
                page.locator('#refreshAnalysis').click()
                expect(page.locator('#dashboardError')).to_be_visible()
                expect(page.locator('#dashboardContent')).to_be_hidden()
                page.unroute('**/analytics/**')
                page.locator('#retryAnalysis').click()
                expect(page.locator('#dashboardContent')).to_be_visible()
                # Vazio explicito, nunca reutilizar resultados sinteticos como reais.
                empty={'origem':'real','sintetico':False,'aviso':'Sem dados reais','produtos':[],
                       'resumo':{'produtos':0,'observacoes':0,'quedas':0,'oportunidades':0},'mensagem':'Sem observacoes'}
                def no_data(route):
                    payload=empty if '/estatisticas' in route.request.url else {
                        'status':'dados_insuficientes','mensagem':'Dados insuficientes','grupos':[],'produtos':[]}
                    route.fulfill(status=200,content_type='application/json',body=json.dumps(payload),headers={'Access-Control-Allow-Origin':'*'})
                page.route('**/analytics/**',no_data)
                page.locator('#dataOrigin').select_option('real')
                expect(page.locator('#emptyAnalysis')).to_be_visible()
                expect(page.locator('#produtosMetric')).to_have_text('0')
                expect(page.locator('#sourceBadge')).to_contain_text('Dados reais')
                assert not errors,errors
            finally:
                browser.close()
        print('OK: dashboard real/demo separados, Pandas/K-Means reais na API isolada, graficos, filtros, celular, vazio, insuficiencia, erro e recuperacao.')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
        for log in logs:
            log.close()


if __name__=='__main__':
    main()
