"""Transporte Scrapling com headers stealth e uma unica tentativa."""
from types import SimpleNamespace
import re
from urllib.parse import urlsplit
from requests.structures import CaseInsensitiveDict

from curl_cffi.requests.exceptions import RequestException
from scrapling.fetchers import FetcherSession
from scrapling.fetchers import StealthySession
from patchright.sync_api import Error as BrowserError


class Session:
    def __init__(self):
        self.headers = {}
        self._manager = None
        self._client = None

    def get(self, url, *, timeout=25, allow_redirects=False):
        if self._client is None:
            self._manager = FetcherSession(
                impersonate='chrome', stealthy_headers=True, retries=1,
                follow_redirects=False, verify=True,
            )
            self._client = self._manager.__enter__()
        page = self._client.get(
            url, headers=self.headers, timeout=max(timeout) if isinstance(timeout, tuple) else timeout,
            follow_redirects=False,
        )
        return SimpleNamespace(status_code=page.status, headers=CaseInsensitiveDict(page.headers),
                               text=page.body.decode(page.encoding or 'utf-8', errors='replace'), url=page.url)

    def close(self):
        if self._client is not None:
            self._manager.__exit__(None, None, None)
            self._client = None


class BrowserSession(Session):
    """Renderiza paginas publicas em perfil temporario, sem resolver desafios."""

    def __init__(self, validate_url, start_url=None):
        super().__init__()
        self.validate_url = validate_url
        self.start_url = start_url

    def get(self, url, *, timeout=25, allow_redirects=False):
        blocked = []

        def setup(page):
            def guard(route):
                request = route.request
                if request.is_navigation_request() and request.frame == page.main_frame:
                    try:
                        self.validate_url(request.url)
                        if re.search(r'/(auth|account|login|checkout|customer|captcha|challenge)(/|$)',
                                     urlsplit(request.url).path, re.I):
                            raise ValueError('Navegacao privada')
                    except ValueError:
                        blocked.append(request.url)
                        route.abort()
                        return
                route.continue_()
            page.route('**/*', guard)

        try:
            if self._client is None:
                self._manager = StealthySession(
                    headless=True, retries=1, solve_cloudflare=False, google_search=False,
                    locale='pt-BR', timezone_id='America/Sao_Paulo',
                )
                self._client = self._manager.__enter__()
                if self.start_url and url != self.start_url:
                    self.validate_url(self.start_url)
                    initial = self._client.fetch(self.start_url, timeout=25000, wait=1000, page_setup=setup)
                    if initial.status != 200:
                        return SimpleNamespace(status_code=initial.status, headers=CaseInsensitiveDict(initial.headers),
                                               text=initial.body.decode(initial.encoding or 'utf-8', errors='replace'), url=url)
            page = self._client.fetch(
                url, timeout=int((max(timeout) if isinstance(timeout, tuple) else timeout) * 1000),
                wait=3000, page_setup=setup,
            )
            if blocked:
                return SimpleNamespace(status_code=302, headers={'Location': blocked[0]}, text='', url=url)
            return SimpleNamespace(status_code=page.status, headers=CaseInsensitiveDict(page.headers),
                                   text=page.body.decode(page.encoding or 'utf-8', errors='replace'), url=page.url)
        except BrowserError:
            if blocked:
                return SimpleNamespace(status_code=302, headers={'Location': blocked[0]}, text='', url=url)
            raise RequestException('Falha ao renderizar pagina publica') from None
