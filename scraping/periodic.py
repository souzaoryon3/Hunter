"""Coleta supervisionada pelo scheduler existente; sem novo servico ou migracao."""
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg

from scraping.catalog_store import save_observations
from scraping.public_sources import STORES, collect_sample
from catalog_expansion.constants import COLLECTION_LOCK as LOCK
from config.settings import bounded_int

ROOT=Path(__file__).resolve().parents[1]
log=logging.getLogger('hunter.collection')


def target_key(store,url):
    match=re.search(r'/produto/(\d+)(?:/|$)',url) if store=='KaBuM!' else None
    identity=match.group(1) if match else url
    return hashlib.sha256((store+'|'+identity).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class CollectionSettings:
    enabled: bool = False
    interval: int = 21600
    limit: int = 6
    delay: int = 3
    targets_path: Path = ROOT/'config/collection_targets.json'

    @classmethod
    def environment(cls):
        enabled=os.environ.get('HUNTER_COLLECTION_ENABLED','0')
        if enabled not in ('0','1'):
            raise ValueError('HUNTER_COLLECTION_ENABLED deve ser 0 ou 1')
        bounded=bounded_int
        return cls(enabled=='1',bounded('HUNTER_COLLECTION_INTERVAL_SECONDS',21600,21600,604800),
                   bounded('HUNTER_COLLECTION_LIMIT',6,1,6),bounded('HUNTER_COLLECTION_DELAY_SECONDS',3,2,30),
                   Path(os.environ.get('HUNTER_COLLECTION_TARGETS',ROOT/'config/collection_targets.json')))

    def targets(self):
        data=json.loads(self.targets_path.read_text(encoding='utf-8'))
        targets=[];seen=set()
        for item in data['targets']:
            if type(item.get('enabled')) is not bool:
                raise ValueError('Alvo deve informar enabled booleano')
            if not item['enabled']:
                continue
            store,url=item['store'],item['url'];u=urlsplit(url)
            if (store not in STORES or u.scheme!='https' or u.netloc!=urlsplit(STORES[store][0]).netloc
                    or u.username or u.password or u.query or u.fragment or '%' in u.path or '..' in u.path):
                raise ValueError('Alvo fora das fontes publicas permitidas')
            if store=='KaBuM!' and not re.match(r'^/produto/\d+/',u.path):
                raise ValueError('KaBuM exige pagina pontual de produto')
            key=target_key(store,url)
            if key not in seen:
                targets.append(dict(store=store,url=url,key=key));seen.add(key)
        # Capacidade de cadastro e independente do lote limitado por config.limit.
        return targets


class Journal:
    def __init__(self,path):
        self.path=Path(path)
        self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'version':1,'targets':{},'stores':{}}
        if self.data.get('version')!=1 or not isinstance(self.data.get('targets'),dict) or not isinstance(self.data.get('stores'),dict):
            raise ValueError('Estado de coleta invalido; recusa para evitar repeticoes')

    def save(self):
        temporary=self.path.with_name(self.path.name+'.tmp')
        temporary.write_text(json.dumps(self.data,ensure_ascii=True),encoding='utf-8')
        os.replace(temporary,self.path)

    def due(self,key,store,now):
        values=[self.data['targets'].get(key,{}).get('next_due'),self.data['stores'].get(store)]
        return all(not value or datetime.fromisoformat(value)<=now for value in values)


def state_path(database_url):
    u=urlsplit(database_url)
    host='loopback' if u.hostname in ('localhost','127.0.0.1','::1') else u.hostname
    identity=f'{host}:{u.port or 5432}{u.path}'
    suffix=hashlib.sha256(identity.encode()).hexdigest()[:16]
    return ROOT/('.env.collection-state.'+suffix+'.json')


def is_blocked(status):
    return any(value in status for value in ('403','429','redirecionamento','desafio','robots_'))


async def collect_due(conn,config,journal,fetch=collect_sample,now=None):
    """Conn dedicado: trava de sessao, sem transacao aberta durante HTTP."""
    if not config.enabled:
        return []
    if not await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',LOCK):
        return []
    results=[];seen=set()
    try:
        if not await conn.fetchval("SELECT to_regclass('hunter_price_observations') IS NOT NULL"):
            raise ValueError('Migracao 003 ausente; coleta desativada')
        # Recarregar depois do lock: outro scheduler pode ter acabado de salvar.
        journal=Journal(journal.path)
        targets=config.targets()
        for target in targets:
            store,url,key=target['store'],target['url'],target['key']
            stamp=now or datetime.now(timezone.utc)
            if not journal.due(key,store,stamp):
                continue
            last=await conn.fetchval('''SELECT max(o.coletado_em) FROM hunter_catalog_products p
                JOIN hunter_price_observations o ON o.produto_id=p.id
                WHERE p.loja=$1 AND p.link=$2''',store,url)
            if last and last+timedelta(seconds=config.interval)>stamp:
                continue
            if len(results)>=config.limit:
                break
            previous=journal.data['targets'].get(key,{})
            run_id=uuid.uuid4().hex
            record=dict(run_id=run_id,store=store,status='claimed',started_at=stamp.isoformat(),
                        next_due=(stamp+timedelta(seconds=config.interval)).isoformat(),failures=previous.get('failures',0))
            journal.data['targets'][key]=record;journal.save()
            try:
                # Requests em thread separada: scan/outbox continuam no mesmo scheduler.
                items,status=await asyncio.to_thread(fetch,store,1,url)
                items=[item for item in items if (store,item['link']) not in seen]
                if status=='ok' and items:
                    inserted=await save_observations(conn,store,items)
                    seen.update((store,item['link']) for item in items)
                elif status=='ok':
                    status='ok_duplicado_ignorado'
                    inserted=0
                else:
                    inserted=0
                record.update(status=status,products=len(items) if status.startswith('ok') else 0,
                              images=sum(bool(p.get('imagem_url')) for p in items) if status.startswith('ok') else 0,
                              observations=inserted)
            except Exception as exc:
                record.update(status='failure_'+type(exc).__name__,products=0,images=0,observations=0)
            finished=now or datetime.now(timezone.utc)
            if record['status'].startswith('ok'):
                record['failures']=0
                wait=config.interval
            else:
                record['failures']+=1
                wait=min(604800,config.interval*2**min(record['failures'],3))
                if is_blocked(record['status']):
                    wait=max(wait,86400)
                    journal.data['stores'][store]=(finished+timedelta(seconds=wait)).isoformat()
            record.update(finished_at=finished.isoformat(),next_due=(finished+timedelta(seconds=wait)).isoformat())
            journal.save();results.append(dict(record,key=key))
            log.info('Coleta loja=%s alvo=%s status=%s produtos=%s imagens=%s',store,key,record['status'],record['products'],record['images'])
            if len(results)<config.limit:
                await asyncio.sleep(config.delay)
        return results
    finally:
        await conn.fetchval('SELECT pg_advisory_unlock($1::bigint)',LOCK)


async def run_collection(database_url,config):
    if not config.enabled:
        return []
    conn=await asyncpg.connect(database_url,timeout=10)
    try:
        if await conn.fetchval("SELECT to_regclass('hunter_collection_control') IS NOT NULL"):
            from catalog_expansion.rotation import collect_rotation
            return await collect_rotation(conn,config)
        return await collect_due(conn,config,Journal(state_path(database_url)))
    finally:
        await conn.close()
