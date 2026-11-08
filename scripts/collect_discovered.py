"""Recupera descoberta KaBuM e revalida paginas publicas antes de persistir no esquema atual."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import asyncpg
import requests
from bs4 import BeautifulSoup
from catalog_expansion.repository import CandidateRepository
from catalog_expansion.constants import COLLECTION_LOCK
from scraping.buscar_produtoskabum import parse_html
from scraping.catalog_store import normalize, save_observations
from scraping.public_sources import AGENT


def public_get(session, robots, url):
    if not robots.can_fetch(AGENT,url):
        return None,'robots_disallows'
    time.sleep(3)
    response=session.get(url,timeout=(10,25),allow_redirects=False)
    if response.status_code != 200:
        return response,'http_'+str(response.status_code)
    soup=BeautifulSoup(response.text,'html.parser')
    title=soup.title.get_text(' ',strip=True).lower() if soup.title else ''
    if any(word in title for word in ('captcha','access denied','just a moment','verifique','acesso negado')):
        return response,'challenge'
    return response,'ok'


async def main(args):
    if args.operator_vault:
        from ops.secret_store import read
        dsn=read('runtime.dpapi')['DATABASE_URL']
    else:
        from config.settings import database_url
        dsn=database_url()
    target=urlsplit(dsn)
    if (target.hostname not in ('localhost','127.0.0.1','::1') or target.path!='/'+args.expect_database):
        raise ValueError('Destino local deve corresponder a --expect-database')
    if not 1<=args.max_products<=10 or not 1<=args.max_pages<=5 or not 1<=args.start_page<=100:
        raise ValueError('Lote limitado a10 produtos e5 paginas, uma requisicao a cada3s')
    conn=await asyncpg.connect(dsn)
    session=requests.Session();session.headers['User-Agent']=AGENT
    output=ROOT/'local-reports/discovery-live';output.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report={'created_at':stamp,'collected':[],'requests':[],'discovered_urls':[],'stopped':None}
    filename=output/('collection-'+stamp+'.json')
    def save():
        filename.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    locked=False
    try:
        if await conn.fetchval('SELECT current_database()')!=args.expect_database:
            raise ValueError('Banco divergente')
        locked=await conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',COLLECTION_LOCK)
        if not locked:raise ValueError('Coleta existente ativa; nao executar em paralelo')
        source=await conn.fetchrow("SELECT * FROM hunter_catalog_sources WHERE code='kabum_public'")
        if not source or source['state']!='enabled':raise ValueError('Fonte KaBuM nao habilitada; nao reativar bloqueios')
        existing=set(await conn.fetchval("SELECT coalesce(array_agg(link),ARRAY[]::text[]) FROM hunter_catalog_products WHERE loja='KaBuM!'"))
        response=session.get('https://www.kabum.com.br/robots.txt',timeout=(10,20),allow_redirects=False)
        report['requests'].append({'url':'https://www.kabum.com.br/robots.txt','http':response.status_code})
        if response.status_code not in (200,404):
            report['stopped']='robots_http_'+str(response.status_code);return
        robots=RobotFileParser();robots.parse(response.text.splitlines() if response.status_code==200 else [])
        seen=set()
        repo=CandidateRepository(conn)
        for page in range(args.start_page,args.start_page+args.max_pages):
            listing='https://www.kabum.com.br/perifericos' if page==1 else f'https://www.kabum.com.br/perifericos?page_number={page}&page_size=20&facet_filters=&sort=most_searched'
            if page==1 and args.discovery_html:
                # HTML antigo serve apenas para descobrir URLs; preco e imagem sao
                # obrigatoriamente recapturados na pagina pontual abaixo.
                html=Path(args.discovery_html).read_text(encoding='utf-8')
            else:
                response,status=public_get(session,robots,listing)
                report['requests'].append({'url':listing,'http':response.status_code if response is not None else None,'status':status})
                if status!='ok':report['stopped']=status;return
                html=response.text
                (output/(stamp+'-listing-'+str(page)+'.html')).write_text(html,encoding='utf-8')
            discovered=parse_html(html,listing)
            for item in discovered:
                url=item['link']
                if url in seen:continue
                seen.add(url);report['discovered_urls'].append(url)
                if url in existing:continue
                response,status=public_get(session,robots,url)
                captured=datetime.now(timezone.utc)
                report['requests'].append({'url':url,'http':response.status_code if response is not None else None,'status':status,'captured_at':captured.isoformat()})
                save()
                if status!='ok':
                    report['stopped']=status
                    if args.persist and (status=='challenge' or status in ('http_401','http_403','http_429')):
                        await conn.execute("UPDATE hunter_catalog_sources SET state=CASE WHEN $2 THEN 'blocked' ELSE state END,suspended_until=GREATEST(coalesce(suspended_until,clock_timestamp()),clock_timestamp()+interval '24 hours') WHERE id=$1",source['id'],status!='http_429')
                    return
                pid=re.search(r'/produto/(\d+)',url).group(1)
                path=output/(stamp+'-product-'+pid+'.html')
                path.write_text(response.text,encoding='utf-8')
                items=[normalize(r) for r in parse_html(response.text,url,captured_at=captured)]
                items=[r for r in items if r['disponivel'] and r.get('imagem_url')]
                if len(items)!=1:continue
                row=items[0]
                if args.persist:
                    async with conn.transaction():
                        await save_observations(conn,'KaBuM!',items)
                        product_id=await conn.fetchval("SELECT id FROM hunter_catalog_products WHERE loja='KaBuM!' AND link=$1",row['link'])
                        candidate=await repo.add(source['id'],row['link'],external_id=pid,origin='public_page',product_id=product_id)
                        # Monitoramento futuro conserva intervalo e prazos existentes.
                        await conn.execute("UPDATE hunter_catalog_candidates SET state='active',last_attempt_at=$2,last_verified_at=$2,next_attempt_at=GREATEST(next_attempt_at,$3) WHERE id=$1",candidate['id'],captured,captured+timedelta(seconds=source['interval_seconds']))
                else:product_id=None
                existing.add(row['link'])
                report['collected'].append({'produto_id':product_id,**row,'html_file':str(path.relative_to(ROOT))})
                save();print('Capturado produto='+pid+' imagem=sim preco='+str(row['preco']),flush=True)
                if len(report['collected'])>=args.max_products:return
    finally:
        save()
        print('Resultado:',len(report['collected']),'produtos;',len(report['discovered_urls']),'URLs descobertas; parada=',report['stopped'],'relatorio=',filename.relative_to(ROOT),flush=True)
        session.close()
        if locked:await conn.fetchval('SELECT pg_advisory_unlock($1::bigint)',COLLECTION_LOCK)
        await conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--operator-vault',action='store_true')
    p.add_argument('--expect-database',required=True)
    p.add_argument('--max-products',type=int,default=6)
    p.add_argument('--max-pages',type=int,default=5)
    p.add_argument('--start-page',type=int,default=1)
    p.add_argument('--discovery-html')
    p.add_argument('--persist',action='store_true')
    try:asyncio.run(main(p.parse_args()))
    except Exception as exc:
        print('Coleta interrompida:',type(exc).__name__,'(detalhes privados omitidos).')
        raise SystemExit(1) from None
