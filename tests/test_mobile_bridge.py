"""Ponte mobile contra servidor HTTP ficticio; nunca conecta ao PostgreSQL."""
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from scripts.mobile_api import LIMIT, make_handler


class FixtureAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        payload = json.dumps(dict(method=self.command, path=self.path,
                                  authorization=self.headers.get('Authorization'),
                                  body=body.decode())).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = respond
    do_POST = respond


class MobileBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), FixtureAPI)
        cls.bridge = ThreadingHTTPServer(('127.0.0.1', 0), make_handler('127.0.0.1', cls.upstream.server_port))
        cls.threads = []
        for server in (cls.upstream, cls.bridge):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.bridge, cls.upstream):
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.bridge.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_search_query_is_forwarded_to_fixed_backend(self):
        status, data = self.request('GET', '/buscar-produtos?nome=mouse&pagina=2')
        self.assertEqual(status, 200)
        self.assertEqual(data['path'], '/buscar-produtos?nome=mouse&pagina=2')

    def test_auth_and_form_body_are_forwarded_without_logging(self):
        body = 'username=fixture%40example.invalid&password=fixture-password'
        status, data = self.request('POST', '/login', body, {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Bearer fixture-token'})
        self.assertEqual(status, 200)
        self.assertEqual(data['body'], body)
        self.assertEqual(data['authorization'], 'Bearer fixture-token')

    def test_files_docs_private_backend_paths_are_not_exposed(self):
        for path in ('/.env', '/docs', '/index.html', '/admin', '/../../.env', 'http://example.invalid/usuario'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)

    def test_oversized_body_is_rejected_before_reading(self):
        self.assertEqual(self.request('POST', '/login', headers={'Content-Length': str(LIMIT+1)})[0], 413)

    def test_malformed_length_is_rejected(self):
        self.assertEqual(self.request('POST', '/login', headers={'Content-Length': '-1'})[0], 413)
