"""Coleta uma pagina por loja, ate tres ofertas, sem contornar bloqueios."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import asyncpg
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraping.buscar_produtoskabum import parse_html as kabum_html
from scraping.buscar_produtosmercadolivre import parse_html as ml_html
from scraping.buscar_produtospichau import parse_html as pichau_html
from scraping.catalog_store import normalize, save_observations

from scraping.public_sources import STORES, collect_sample


async def run(args):
    conn = None
    try:
        if args.persist:
            if not args.expect_database or not os.environ.get('DATABASE_URL'):
                raise ValueError('Informe DATABASE_URL e --expect-database explicitamente')
            conn = await asyncpg.connect(os.environ['DATABASE_URL'],timeout=10)
            if await conn.fetchval('SELECT current_database()') != args.expect_database:
                raise ValueError('Destino divergente; nenhuma coleta executada')
            if not await conn.fetchval("SELECT to_regclass('hunter_price_observations') IS NOT NULL"):
                raise ValueError('Migracao 003 ausente')
        results = []
        for store in STORES:
            if args.store and store not in args.store:
                continue
            items, status = collect_sample(store,args.limit,args.url)
            before = await conn.fetchval('SELECT count(*) FROM hunter_price_observations') if conn else 0
            if conn and items:
                await save_observations(conn,store,items)
            added = (await conn.fetchval('SELECT count(*) FROM hunter_price_observations')-before) if conn else 0
            row = dict(loja=store,status=status,produtos=len(items),com_imagem=sum(bool(p.get('imagem_url')) for p in items),
                       observacoes_gravadas=added,ofertas=items)
            results.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='ofertas'},ensure_ascii=True))
        target = Path(tempfile.gettempdir())/'HunterRuntime'/'collection003.json'
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(results,default=str,ensure_ascii=False),encoding='utf-8')
        print('Resultado local: '+str(target))
    finally:
        if conn:
            await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,choices=(1,2,3),default=2)
    parser.add_argument('--persist',action='store_true')
    parser.add_argument('--expect-database')
    parser.add_argument('--store',action='append',choices=tuple(STORES))
    parser.add_argument('--url',help='Pagina publica especifica; exige uma unica --store')
    try:
        args=parser.parse_args()
        if args.url and len(args.store or []) != 1:
            parser.error('--url exige exatamente uma --store')
        asyncio.run(run(args))
    except Exception as exc:
        print('Coleta interrompida: '+type(exc).__name__+'; confira destino/conectividade.',file=sys.stderr)
        raise SystemExit(1) from None
