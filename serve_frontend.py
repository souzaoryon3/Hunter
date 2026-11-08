"""Servidor local do Hunter: arquivos atuais, sem cache e com diretório fixo."""
import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / 'frontend'
PAGES = {"index.html", "buscar.html", "alertas.html", "feedback.html", "configurar.html", "login.html", "dashboard.html"}
ASSETS = {'ui.css':'assets/css/ui.css', 'styles.css':'assets/css/styles.css',
          'ui.js':'assets/js/ui.js', 'dashboard.js':'assets/js/dashboard.js'}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"}


class FrontendHandler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        route=unquote(urlsplit(path).path).lstrip('/') or 'index.html'
        route=ASSETS.get(route,route)
        if route.startswith(('img/','imgfeature/')):
            route='assets/'+route
        return str((FRONTEND/route).resolve())

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        if path == '/runtime-config.js':
            value=os.environ.get('HUNTER_API_URL','')
            if value:
                target=urlsplit(value)
                if target.scheme not in ('http','https') or not target.hostname or target.username or target.password or target.query or target.fragment:
                    self.send_error(500,'Configuracao publica invalida');return None
            body=('window.HUNTER_API_URL = window.HUNTER_API_URL || '+json.dumps(value)+';').encode()
            import io
            self.send_response(200);self.send_header('Content-Type','application/javascript')
            self.send_header('Content-Length',str(len(body)));self.end_headers()
            return io.BytesIO(body)
        candidate = Path(self.translate_path(path))
        try:
            relative = candidate.relative_to(FRONTEND)
        except ValueError:
            self.send_error(403, "Acesso negado")
            return None
        is_page = relative.as_posix() in PAGES
        is_script = relative.parts[:2] in (('assets','js'),('assets','css')) and candidate.suffix in ('.js','.css')
        is_image = (relative.parts[:2] in (('assets','img'),('assets','imgfeature'))
                    and candidate.suffix.lower() in IMAGE_EXTENSIONS)
        if not (is_page or is_script or is_image) or not candidate.is_file():
            self.send_error(404, "Arquivo nao encontrado")
            return None
        # Uma versão antiga não deve receber 304 e reaproveitar HTML em cache.
        if "If-Modified-Since" in self.headers:
            del self.headers["If-Modified-Since"]
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description="Frontend local do Hunter, sem cache.")
    parser.add_argument("--port", type=int, default=5500)
    args = parser.parse_args()
    handler = partial(FrontendHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Hunter: http://127.0.0.1:{args.port}/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
