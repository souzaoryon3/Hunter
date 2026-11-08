"""Contratos anteriores permanecem acessiveis pelas fachadas e fabrica."""

import unittest


class APIContractTests(unittest.TestCase):
    def test_existing_http_contracts_are_preserved(self):
        import app

        routes = {
            (method, route.path)
            for route in app.app.routes
            for method in getattr(route, "methods", ())
        }
        required = {
            ("GET", "/"),
            ("POST", "/cadastrar"),
            ("POST", "/login"),
            ("GET", "/usuario"),
            ("PUT", "/usuario"),
            ("DELETE", "/usuario"),
            ("POST", "/feedback"),
            ("GET", "/feedbacks"),
            ("PUT", "/feedback/{feedback_id}"),
            ("DELETE", "/feedback/{feedback_id}"),
            ("POST", "/alerta-preco"),
            ("GET", "/alertas"),
            ("PUT", "/alerta/{alerta_id}"),
            ("DELETE", "/alerta/{alerta_id}"),
            ("GET", "/notificacoes"),
            ("PUT", "/notificacoes/{notificacao_id}/lida"),
            ("GET", "/lojas"),
            ("GET", "/buscar-produtos"),
            ("GET", "/produtos/{produto_id}/historico"),
            ("GET", "/analytics/estatisticas"),
            ("GET", "/analytics/historico/{produto_id}"),
            ("GET", "/analytics/agrupamentos"),
        }
        self.assertFalse(required - routes)
        import auth
        from backend import security

        self.assertIs(auth.get_current_user, security.get_current_user)

    def test_database_pool_is_not_created_on_import(self):
        from backend import database

        self.assertIsNone(database.db_pool)
