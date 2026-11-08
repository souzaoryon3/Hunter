"""Fila persistente sem coletor ou integracao com scheduler.

Uma conexao asyncpg por operacao concorrente. Erros armazenados sao codigos
fechados: nunca passe excecoes, corpos HTTP ou credenciais para a persistencia.
"""
import re
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ERRORS = frozenset(('timeout', 'network', 'http_error', 'access_denied',
                    'rate_limited', 'invalid_data', 'lease_expired', 'manual_rejection'))
STATES = frozenset(('pending', 'active', 'backoff', 'blocked', 'rejected', 'paused'))
TRANSITIONS = {
    'pending': {'paused', 'rejected', 'blocked'},
    'active': {'paused', 'rejected', 'blocked'},
    'backoff': {'paused', 'rejected', 'blocked'},
    'blocked': {'pending', 'paused', 'rejected'},
    'paused': {'pending', 'rejected'},
    'rejected': {'pending'},
}


def canonical_url(url, allowed_hosts):
    """Normalizacao conservadora: identidade de query preservada, tracking removido.

    Slugs diferentes so sao equivalentes com external_id verificado. Nao infere
    identidade por nome nem remove parametros de vendedor/variante.
    """
    try:
        parts = urlsplit(url)
        if (len(url) > 4000 or any(ord(c) < 33 for c in url) or '\\' in url
                or parts.scheme != 'https' or parts.username or parts.password
                or parts.port not in (None, 443) or parts.hostname not in allowed_hosts):
            raise ValueError()
        pairs = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=50)
        if any(re.search(r'token|secret|password|credential|authorization|api.?key|signature', k, re.I)
               for k, _ in pairs):
            raise ValueError()
        query = urlencode([(k, v) for k, v in pairs
                           if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid')])
        return urlunsplit(('https', parts.hostname, parts.path or '/', query, ''))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('URL publica HTTPS invalida ou host nao permitido.') from None


def error_code(value):
    if value is not None and value not in ERRORS:
        raise ValueError('Use somente codigo de erro permitido, sem texto livre.')
    return value


class CandidateRepository:
    def __init__(self, connection):
        self.conn = connection

    async def create_source(self, code, loja, integration_type, allowed_hosts,
                            interval_seconds=21600, request_limit=1, request_delay_seconds=3):
        hosts = sorted(set(allowed_hosts))
        if not hosts or any(not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', h) for h in hosts):
            raise ValueError('Hosts devem ser nomes exatos, sem URLs ou credenciais.')
        if await self.conn.fetchval("SELECT to_regclass('hunter_catalog_shops') IS NOT NULL"):
            await self.conn.execute('INSERT INTO hunter_catalog_shops(loja) VALUES($1) ON CONFLICT DO NOTHING',loja)
        return await self.conn.fetchrow('''INSERT INTO hunter_catalog_sources
            (code,loja,integration_type,allowed_hosts,interval_seconds,request_limit,request_delay_seconds)
            VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *''',
            code, loja, integration_type, hosts, interval_seconds, request_limit, request_delay_seconds)

    async def add(self, source_id, url, *, external_id=None, seller='', variant='',
                  origin='manual', product_id=None):
        async with self.conn.transaction():
            # Serializa admissoes da mesma fonte (sem HTTP), incluindo identidades
            # externas e URLs simultaneas que poderiam produzir conflitos cruzados.
            source = await self.conn.fetchrow('SELECT * FROM hunter_catalog_sources WHERE id=$1 FOR UPDATE', source_id)
            if source is None:
                raise ValueError('Fonte inexistente.')
            canonical = canonical_url(url, source['allowed_hosts'])
            if external_id is not None and not external_id.strip():
                raise ValueError('Identificador externo vazio.')
            if product_id is not None and not await self.conn.fetchval(
                    'SELECT EXISTS(SELECT 1 FROM hunter_catalog_products WHERE id=$1 AND loja=$2)', product_id, source['loja']):
                raise ValueError('Produto inexistente ou de outra loja.')
            matches = await self.conn.fetch('''SELECT * FROM hunter_catalog_candidates
                WHERE source_id=$1 AND (canonical_url=$2 OR
                ($3::text IS NOT NULL AND external_id=$3 AND seller=$4 AND variant=$5)) FOR UPDATE''',
                source_id, canonical, external_id, seller, variant)
            if len(matches) > 1:
                raise ValueError('URL e identidade apontam para candidatos diferentes; revisar manualmente.')
            if matches:
                row = matches[0]
                if ((external_id is not None and row['external_id'] not in (None, external_id))
                        or row['seller'] != seller or row['variant'] != variant
                        or (product_id is not None and row['product_id'] not in (None, product_id))):
                    raise ValueError('Identidade conflitante; revisar manualmente.')
                return await self.conn.fetchrow('''UPDATE hunter_catalog_candidates
                    SET external_id=COALESCE(external_id,$2),product_id=COALESCE(product_id,$3)
                    WHERE id=$1 RETURNING *''', row['id'], external_id, product_id)
            # URL original publica permanece sem fragmento; rejeita queries secretas
            # acima. Nao recebe links de afiliado assinados nem URLs autenticadas.
            original = urlunsplit(urlsplit(url)._replace(fragment=''))
            return await self.conn.fetchrow('''INSERT INTO hunter_catalog_candidates
                (source_id,original_url,canonical_url,external_id,seller,variant,origin,product_id)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *''',
                source_id, original, canonical, external_id, seller, variant, origin, product_id)

    async def list(self, state=None, eligible=False, limit=100):
        if state is not None and state not in STATES:
            raise ValueError('Estado invalido.')
        if not 1 <= limit <= 500:
            raise ValueError('Limite invalido.')
        return await self.conn.fetch('''SELECT c.* FROM hunter_catalog_candidates c
            JOIN hunter_catalog_sources s ON s.id=c.source_id
            WHERE ($1::text IS NULL OR c.state=$1) AND (NOT $2::boolean OR
            (s.state='enabled' AND c.state IN ('pending','active','backoff')
             AND c.next_attempt_at<=clock_timestamp()
             AND (c.lease_expires_at IS NULL OR c.lease_expires_at<=clock_timestamp())))
            ORDER BY c.next_attempt_at,c.id LIMIT $3''', state, eligible, limit)

    async def transition(self, candidate_id, state, reason=None):
        error_code(reason)
        async with self.conn.transaction():
            row = await self.conn.fetchrow('SELECT * FROM hunter_catalog_candidates WHERE id=$1 FOR UPDATE', candidate_id)
            if row is None or state not in TRANSITIONS[row['state']]:
                raise ValueError('Transicao invalida.')
            if row['lease_token'] is not None:
                raise ValueError('Candidato reservado; finalizar ou recuperar lease primeiro.')
            if state == 'rejected' and reason is None:
                raise ValueError('Rejeicao exige motivo permitido.')
            return await self.conn.fetchrow('''UPDATE hunter_catalog_candidates
                SET state=$2,error_code=$3 WHERE id=$1 RETURNING *''', candidate_id,state,reason)

    async def claim(self, owner, limit=1, lease_seconds=300, candidate_id=None):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', owner) or not 1 <= limit <= 6 or not 30 <= lease_seconds <= 1800:
            raise ValueError('Parametros de lease invalidos.')
        async with self.conn.transaction():
            rows = await self.conn.fetch('''SELECT c.* FROM hunter_catalog_candidates c
                JOIN hunter_catalog_sources s ON s.id=c.source_id
                WHERE s.state='enabled' AND c.state IN ('pending','active','backoff')
                AND c.next_attempt_at<=clock_timestamp()
                AND (c.lease_expires_at IS NULL OR c.lease_expires_at<=clock_timestamp())
                AND ($2::bigint IS NULL OR c.id=$2)
                ORDER BY c.next_attempt_at,c.id LIMIT $1 FOR UPDATE OF c SKIP LOCKED''', limit,candidate_id)
            claimed = []
            for row in rows:
                await self.conn.execute('''UPDATE hunter_catalog_runs SET result='expired',
                    error_code='lease_expired',finished_at=GREATEST(clock_timestamp(),started_at)
                    WHERE candidate_id=$1 AND result='running' ''', row['id'])
                token = uuid4()
                item = await self.conn.fetchrow('''UPDATE hunter_catalog_candidates
                    SET attempts=attempts+1,last_attempt_at=statement_timestamp(),lease_token=$2,
                    lease_owner=$3,lease_expires_at=statement_timestamp()+$4*interval '1 second',
                    next_attempt_at=statement_timestamp()+(SELECT interval_seconds FROM hunter_catalog_sources
                        WHERE id=source_id)*interval '1 second'
                    WHERE id=$1 RETURNING *''', row['id'],token,owner,lease_seconds)
                await self.conn.execute('INSERT INTO hunter_catalog_runs(id,candidate_id) VALUES($1,$2)', token,row['id'])
                claimed.append(item)
            return claimed

    async def finish(self, candidate_id, token, result, *, http_status=None,
                     observations_inserted=0, error=None):
        error_code(error)
        if (result not in ('success','failed','blocked') or observations_inserted < 0
                or (http_status is not None and not 100 <= http_status <= 599)
                or (result != 'success' and (error is None or observations_inserted != 0))
                or (result == 'success' and (error is not None or (http_status is not None and http_status >= 400)))):
            raise ValueError('Resultado inconsistente.')
        async with self.conn.transaction():
            row = await self.conn.fetchrow('''SELECT c.*,s.interval_seconds FROM hunter_catalog_candidates c
                JOIN hunter_catalog_sources s ON s.id=c.source_id
                WHERE c.id=$1 AND c.lease_token=$2 AND c.lease_expires_at>clock_timestamp()
                FOR UPDATE OF c''', candidate_id, token)
            if row is None or row['lease_expires_at'] <= await self.conn.fetchval('SELECT clock_timestamp()'):
                raise ValueError('Lease expirado ou substituido; resultado recusado.')
            state = {'success':'active','failed':'backoff','blocked':'blocked'}[result]
            await self.conn.execute('''UPDATE hunter_catalog_runs SET result=$2,http_status=$3,
                observations_inserted=$4,error_code=$5,finished_at=GREATEST(clock_timestamp(),started_at)
                WHERE id=$1 AND result='running' ''', token,result,http_status,observations_inserted,error)
            return await self.conn.fetchrow('''UPDATE hunter_catalog_candidates SET state=$2,error_code=$3,
                last_verified_at=CASE WHEN $2='active' THEN clock_timestamp() ELSE last_verified_at END,
                next_attempt_at=GREATEST(next_attempt_at,clock_timestamp()+$4*interval '1 second'),
                lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id=$1 RETURNING *''',
                candidate_id,state,error,row['interval_seconds'])

    async def runs(self, candidate_id, limit=100):
        if not 1 <= limit <= 500:
            raise ValueError('Limite invalido.')
        return await self.conn.fetch('''SELECT * FROM hunter_catalog_runs WHERE candidate_id=$1
            ORDER BY started_at DESC,id LIMIT $2''', candidate_id,limit)
