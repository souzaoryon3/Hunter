"""Rodada limitada no scheduler existente; nenhum HTTP em transacao PostgreSQL."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from catalog_expansion.adapters import ADAPTERS, FetchResult
from catalog_expansion.repository import CandidateRepository, canonical_url
from scraping.catalog_store import save_observations
from catalog_expansion.constants import COLLECTION_LOCK as LOCK

log=logging.getLogger('hunter.rotation')


async def seed_existing(conn,config,journal):
    """Admite apenas produtos existentes dos alvos ativos, sem coletar/alterar historico."""
    repo=CandidateRepository(conn)
    async with conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(281237)')
        source=await conn.fetchrow("SELECT * FROM hunter_catalog_sources WHERE code='kabum_public'")
        created=source is None
        if created:
            source=await repo.create_source('kabum_public','KaBuM!','public_page',['www.kabum.com.br'],
                config.interval,6,config.delay)
            await conn.execute('''UPDATE hunter_catalog_sources SET adapter='kabum_public',state='enabled',
                permission_reference='existing_public_product_monitoring:CONTINUIDADE.md' WHERE id=$1''',source['id'])
        count=0; stamps=[]
        for target in config.targets():
            if target['store']!='KaBuM!':
                continue
            product=await conn.fetchrow('''SELECT p.id,p.link,max(o.coletado_em) last_seen
                FROM hunter_catalog_products p JOIN hunter_price_observations o ON o.produto_id=p.id
                WHERE p.loja=$1 AND p.link=$2 GROUP BY p.id''',target['store'],target['url'])
            if product is None:
                continue
            import re
            external=re.search(r'/produto/(\d+)',product['link']).group(1)
            row=await repo.add(source['id'],product['link'],external_id=external,
                origin='existing_catalog',product_id=product['id'])
            # Somente aumenta prazo; repeticao nao antecipa cooldown nem reseta estado.
            due=product['last_seen']+timedelta(seconds=max(config.interval,source['interval_seconds']))
            old=journal.data['targets'].get(target['key'],{}).get('next_due')
            shop_due=journal.data['stores'].get(target['store'])
            for value in (old,shop_due):
                if value:
                    due=max(due,datetime.fromisoformat(value))
            await conn.execute('''UPDATE hunter_catalog_candidates SET next_attempt_at=GREATEST(next_attempt_at,$2)
                WHERE id=$1''',row['id'],due)
            stamps.append(product['last_seen']); count+=1
        if created and stamps:
            await conn.execute('''UPDATE hunter_catalog_sources SET window_started_at=$2,
                products_in_window=$3,http_in_window=$3*2 WHERE id=$1''',source['id'],max(stamps),min(count,6))
            await conn.execute('''UPDATE hunter_collection_control SET next_round_at=GREATEST(next_round_at,$1)''',
                min(stamps)+timedelta(seconds=config.interval))
        return count


async def reserve(conn,owner,adapters):
    """Fonte e candidato travados juntos; quotas persistem inclusive em crash."""
    repo=CandidateRepository(conn)
    async with conn.transaction():
        row=await conn.fetchrow('''SELECT c.id,s.id source_id FROM hunter_catalog_candidates c
            JOIN hunter_catalog_sources s ON s.id=c.source_id
            WHERE s.state='enabled' AND s.channel='retail' AND s.permission_reference IS NOT NULL
              AND s.http_request_limit>=2
              AND s.adapter=ANY($1::text[]) AND c.state IN ('pending','active','backoff')
              AND c.next_attempt_at<=clock_timestamp()
              AND (c.lease_expires_at IS NULL OR c.lease_expires_at<=clock_timestamp())
              AND (s.suspended_until IS NULL OR s.suspended_until<=clock_timestamp())
              AND (s.next_request_at IS NULL OR s.next_request_at<=clock_timestamp())
              AND (s.window_started_at IS NULL OR s.window_started_at+s.interval_seconds*interval '1 second'<=clock_timestamp()
                   OR (s.products_in_window<s.request_limit AND s.http_in_window+2<=s.http_request_limit))
            ORDER BY c.next_attempt_at,c.id LIMIT 1 FOR UPDATE OF c,s SKIP LOCKED''',list(adapters))
        if row is None:
            return None
        source=await conn.fetchrow('SELECT * FROM hunter_catalog_sources WHERE id=$1',row['source_id'])
        now=await conn.fetchval('SELECT clock_timestamp()')
        reset=source['window_started_at'] is None or source['window_started_at']+timedelta(seconds=source['interval_seconds'])<=now
        # Mesmo apos reset, quotas menores que custo maximo nao autorizam requisicao.
        if source['http_request_limit']<2:
            return None
        items=await repo.claim(owner,1,300,candidate_id=row['id'])
        if not items:
            return None
        await conn.execute('''UPDATE hunter_catalog_sources SET window_started_at=$2,
            products_in_window=$3,http_in_window=$4,
            next_request_at=clock_timestamp()+request_delay_seconds*interval '1 second' WHERE id=$1''',
            source['id'],now if reset else source['window_started_at'],
            1 if reset else source['products_in_window']+1,2 if reset else source['http_in_window']+2)
        await conn.execute('UPDATE hunter_catalog_runs SET http_requests_reserved=2 WHERE id=$1',items[0]['lease_token'])
        return source,items[0]


async def collect_rotation(conn,config,adapters=None):
    if not config.enabled:
        return []
    if not await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',LOCK):
        return []
    results=[];adapters=ADAPTERS if adapters is None else adapters
    try:
        # Checkpoint de rodada persiste mesmo em queda do processo.
        due=await conn.fetchval('SELECT next_round_at<=clock_timestamp() FROM hunter_collection_control')
        if not due:
            return []
        repo=CandidateRepository(conn)
        for _ in range(config.limit):
            async with conn.transaction():
                reservation=await reserve(conn,'scheduler_'+str(os.getpid()),adapters)
                if reservation is not None and not results:
                    await conn.execute('''UPDATE hunter_collection_control SET
                        next_round_at=clock_timestamp()+$1*interval '1 second' ''',config.interval)
            if reservation is None:
                break
            source,candidate=reservation
            try:
                response=await asyncio.to_thread(adapters[source['adapter']],dict(source),dict(candidate))
                if not isinstance(response,FetchResult):
                    raise ValueError('Contrato de adaptador invalido')
            except Exception:
                response=FetchResult([],'network_error')
            blocked=(response.http_status in (401,403) or any(x in response.status for x in ('robots_','desafio','redirecionamento')))
            limited=response.http_status==429
            result='blocked' if blocked else ('success' if response.status=='ok' and response.items else 'failed')
            error=None if result=='success' else ('access_denied' if blocked else 'rate_limited' if limited else
                'network' if response.status=='network_error' or response.status.startswith('rede_') else
                'http_error' if response.http_status and response.http_status>=400 else 'invalid_data')
            try:
                async with conn.transaction():
                    # Lock e fencing ANTES de gravar observacoes; finish e persistencia
                    # participam da mesma transacao externa.
                    live=await conn.fetchval('''SELECT id FROM hunter_catalog_candidates WHERE id=$1
                        AND lease_token=$2 AND lease_expires_at>clock_timestamp() FOR UPDATE''',candidate['id'],candidate['lease_token'])
                    if live is None:
                        raise ValueError('Lease vencido')
                    inserted=0
                    if result=='success':
                        if len(response.items)!=1:
                            raise ValueError('Uma oferta por candidato')
                        item=response.items[0]
                        if (canonical_url(item['link'],source['allowed_hosts'])!=candidate['canonical_url']
                                or not item.get('imagem_url') or item.get('channel','retail')!=source['channel']):
                            raise ValueError('Oferta fora da identidade ou sem imagem')
                        inserted=await save_observations(conn,source['loja'],response.items)
                        pid=await conn.fetchval('SELECT id FROM hunter_catalog_products WHERE loja=$1 AND link=$2',source['loja'],item['link'])
                        if candidate['product_id'] not in (None,pid):
                            raise ValueError('Identidade divergente')
                        await conn.execute('UPDATE hunter_catalog_candidates SET product_id=$2 WHERE id=$1',candidate['id'],pid)
                    await repo.finish(candidate['id'],candidate['lease_token'],result,
                        http_status=response.http_status,observations_inserted=inserted,error=error)
                    if result!='success':
                        now=await conn.fetchval('SELECT clock_timestamp()')
                        wait=min(604800,source['interval_seconds']*2**min(candidate['attempts'],3))
                        until=now+timedelta(seconds=max(wait,86400 if limited or blocked else 0))
                        if response.retry_after:
                            until=max(until,response.retry_after)
                        await conn.execute('''UPDATE hunter_catalog_candidates SET next_attempt_at=GREATEST(next_attempt_at,$2)
                            WHERE id=$1''',candidate['id'],until)
                        if blocked or limited:
                            await conn.execute('''UPDATE hunter_catalog_sources SET suspended_until=$2,
                                state=CASE WHEN $3 THEN 'blocked' ELSE state END WHERE id=$1''',source['id'],until,blocked)
                results.append({'candidate_id':candidate['id'],'result':result,'observations':inserted})
            except ValueError:
                # Nada da captura foi gravado se validacao/fencing falhou.
                try:
                    await repo.finish(candidate['id'],candidate['lease_token'],'failed',error='invalid_data')
                except ValueError:
                    pass
                results.append({'candidate_id':candidate['id'],'result':'failed','observations':0})
            log.info('Rotacao candidato=%s resultado=%s observacoes=%s',candidate['id'],results[-1]['result'],results[-1]['observations'])
            await asyncio.sleep(max(config.delay,source['request_delay_seconds']))
        return results
    finally:
        await conn.fetchval('SELECT pg_advisory_unlock($1::bigint)',LOCK)
