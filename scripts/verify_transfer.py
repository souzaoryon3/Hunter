"""Valida somente stack dev restaurada em loopback; fixtures ficam na copia."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from scripts import transfer_database as transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    u = urlsplit(args.url)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost"):
        parser.error("Somente HTTP loopback")
    command, env = transfer.compose_config(args.instance)
    container = transfer.run(command + ["ps", "-q", "postgres"], env=env).decode().strip()
    rows = [json.loads(row) for row in transfer.sql(container, """SELECT row_to_json(t)::text FROM (
      SELECT p.id,o.nome,o.preco,o.imagem_url,(SELECT count(*) FROM hunter_price_observations h WHERE h.produto_id=p.id) total
      FROM hunter_catalog_products p JOIN LATERAL
      (SELECT * FROM hunter_price_observations WHERE produto_id=p.id ORDER BY coletado_em DESC,id DESC LIMIT 1) o ON true ORDER BY p.id) t""").splitlines()]
    session = requests.Session()
    base = args.url.rstrip("/")

    def call(path, method="GET", **kwargs):
        r = session.request(method, base + path, timeout=30, **kwargs)
        r.raise_for_status()
        return r.json() if "application/json" in r.headers.get("Content-Type", "") else r.content

    call("/health/ready")
    call("/buscar.html")
    for row in rows:
        found = call("/buscar-produtos?" + urlencode({"nome": row["nome"]}))["produtos"]
        assert any(p["produto_id"] == row["id"] and p["imagem_url"] == row["imagem_url"] and p["preco"] == row["preco"] for p in found)
        history = call(f"/produtos/{row['id']}/historico")
        assert history["total"] == row["total"]
    # Conta preservada pode acessar seus vinculos com uma senha inteiramente nova.
    uid = int(transfer.sql(container, "SELECT min(id) FROM usuarios WHERE senha='!disabled-transfer-no-login!'"))
    password = secrets.token_urlsafe(24)
    with patch("getpass.getpass", return_value=password):
        transfer.activate_user(argparse.Namespace(instance=args.instance, user_id=uid))
    token = call("/login", "POST", data={"username": f"transfer-{uid}@example.invalid", "password": password})["access_token"]
    session.headers["Authorization"] = "Bearer " + token
    call("/alertas")
    call("/notificacoes")
    # Nova conta e alerta comprovam entrega no broker novo, sem reutilizar JWT antigo.
    email = "restored" + secrets.token_hex(8) + "@example.invalid"
    call("/cadastrar", "POST", json={"nome": "DEMO Restauracao", "email": email, "senha": password})
    token = call("/login", "POST", data={"username": email, "password": password})["access_token"]
    session.headers["Authorization"] = "Bearer " + token
    call("/alerta-preco", "POST", json={"produto": rows[0]["nome"], "preco": rows[0]["preco"] + 1})
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        notes = call("/notificacoes")["notificacoes"]
        if notes:
            break
        time.sleep(1)
    else:
        raise AssertionError("Broker novo nao entregou notificacao")
    call(f"/notificacoes/{notes[0]['id']}/lida", "PUT")
    assert call("/notificacoes")["notificacoes"][0]["read_at"]
    assert call("/analytics/estatisticas?origem=real")["sintetico"] is False
    assert call("/analytics/agrupamentos?origem=demo")["sintetico"] is True
    decoded = 0
    if args.browser:
        from playwright.sync_api import sync_playwright, expect
        from scripts.browser_support import launch_browser
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            for row in rows:
                page.goto(base + "/buscar.html?" + urlencode({"q": row["nome"]}))
                image = page.locator(".product-card .product-image").first
                expect(image).to_be_visible()
                page.wait_for_function("url => { const i=document.querySelector('.product-card .product-image'); return i && i.complete && i.naturalWidth>0 && i.currentSrc===url; }", arg=row["imagem_url"], timeout=30000)
                decoded += 1
            page.goto(base + "/dashboard.html")
            page.set_viewport_size({"width": 390, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            browser.close()
    report = {"products": len(rows), "observations": sum(r["total"] for r in rows), "remote_images_decoded": decoded,
              "restored_user_login": True, "new_login_alert_broker_scheduler_worker_notification_read": True,
              "analytics_real_and_demo": True, "principal_accessed": False}
    out = ROOT / "local-reports"
    out.mkdir(exist_ok=True)
    (out / "transfer-functional.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Copia restaurada validada:", json.dumps(report))


if __name__ == "__main__":
    main()
