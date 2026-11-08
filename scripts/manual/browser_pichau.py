"""Smoke test de leitura contra frontend/API reais e catálogo Pichau carregado."""
from playwright.sync_api import sync_playwright, expect
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.browser_support import launch_browser


def main():
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        for host in ('fonts.googleapis.com', 'fonts.gstatic.com', 'vlibras.gov.br'):
            page.route('https://' + host + '/**', lambda route: route.abort())
        response = page.request.get('http://127.0.0.1:8000/buscar-produtos?nome=teclado&loja=Pichau')
        assert response.ok
        products = response.json()['produtos']
        assert products and all(p['loja'] == 'Pichau' for p in products)
        page.goto('http://127.0.0.1:5500/buscar.html?q=teclado&loja=Pichau')
        expect(page.locator('.product-card')).to_have_count(len(products))
        expect(page.locator('.product-card').first).to_contain_text('Preço no Pix')
        expect(page.locator('.product-card').first).to_contain_text('Captura pública consultada')
        assert all('www.pichau.com.br' in href for href in page.locator('.product-card a').evaluate_all('(links) => links.map(a => a.href)'))
        page.locator('#minPrice').fill('200')
        page.locator('#maxPrice').fill('300')
        expected = sum(200 <= p['preco'] <= 300 for p in products)
        expect(page.locator('.product-card')).to_have_count(expected)
        if expected:
            expect(page.locator('.product-card').first).to_contain_text('Sul e Sudeste')
        page.locator('#shippingFilter').select_option('free')
        expect(page.locator('.product-card')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#clearFilters').click()
        expect(page.locator('#storeFilter')).to_have_value('')
        browser.close()
        print('OK: Pichau consultada do PostgreSQL pela API real, links, Pix/cartão, faixa de preço e frete regional.')


if __name__ == '__main__':
    main()
