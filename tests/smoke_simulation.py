"""Smoke opt-in na copia hunter_sim: nunca escreve no banco principal."""

import asyncio
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from ops import secret_store
from scripts.simulate_production import admin_connection

BASE = "https://localhost:8443"


async def products(state):
    c = await admin_connection(state)
    try:
        assert await c.fetchval("SELECT current_database()") == "hunter_sim"
        return [
            dict(r)
            for r in await c.fetch("""SELECT p.id,o.nome,o.preco,o.imagem_url FROM hunter_catalog_products p
            JOIN LATERAL (SELECT * FROM hunter_price_observations WHERE produto_id=p.id ORDER BY coletado_em DESC,id DESC LIMIT 1) o ON true ORDER BY p.id""")
        ]
    finally:
        await c.close()


def main():
    state = secret_store.read("simulation.dpapi")
    rows = asyncio.run(products(state))
    assert len(rows) == 6 and all(r["imagem_url"] for r in rows)
    session = requests.Session()
    session.verify = str(ROOT / ".secrets/simulation-tls/client/ca.crt")
    for path in (
        "/health/ready",
        "/lojas",
        "/analytics/estatisticas",
        "/analytics/agrupamentos",
        "/dashboard.html",
        "/buscar.html",
    ):
        r = session.get(BASE + path, timeout=30)
        assert r.status_code == 200, (path, r.status_code)
    marker = "Simulation" + secrets.token_hex(8)
    email = marker.lower() + "@example.invalid"
    password = secrets.token_urlsafe(24)
    r = session.post(
        BASE + "/cadastrar",
        json={"nome": "Simulacao isolada", "email": email, "senha": password},
        timeout=20,
    )
    assert r.status_code == 201, r.status_code
    r = session.post(
        BASE + "/login", data={"username": email, "password": password}, timeout=20
    )
    assert r.status_code == 200
    session.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    assert session.get(BASE + "/usuario", timeout=10).status_code == 200
    for row in rows:
        found = session.get(
            BASE + "/buscar-produtos", params={"nome": row["nome"]}, timeout=20
        ).json()["produtos"]
        assert any(p.get("imagem_url") == row["imagem_url"] for p in found), row["id"]
        assert (
            session.get(
                BASE + f"/produtos/{row['id']}/historico", timeout=10
            ).status_code
            == 200
        )
    row = rows[0]
    r = session.post(
        BASE + "/alerta-preco",
        json={"produto": row["nome"], "preco": float(row["preco"]) + 1},
        timeout=10,
    )
    assert r.status_code == 201, r.status_code
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        r = session.get(BASE + "/notificacoes", timeout=10)
        assert r.status_code == 200
        notes = r.json()["notificacoes"]
        if notes:
            break
        time.sleep(1)
    else:
        raise AssertionError("Scheduler/worker nao entregaram notificacao")
    assert (
        session.put(
            BASE + f"/notificacoes/{notes[0]['id']}/lida", timeout=10
        ).status_code
        == 200
    )
    assert (
        session.post(
            BASE + "/feedback",
            json={"feedback": "Smoke isolado com privilegios minimos"},
            timeout=10,
        ).status_code
        == 201
    )
    # Credenciais do usuario sintetico tambem ficam cifradas, para validacao no Edge.
    secret_store.write(
        "simulation-smoke.dpapi",
        {"email": email, "password": password},
        replace=(ROOT / ".secrets/simulation-smoke.dpapi").exists(),
    )
    print(
        "Simulacao: TLS verificado, login/CRUD,6 imagens via API,6 historicos,analytics,dashboard e entrega RabbitMQ/ACK/notificacao aprovados."
    )


if __name__ == "__main__":
    main()
