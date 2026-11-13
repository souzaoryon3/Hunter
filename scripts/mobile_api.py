"""Ponte HTTP de desenvolvimento para celular; somente API, sem arquivos ou banco."""
import argparse
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from urllib.parse import urlsplit

ROUTES = re.compile(
    r"^/(?:health/(?:ready|live)|lojas|buscar-produtos|produtos/\d+/historico|"
    r"cadastrar|login|usuario|alerta-preco|alertas|alerta/\d+|notificacoes(?:/\d+/lida)?)$"
)
LIMIT = 1024 * 1024


def make_handler(host, port):
    class ApiBridge(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Nunca registra corpos, tokens ou credenciais.

        def fail(self, status, message):
            body = json.dumps({"detail": message}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def forward(self):
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not ROUTES.fullmatch(parsed.path):
                self.fail(404, "Recurso indisponivel nesta ponte de desenvolvimento.")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > LIMIT or self.headers.get("Transfer-Encoding"):
                    self.fail(413, "Requisicao excede os limites de desenvolvimento.")
                    return
            except ValueError:
                self.fail(400, "Tamanho de requisicao invalido.")
                return
            body = self.rfile.read(length) if length else None
            headers = {key: self.headers[key] for key in ("Content-Type", "Accept", "Authorization") if key in self.headers}
            connection = HTTPConnection(host, port, timeout=20)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(payload)
            except (OSError, HTTPException):
                self.fail(502, "A API local nao respondeu. Inicie a stack Hunter e tente novamente.")
            finally:
                connection.close()

        do_GET = forward
        do_POST = forward
        do_PUT = forward
        do_DELETE = forward
    return ApiBridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Use o IP da rede local para conectar um celular.")
    parser.add_argument("--port", type=int, default=18089)
    parser.add_argument("--target", default="http://127.0.0.1:18088")
    args = parser.parse_args()
    target = urlsplit(args.target)
    if (target.scheme != "http" or target.hostname not in ("localhost", "127.0.0.1")
            or target.username or target.password or target.query or target.fragment or target.path not in ("", "/")):
        parser.error("O destino deve ser a API HTTP local em loopback, sem credenciais.")
    if not 1024 <= args.port <= 65535:
        parser.error("Use uma porta entre 1024 e 65535.")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(target.hostname, target.port or 80))
    print(f"Hunter Mobile API: http://{args.host}:{args.port} (desenvolvimento local)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
