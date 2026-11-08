"""Teste opt-in no principal; preserva fixtures e todos os dados existentes."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import os
import secrets
from urllib.parse import urlsplit

import asyncpg
import requests
from playwright.sync_api import sync_playwright, expect


async def seed(dsn, marker):
    conn = await asyncpg.connect(dsn)
    try:
        assert await conn.fetchval('SELECT current_database()') == 'hunter_db'
        await conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES ($1,90,'https://example.com/hunter-controlled-test')", marker)
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-main-fixture', action='store_true')
    args = parser.parse_args()
    dsn = os.environ.get('DATABASE_URL', '')
    db = urlsplit(dsn)
    if (not args.allow_main_fixture or db.path != '/hunter_db'
            or db.hostname not in ('localhost', '127.0.0.1') or (db.port or 5432) != 5432
            or os.environ.get('HUNTER_QUEUE_TESTS') == '1'):
        raise SystemExit('Exige autorizacao explicita e hunter_db local:5432.')
    marker = 'HunterIntegracao' + secrets.token_hex(6)
    email, password = marker.lower() + '@example.com', secrets.token_urlsafe(18)
    response = requests.post('http://127.0.0.1:8000/cadastrar', json={
        'nome': 'Teste controlado mensageria', 'email': email, 'senha': password}, timeout=10)
    assert response.status_code == 201, 'Cadastro controlado falhou'
    asyncio.run(seed(dsn, marker))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page()
            for host in ('fonts.googleapis.com', 'fonts.gstatic.com', 'vlibras.gov.br'):
                page.route('https://' + host + '/**', lambda route: route.abort())
            page.goto('http://127.0.0.1:5500/login.html?next=alertas.html')
            page.locator('#loginEmail').fill(email)
            page.locator('#loginSenha').fill(password)
            page.locator('#loginForm button[type=submit]').click()
            expect(page.locator('#protectedContent')).to_be_visible()
            page.locator('#produto').fill(marker)
            page.locator('#preco').fill('100')
            page.locator('#saveAlert').click()
            expect(page.locator('#alertsList')).to_contain_text(marker)
            for _ in range(160):
                page.locator('#refreshNotifications').click()
                if marker in page.locator('#notificationList').inner_text():
                    break
                page.wait_for_timeout(500)
            expect(page.locator('#notificationList')).to_contain_text(marker)
            page.locator('#notificationList button').filter(has_text='Marcar como lida').click()
            expect(page.locator('#unreadCount')).to_have_text('0 não lidas')
            page.reload()
            expect(page.locator('#notificationList')).to_contain_text('Lida')
        finally:
            browser.close()
    print('OK: frontend principal, alerta, scheduler/publisher, worker, notificacao e leitura persistida. Fixture preservada: ' + marker)


if __name__ == '__main__':
    main()
