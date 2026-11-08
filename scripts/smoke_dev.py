"""Smoke HTTP exclusivo da stack dev; cria apenas usuario/alerta ficticios."""
import json
import secrets
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8088")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    u = urlsplit(base)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost") or u.path:
        parser.error("Use somente a URL HTTP loopback da stack dev.")
    token = None

    def call(path, data=None, method=None, form=False):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        if data is not None:
            body = (urlencode(data) if form else json.dumps(data)).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        else:
            body = None
        with urlopen(Request(base + path, data=body, headers=headers, method=method), timeout=30) as r:
            payload = r.read()
            return json.loads(payload) if "application/json" in r.headers.get("Content-Type", "") else payload

    call("/health/ready")
    call("/index.html")
    call("/assets/js/pages/search.js")
    rows = call("/buscar-produtos?nome=" + urlencode({"q": "DEMO FICTICIO"})[2:])["produtos"]
    assert rows and all("DEMO FICTICIO" in p["nome"] for p in rows)
    name = rows[0]["nome"]
    email = "dev" + secrets.token_hex(8) + "@example.invalid"
    password = secrets.token_urlsafe(24)
    call("/cadastrar", {"nome": "DEMO FICTICIO", "email": email, "senha": password})
    token = call("/login", {"username": email, "password": password}, form=True)["access_token"]
    call("/usuario")
    call("/alerta-preco", {"produto": name, "preco": 100})
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        notes = call("/notificacoes")["notificacoes"]
        if notes:
            break
        time.sleep(1)
    else:
        raise AssertionError("Notificacao nao entregue pelo scheduler/broker/worker")
    call(f"/notificacoes/{notes[0]['id']}/lida", method="PUT")
    assert call("/notificacoes")["notificacoes"][0]["read_at"]
    call("/analytics/estatisticas?origem=demo")
    groups = call("/analytics/agrupamentos?origem=demo")
    assert groups
    call("/dashboard.html")
    print("OK: frontend reorganizado, login, busca ficticia, alerta, scheduler/RabbitMQ/worker, notificacao/leitura e Data Mining demo.")


if __name__ == "__main__":
    main()
