"""Fontes publicas limitadas; redirects canonicos seguros, sem seguir autenticacao."""
import os
import re
from urllib.parse import urlsplit, urljoin, parse_qsl

from scraping import transport
from scrapling import Selector
from scraping.buscar_produtoskabum import parse_html as kabum_html
from scraping.buscar_produtosmercadolivre import parse_html as ml_html, public_url as ml_url
from scraping.buscar_produtospichau import parse_html as pichau_html, public_url as pichau_url
from scraping.catalog_store import normalize
from scraping.tech_stores import STORES as TECH_STORES, public_url as tech_url

AGENT = 'HunterCatalog/1.0 (small public catalog sample)'
STORES = {
    'KaBuM!': ('https://www.kabum.com.br/perifericos', kabum_html),
    'Mercado Livre': ('https://lista.mercadolivre.com.br/teclado', ml_html),
    'Pichau': ('https://www.pichau.com.br/perifericos/teclado', pichau_html),
    **TECH_STORES,
}


def store_url(store, value):
    if store in TECH_STORES:
        return tech_url(store, value)
    if store == 'Mercado Livre':
        return ml_url(value)
    if store == 'Pichau':
        return pichau_url(value)
    u = urlsplit(value)
    if (u.scheme != 'https' or u.netloc != urlsplit(STORES[store][0]).netloc
            or u.username or u.password):
        raise ValueError('URL fora da loja')
    return value


def respect_robots():
    """Consulta opcional; desativada por padrao por decisao do operador."""
    return os.environ.get('HUNTER_RESPECT_ROBOTS', '0') == '1'


def robots_allows(text, agent, url):
    """Respeita wildcard e fim-de-URL que RobotFileParser nao interpreta."""
    groups = []
    names, rules, directives = [], [], False
    for line in [*text.splitlines(), 'User-agent: end-of-file-marker']:
        key, sep, value = line.split('#', 1)[0].partition(':')
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == 'user-agent':
            if directives:
                groups.append((names, rules))
                names, rules, directives = [], [], False
            names.append(value.lower())
        elif key in ('allow', 'disallow') and names:
            directives = True
            if value:
                rules.append((key == 'allow', value))
    selected, best = [], -1
    for names, rules in groups:
        specificity = max((len(name) if name != '*' else 0 for name in names
                           if name == '*' or name in agent.lower()), default=-1)
        if specificity > best:
            selected, best = list(rules), specificity
        elif specificity == best and specificity >= 0:
            selected.extend(rules)
    u = urlsplit(url)
    target = u.path + ('?' + u.query if u.query else '')
    matched = []
    for allow, pattern in selected:
        expr = re.escape(pattern.rstrip('$')).replace(r'\*', '.*')
        if pattern.endswith('$'):
            expr += '$'
        if re.match(expr, target):
            matched.append((len(pattern.replace('*', '').rstrip('$')), allow))
    return max(matched, default=(0, True))[1]


def listing_url(store, value):
    """Parametros publicos de busca/paginacao, sem ampliar URLs de produtos."""
    u = urlsplit(value)
    if u.fragment or u.username or u.password or any(c.isspace() for c in value):
        raise ValueError('Listagem invalida')
    base = u._replace(query='').geturl()
    store_url(store, base)
    allowed = {
        'KaBuM!': {'page_number', 'page_size', 'search-term'},
        'Pichau': {'page'},
        'Mercado Livre': set(),
        'TerabyteShop': {'pagina'},
        'Amazon Brasil': {'k', 'page'},
        'Magalu': {'page'},
        'Fast Shop': {'q', 'page'},
        'GK InfoStore': {'q', 'page'},
    }[store]
    params = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
    if len(dict(params)) != len(params):
        raise ValueError('Parametros repetidos')
    for key, val in params:
        if key not in allowed:
            raise ValueError('Parametro de listagem invalido')
        if key in ('k', 'q', 'search-term'):
            if not re.fullmatch(r'[a-zA-Z0-9 -]{1,60}', val):
                raise ValueError('Busca invalida')
        elif not val.isascii() or not val.isdigit() or not 1 <= int(val) <= 100:
            raise ValueError('Pagina invalida')
    return value


def fetch_public_html(store, url, request_delay=0, *, listing=False, browser=False, session=None):
    validate = listing_url if listing else store_url
    url = validate(store, url)
    own_session = session is None
    if session is None:
        session = transport.BrowserSession(lambda value: validate(store, value)) if browser else transport.Session()
    session.headers['User-Agent'] = AGENT
    robots_cache, visited = {}, set()
    try:
        for hop in range(3):
            if url in visited:
                return None, url, 'redirecionamento_circular', {}
            visited.add(url)
            if respect_robots():
                root = 'https://' + urlsplit(url).netloc
                if root not in robots_cache:
                    response = session.get(root+'/robots.txt', timeout=(10,20), allow_redirects=False)
                    if response.status_code not in (200,404):
                        return None, url, 'robots_http_'+str(response.status_code), _metadata(response)
                    text = response.text if response.status_code == 200 else ''
                    robots_cache[root] = text
                text = robots_cache[root]
                allowed = robots_allows(text, AGENT, url)
                if not allowed:
                    return None, url, 'robots_nao_permite', {}
            if request_delay:
                import time
                time.sleep(request_delay)
            response = session.get(url, timeout=(10,25), allow_redirects=False)
            meta = _metadata(response)
            if 300 <= response.status_code < 400:
                # KaBuM conserva o contrato anterior de no maximo duas requisicoes.
                if store == 'KaBuM!' and not listing:
                    return None, url, 'redirecionamento_http_'+str(response.status_code), meta
                location = getattr(response,'headers',{}).get('Location')
                if not isinstance(location,str) or not location:
                    return None, url, 'redirecionamento_sem_destino', meta
                destination = urljoin(url,location)
                target = urlsplit(destination)
                meta.update(redirect_host=target.hostname, redirect_path=target.path)
                if re.search(r'/(gz|jms|auth|account|login|registration|customer|checkout|security|challenge)(/|$)',target.path,re.I):
                    return None, url, 'redirecionamento_autenticacao', meta
                try:
                    destination = validate(store,destination)
                except ValueError:
                    return None, url, 'redirecionamento_fora_da_loja', meta
                if hop == 2:
                    return None, url, 'redirecionamento_limite', meta
                url = destination
                continue
            if response.status_code != 200:
                if response.status_code == 423 and 'loja bloqueada' in response.text.lower():
                    return None, url, 'loja_indisponivel', meta
                return None, url, 'pagina_http_'+str(response.status_code), meta
            if urlsplit(response.url).netloc != urlsplit(url).netloc:
                return None, url, 'redirecionamento_fora_da_loja', meta
            if browser:
                try:
                    validate(store, response.url)
                except ValueError:
                    return None, url, 'redirecionamento_fora_da_loja', meta
                if re.search(r'/(auth|account|login|checkout|customer|captcha|challenge)(/|$)',
                             urlsplit(response.url).path, re.I):
                    return None, url, 'redirecionamento_autenticacao', meta
                url = response.url
            page = Selector(response.text, url=url)
            title = (page.css('title::text').get() or '').lower()
            headers = getattr(response,'headers',{})
            if (headers.get('CF-Mitigated', headers.get('cf-mitigated')) == 'challenge'
                    or any(word in title for word in ('captcha','access denied','just a moment','verifique','acesso negado', 'robot check'))
                    or page.css('form[action*="validateCaptcha"], #captchacharacters, #challenge-form, iframe[src*="captcha"]')
                    or 'sorry, we just need to make sure you' in page.get_all_text().lower()):
                return None, url, 'desafio_de_acesso', meta
            return response.text, url, 'ok', meta
    except transport.RequestException as exc:
        return None, url, 'rede_'+type(exc).__name__, {}
    finally:
        if own_session:
            session.close()


def collect_sample(store, limit=2, override_url=None, with_metadata=False, request_delay=0):
    result = _collect_sample(store,limit,override_url,request_delay)
    return result if with_metadata else result[:2]


def _collect_sample(store, limit=2, override_url=None, request_delay=0):
    url, parser = STORES[store]
    if not 1 <= limit <= 3:
        raise ValueError('Limite de um a tres produtos')
    html, final_url, status, meta = fetch_public_html(store,override_url or url,request_delay)
    if status != 'ok':
        return [], status, meta
    try:
        unique = {}
        for item in parser(html,final_url):
            try:
                item = normalize(item)
            except ValueError:
                continue
            unique.setdefault(item['link'],item)
            if len(unique) >= limit:
                break
        return list(unique.values()), 'ok' if unique else 'markup_sem_ofertas_reconhecidas', meta
    except ValueError:
        return [], 'markup_ou_pagina_recusada', meta


def _metadata(response):
    headers = getattr(response,'headers',{})
    return {'http_status':response.status_code,'retry_after':headers.get('Retry-After')}
