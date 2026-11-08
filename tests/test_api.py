"""Testes: python -B -m unittest discover -s tests -v.

Integração opt-in com HUNTER_TEST_DATABASE_URL. Todas as gravações são revertidas.
Sequências PostgreSQL podem avançar, mesmo após rollback.
"""
import asyncio
import json
import os
import secrets
import unittest
from datetime import timedelta
from urllib.parse import urlencode

os.environ.setdefault("JWT_SECRET_KEY", secrets.token_hex(32))

import asyncpg
from config.settings import test_database_url
from fastapi import HTTPException
from pydantic import ValidationError

import app as backend
from auth import create_access_token, get_current_user


async def http(method, path, body=None, token=None, form=False):
    """Executa a aplicação ASGI sem iniciar servidor ou lifespan."""
    headers = [(b"host", b"testserver")]
    if token:
        headers.append((b"authorization", ("Bearer " + token).encode()))
    raw = b""
    if body is not None:
        raw = urlencode(body).encode() if form else json.dumps(body).encode()
        headers.append((b"content-type", b"application/x-www-form-urlencoded" if form else b"application/json"))
    route, _, query = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": route, "raw_path": route.encode(), "query_string": query.encode(),
             "headers": headers, "client": ("127.0.0.1", 1), "server": ("testserver", 80), "root_path": ""}
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    await backend.app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(data) if data else None


class ValidationTests(unittest.TestCase):
    def test_messages(self):
        self.assertEqual(backend.Feedback(feedback="  mensagem  ").feedback, "mensagem")
        for message in ("", "   ", "x" * 5001):
            with self.assertRaises(ValidationError):
                backend.Feedback(feedback=message)

    def test_prices(self):
        for price in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValidationError):
                backend.AlertaPreco(produto="Mouse", preco=price)
        with self.assertRaises(ValidationError):
            backend.AlertaPreco(produto="  ", preco=10)

    def test_tokens(self):
        self.assertEqual(get_current_user(create_access_token({"sub": "7"})), "7")
        for token in (create_access_token({"sub": "7"}, timedelta(seconds=-1)), create_access_token({}), "invalid"):
            with self.assertRaises(HTTPException):
                get_current_user(token)


@unittest.skipUnless(os.environ.get("HUNTER_TEST_DATABASE_URL"), "Banco de testes não configurado")
class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = await asyncpg.connect(test_database_url())
        self.addAsyncCleanup(self.cleanup_database)
        self.tx = self.conn.transaction()
        await self.tx.start()

        async def test_db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db] = test_db
        self.email = "hunter-test-" + secrets.token_hex(8) + "@example.com"
        self.password = "Hunter-test-123"
        status, user = await http("POST", "/cadastrar", {"nome": "Teste Hunter", "email": self.email, "senha": self.password})
        self.assertEqual(status, 201, user)
        self.user_id = user["usuario_id"]
        status, login = await http("POST", "/login", {"username": self.email, "password": self.password}, form=True)
        self.assertEqual(status, 200, login)
        self.token = login["access_token"]

    async def cleanup_database(self):
        backend.app.dependency_overrides.clear()
        try:
            if hasattr(self, "tx"):
                await self.tx.rollback()
            if hasattr(self, "user_id"):
                self.assertFalse(await self.conn.fetchval("SELECT EXISTS(SELECT 1 FROM usuarios WHERE id=$1)", self.user_id))
        finally:
            await self.conn.close()

    async def test_profile_and_stable_identity(self):
        status, profile = await http("GET", "/usuario", token=self.token)
        self.assertEqual(status, 200)
        self.assertNotIn("senha", profile)
        updated_email = "new-" + self.email
        status, _ = await http("PUT", "/usuario", {"email": updated_email}, self.token)
        self.assertEqual(status, 400)
        status, _ = await http("PUT", "/usuario", {"email": updated_email, "senha_atual": self.password}, self.token)
        self.assertEqual(status, 200)
        status, profile = await http("GET", "/usuario", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(profile["email"], updated_email)

    async def test_feedback_crud_and_owner(self):
        status, result = await http("POST", "/feedback", {"feedback": "  Boa experiencia  ", "nome": "Outro", "email": "outro@example.com"}, self.token)
        self.assertEqual(status, 201)
        feedback_id = result["id"]
        row = await self.conn.fetchrow("SELECT nome, email FROM feedbacks WHERE id=$1", feedback_id)
        self.assertEqual(row["email"], self.email)
        status, _ = await http("PUT", f"/feedback/{feedback_id}", {"feedback": "Atualizada"}, self.token)
        self.assertEqual(status, 200)
        status, rows = await http("GET", "/feedbacks", token=self.token)
        self.assertEqual(rows[0]["feedback"], "Atualizada")
        status, _ = await http("PUT", f"/feedback/{feedback_id}", {"feedback": "  "}, self.token)
        self.assertEqual(status, 422)
        await self.check_other_user_denied(f"/feedback/{feedback_id}", {"feedback": "Invadida"})
        status, _ = await http("DELETE", f"/feedback/{feedback_id}", token=self.token)
        self.assertEqual(status, 200)

    async def check_other_user_denied(self, path, body):
        other_id = await self.conn.fetchval("INSERT INTO usuarios(nome,email,senha) VALUES($1,$2,$3) RETURNING id", "Outro Teste", "other-"+self.email, "unused")
        other_token = create_access_token({"sub": str(other_id)})
        for method in ("PUT", "DELETE"):
            status, _ = await http(method, path, body if method == "PUT" else None, other_token)
            self.assertEqual(status, 404)

    async def test_alerts_crud_and_matching(self):
        marker = "Hunter Product " + secrets.token_hex(8)
        await self.conn.execute("INSERT INTO produtos_kabum(nome,preco,link) VALUES($1,$2,$3)", marker, 99.5, "https://kabum.com.br/test")
        status, result = await http("POST", "/alerta-preco", {"produto": marker, "preco": 100}, self.token)
        self.assertEqual(status, 201)
        alert_id = result["id"]
        status, alerts = await http("GET", "/alertas", token=self.token)
        self.assertTrue(alerts[0]["atingido"])
        self.assertEqual(alerts[0]["preco_atual"], 99.5)
        status, _ = await http("PUT", f"/alerta/{alert_id}", {"preco": 90}, self.token)
        self.assertEqual(status, 200)
        _, alerts = await http("GET", "/alertas", token=self.token)
        self.assertFalse(alerts[0]["atingido"])
        await self.check_other_user_denied(f"/alerta/{alert_id}", {"preco": 1})
        status, _ = await http("DELETE", f"/alerta/{alert_id}", token=self.token)
        self.assertEqual(status, 200)

    async def test_search_filters_and_pagination(self):
        marker = "Hunter Search " + secrets.token_hex(8)
        for table, price in (("produtos_kabum", 10), ("produtos_kabum", 20), ("produtos_mercadolivre", 30)):
            await self.conn.execute(f"INSERT INTO {table}(nome,preco,link) VALUES($1,$2,$3)", marker, price, "https://example.com/"+str(price))
        status, data = await http("GET", "/buscar-produtos?"+urlencode({"nome":marker,"limite":2}))
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 3)
        self.assertEqual([p["preco"] for p in data["produtos"]], [10,20])
        _, data = await http("GET", "/buscar-produtos?"+urlencode({"nome":marker,"limite":2,"pagina":2}))
        self.assertEqual([p["preco"] for p in data["produtos"]], [30])
        _, data = await http("GET", "/buscar-produtos?"+urlencode({"nome":marker,"loja":"KaBuM!","preco_min":20,"preco_max":20}))
        self.assertEqual(data["total"], 1)
        _, data = await http("GET", "/buscar-produtos?"+urlencode({"nome":marker,"ordem":"priceDesc"}))
        self.assertEqual([p["preco"] for p in data["produtos"]], [30,20,10])
        _, data = await http("GET", "/buscar-produtos?"+urlencode({"nome":marker,"frete_gratis":"true"}))
        self.assertTrue(data["frete_disponivel"])
        self.assertEqual(data["total"], 0)
        status, _ = await http("GET", "/buscar-produtos?nome=mouse&preco_min=20&preco_max=10")
        self.assertEqual(status, 422)

    async def test_delete_cascade_and_authentication(self):
        status, _ = await http("GET", "/usuario")
        self.assertEqual(status, 401)
        status, _ = await http("POST", "/login", {"username":self.email,"password":"wrong"}, form=True)
        self.assertEqual(status, 401)
        await http("POST", "/feedback", {"feedback":"Teste"}, self.token)
        await http("POST", "/alerta-preco", {"produto":"Teste","preco":50}, self.token)
        status, _ = await http("DELETE", "/usuario", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(await self.conn.fetchval("SELECT count(*) FROM feedbacks WHERE usuario_id=$1",self.user_id),0)
        self.assertEqual(await self.conn.fetchval("SELECT count(*) FROM alertas_preco WHERE usuario_id=$1",self.user_id),0)
        status, _ = await http("GET", "/usuario", token=self.token)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
