"""Verificação no Edge instalado, com API simulada e sem gravar no banco.
Execute com o frontend local ativo: python -B tests/browser_ux.py.
"""
import base64
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.browser_support import launch_browser


def token(exp=None):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "7", "exp": exp or int(time.time()) + 3600}).encode()).decode().rstrip("=")
    return "test." + payload + ".signature"


def main():
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        context.route("https://fonts.gstatic.com/**", lambda route: route.abort())
        context.route("https://vlibras.gov.br/**", lambda route: route.abort())
        state = {"profile": {"id": 7, "nome": "Pessoa Teste", "email": "teste@example.com"},
                 "alerts": [{"id": 1, "produto": "Mouse Teste", "preco": 100, "preco_atual": 90, "atingido": True, "loja": "KaBuM!", "link": "https://kabum.com.br/test", "data": "2026-10-05"}],
                 "messages": [], "feedback_body": None, "alert_body": None, "search_error": False,
                 "notifications": [{"id": 1, "produto": "Oferta recebida pela fila", "preco": 90, "preco_desejado": 100,
                                    "loja": "Pichau", "link": "https://www.pichau.com.br/demo", "created_at": "2026-10-23T12:00:00Z", "read_at": None}]}
        products = [{"nome": "Mouse Teste " + str(i), "preco": i * 10, "link": "https://kabum.com.br/" + str(i), "loja": "KaBuM!" if i % 2 else "Mercado Livre"} for i in range(1, 31)]

        def api(route):
            parsed = urlparse(route.request.url)
            path = parsed.path
            method = route.request.method
            data = {}
            if route.request.post_data and "application/json" in route.request.headers.get("content-type", ""):
                data = json.loads(route.request.post_data)
            status = 200
            result = {"message": "Operação concluída."}
            if method == "OPTIONS":
                route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE"})
                return
            if path == "/usuario":
                if method == "PUT":
                    state["profile"].update({k: v for k, v in data.items() if k in ("nome", "email")})
                    result["access_token"] = token()
                elif method == "GET":
                    result = state["profile"]
            elif path == "/buscar-produtos":
                if state["search_error"]:
                    route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail":"Consulta indisponível."}), headers={"Access-Control-Allow-Origin":"*"})
                    return
                query = parse_qs(parsed.query)
                found = products[:]
                if query.get("loja"):
                    found = [p for p in found if p["loja"] == query["loja"][0]]
                if query.get("preco_min"):
                    found = [p for p in found if p["preco"] >= float(query["preco_min"][0])]
                if query.get("preco_max"):
                    found = [p for p in found if p["preco"] <= float(query["preco_max"][0])]
                if query.get("frete_gratis") == ["true"]:
                    found = [p for p in found if p.get("frete_gratis") is True]
                found.sort(key=lambda p: p["preco"], reverse=query.get("ordem") == ["priceDesc"])
                current = int(query.get("pagina", [1])[0])
                result = {"produtos": found[(current-1)*24:current*24], "total": len(found), "pagina": current, "frete_disponivel": False}
            elif path == "/alertas":
                result = state["alerts"]
            elif path == "/notificacoes":
                result = {"notificacoes": state["notifications"], "total": len(state["notifications"]),
                          "nao_lidas": sum(n['read_at'] is None for n in state['notifications']), "pagina": 1}
            elif path.startswith('/notificacoes/'):
                state['notifications'][0]['read_at'] = '2026-10-23T12:01:00Z'
            elif path == "/alerta-preco":
                state["alert_body"] = data
                state["alerts"].append({"id": 2, **data, "preco_atual": None, "atingido": False, "data": "2026-10-05"})
            elif path.startswith("/alerta/"):
                key = int(path.rsplit("/", 1)[1])
                if method == "DELETE": state["alerts"] = [a for a in state["alerts"] if a["id"] != key]
                if method == "PUT": next(a for a in state["alerts"] if a["id"] == key).update(data)
            elif path == "/feedbacks":
                result = state["messages"]
            elif path == "/feedback":
                state["feedback_body"] = data
                state["messages"].append({"id": 1, "feedback": data["feedback"], "data_envio": "2026-10-05"})
            elif path.startswith("/feedback/"):
                key = int(path.rsplit("/", 1)[1])
                if method == "DELETE": state["messages"] = [m for m in state["messages"] if m["id"] != key]
                if method == "PUT": next(m for m in state["messages"] if m["id"] == key).update(data)
            elif path == "/login": result = {"access_token": token(), "token_type": "bearer"}
            route.fulfill(status=status, content_type="application/json", body=json.dumps(result), headers={"Access-Control-Allow-Origin": "*"})

        context.route(re.compile(r"http://(?:127\.0\.0\.1|localhost):8000/"), api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        base = os.environ.get('HUNTER_FRONTEND_URL', 'http://127.0.0.1:5500/')
        page.goto(base)
        expect(page.locator("h1")).to_contain_text("O preço certo")
        page.locator("#homeQuery").fill("mouse")
        page.locator("#homeSearch button").click()
        expect(page.locator(".product-card")).to_have_count(24)
        page.locator("#loadMore").click()
        expect(page.locator(".product-card")).to_have_count(30)
        page.locator("#storeFilter").select_option("KaBuM!")
        expect(page.locator(".product-card")).to_have_count(15)
        page.locator("#minPrice").fill("50")
        page.locator("#maxPrice").fill("100")
        expect(page.locator(".product-card")).to_have_count(3)
        page.locator("#sortOrder").select_option("priceDesc")
        expect(page.locator(".product-price").first).to_contain_text("90,00")
        page.reload()
        expect(page.locator("#minPrice")).to_have_value("50")
        expect(page.locator(".product-card")).to_have_count(3)
        page.locator("#minPrice").fill("200")
        expect(page.locator("#filterError")).to_be_visible()
        expect(page.locator(".product-card")).to_have_count(0)
        page.locator("#clearFilters").click()
        expect(page.locator(".product-card")).to_have_count(24)
        assert page.locator('#shippingFilter option[value="free"]').is_enabled()
        page.locator('#shippingFilter').select_option('free')
        expect(page.locator('.product-card')).to_have_count(0)
        page.locator('#shippingFilter').select_option('all')
        expect(page.locator('.product-card')).to_have_count(24)
        products.append({"nome": "Teclado Pichau", "preco": 119.99, "preco_cartao": 141.16,
                         "link": "https://www.pichau.com.br/teclado-teste", "loja": "Pichau", "pagamento": "Pix",
                         "frete_gratis": None, "frete_observacao": "Frete grátis: Sul e Sudeste",
                         "fonte_coleta": "captura_publica", "coletado_em": "2026-10-05T12:00:00Z"})
        page.locator('#storeFilter').select_option('Pichau')
        expect(page.locator('.product-card')).to_have_count(1)
        expect(page.locator('.product-card')).to_contain_text('Preço no Pix')
        expect(page.locator('.product-card')).to_contain_text('Sul e Sudeste')
        expect(page.locator('.product-card')).to_contain_text('Captura pública consultada')
        products.pop()
        page.locator('#clearFilters').click()
        expect(page.locator('.product-card')).to_have_count(24)
        state["search_error"] = True
        page.locator("#searchForm button").click()
        expect(page.locator("#searchState")).to_contain_text("Consulta indisponível")
        expect(page.locator(".product-card")).to_have_count(0)
        state["search_error"] = False
        page.locator("#searchState button").click()
        expect(page.locator(".product-card")).to_have_count(24)
        page.locator(".product-card button").first.click()
        expect(page).to_have_url(__import__('re').compile(r"login.html\?next="))
        page.locator("#loginEmail").fill("teste@example.com")
        page.locator("#loginSenha").fill("Test-password")
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#produto")).to_have_value("Mouse Teste 1")
        expect(page.locator("#preco")).to_have_value("10.00")
        page.locator("#saveAlert").click()
        expect(page.locator("#alertsList .list-card")).to_have_count(2)
        assert state["alert_body"]["produto"] == "Mouse Teste 1"
        page.locator('#alertsList button').filter(has_text="Editar").first.click()
        page.locator("#preco").fill("80")
        page.locator("#saveAlert").click()
        expect(page.locator("#alertsList .price-row").first).to_contain_text("80,00")
        page.locator('#alertsList button').filter(has_text="Excluir").last.click()
        page.locator('#confirmDialog [value=confirm]').click()
        expect(page.locator("#alertsList .list-card")).to_have_count(1)
        expect(page.locator('#notificationList')).to_contain_text('Oferta recebida pela fila')
        expect(page.locator('#unreadCount')).to_have_text('1 não lidas')
        page.locator('#notificationList button').filter(has_text='Marcar como lida').click()
        expect(page.locator('#unreadCount')).to_have_text('0 não lidas')
        page.goto(base + "feedback.html")
        expect(page.locator("#protectedContent")).to_be_visible()
        assert page.locator("#feedbackForm input").count() == 0
        page.locator("#feedback").fill("  Boa experiência  ")
        page.locator("#saveFeedback").click()
        expect(page.locator("#feedbackList .list-card")).to_have_count(1)
        assert state["feedback_body"] == {"feedback": "Boa experiência"}
        page.locator('#feedbackList button').filter(has_text="Editar").click()
        page.locator("#feedback").fill("Mensagem atualizada")
        page.locator("#saveFeedback").click()
        expect(page.locator("#feedbackList .message")).to_have_text("Mensagem atualizada")
        page.locator('#feedbackList button').filter(has_text="Excluir").click()
        page.locator('#confirmDialog [value=cancel]').click()
        expect(page.locator("#feedbackList .list-card")).to_have_count(1)
        page.goto(base + "configurar.html")
        expect(page.locator("#updateNome")).to_have_value("Pessoa Teste")
        page.locator("#updateEmail").fill("novo@example.com")
        page.locator("#updateUserForm button").click()
        expect(page.locator("#notifications")).to_contain_text("senha atual")
        page.locator("#currentPassword").fill("Test-password")
        page.locator("#updateUserForm button").click()
        expect(page.locator("#notifications")).to_contain_text("Operação concluída")
        page.locator("#deleteUserBtn").click()
        expect(page.locator("#confirmDialog")).to_be_visible()
        page.locator('#confirmDialog [value=cancel]').click()
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 900})
            for filename in ("index.html", "buscar.html?q=mouse", "alertas.html", "feedback.html", "configurar.html", "login.html"):
                page.goto(base + filename)
                page.wait_for_timeout(150)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (filename, width, "overflow")
                if width == 390:
                    page.locator("#menuToggle").click()
                    expect(page.locator("#navLinks")).to_be_visible()
                    expect(page.locator("#menuToggle")).to_have_attribute("aria-expanded", "true")
        page.evaluate("value => localStorage.setItem('token', value)", token(int(time.time())-10))
        page.goto(base + "alertas.html")
        expect(page.locator("#protectedContent")).to_be_hidden()
        expect(page.locator("#authGate")).to_contain_text("Entrar / Criar conta")
        page.goto(base + "buscar.html?q=mouse")
        expect(page.locator(".product-card")).to_have_count(24)
        screenshot = str(Path(tempfile.gettempdir()) / "hunter-search-preview.png")
        page.screenshot(path=str(Path(tempfile.gettempdir()) / "hunter-search-mobile.png"))
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.screenshot(path=screenshot)
        assert not errors, errors
        print("OK: busca, filtros, paginação, login com retorno, alertas CRUD, feedback CRUD, perfil, confirmação, sessão e seis páginas em desktop/celular.")
        print("Preview:", screenshot)
        browser.close()


if __name__ == "__main__":
    main()
