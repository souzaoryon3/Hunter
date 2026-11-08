"""Rotas publicas somente leitura; calculos fora do event loop do FastAPI."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from data_mining.analysis import statistics, analytical_history, cluster_products
from data_mining.demo import demo_rows
from data_mining.repository import observations


def create_router(get_db):
    router=APIRouter(prefix='/analytics',tags=['Data Mining'])

    async def dataset(conn,origin,days,product_id=None):
        if origin=='demo':
            cutoff=datetime.now(timezone.utc)-timedelta(days=days)
            return [r for r in demo_rows() if r['coletado_em']>=cutoff
                    and (product_id is None or r['produto_id']==product_id)]
        if not await conn.fetchval("SELECT to_regclass('hunter_price_observations') IS NOT NULL"):
            raise HTTPException(503,'Histórico observado ainda não ativado neste ambiente.')
        try:
            return await observations(conn,days,product_id)
        except ValueError as exc:
            raise HTTPException(413,str(exc)) from None

    def envelope(origin,days):
        return dict(origem=origin,sintetico=origin=='demo',dias=days,
                    aviso='Demonstração: dados sintéticos, sem relação com ofertas reais.' if origin=='demo'
                    else 'Somente observações reais datadas; catálogo legado sem data e fixtures excluídos.')

    @router.get('/estatisticas')
    async def stats(origem:Literal['real','demo']='real',dias:int=Query(90,ge=1,le=365),
                    produto_id:int|None=Query(None,gt=0),limiar:float=Query(5,ge=1,le=90),conn=Depends(get_db)):
        rows=await dataset(conn,origem,dias,produto_id)
        return {**envelope(origem,dias),**await run_in_threadpool(statistics,rows,None,limiar)}

    @router.get('/historico/{produto_id}')
    async def history(produto_id:int,origem:Literal['real','demo']='real',
                      dias:int=Query(90,ge=1,le=365),conn=Depends(get_db)):
        rows=await dataset(conn,origem,dias,produto_id)
        if origem=='demo':
            exists=1<=produto_id<=9
        else:
            exists=await conn.fetchval('SELECT EXISTS(SELECT 1 FROM hunter_catalog_products WHERE id=$1)',produto_id)
        if not exists:
            raise HTTPException(404,'Produto não encontrado nesta origem.')
        summary=await run_in_threadpool(statistics,rows)
        series=await run_in_threadpool(analytical_history,rows)
        return {**envelope(origem,dias),'produto':next(iter(summary['produtos']),None),
                'serie':series,'mensagem':summary['mensagem']}

    @router.get('/agrupamentos')
    async def clusters(origem:Literal['real','demo']='real',dias:int=Query(90,ge=1,le=365),
                       k:int=Query(3,ge=2,le=5),conn=Depends(get_db)):
        rows=await dataset(conn,origem,dias)
        return {**envelope(origem,dias),**await run_in_threadpool(cluster_products,rows,k)}

    return router
