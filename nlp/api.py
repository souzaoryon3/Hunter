"""Catalogo publico analisado: sugestoes e agregacao textual com precos minerados."""
from fastapi import APIRouter, Depends, HTTPException, Query

from nlp.analysis import ALGORITHM, query_tokens

LATEST = '''SELECT DISTINCT ON (r.produto_id) r.*,o.nome,o.disponivel,p.loja
    FROM hunter_text_results r
    JOIN hunter_price_observations o ON o.id=r.observation_id
    JOIN hunter_catalog_products p ON p.id=r.produto_id
    WHERE p.channel='retail' AND r.event_time<=now()
    ORDER BY r.produto_id,r.event_time DESC,r.observation_id DESC'''


def create_router(get_db):
    router = APIRouter()

    async def require_schema(conn):
        if not await conn.fetchval("SELECT to_regclass('hunter_text_results')"):
            raise HTTPException(503, 'Analise textual exige migracao 009 e consumidor PLN.')

    @router.get('/sugestoes', tags=['PLN'])
    async def suggestions(q:str=Query(...,min_length=2,max_length=80),
                          limite:int=Query(8,ge=1,le=10),conn=Depends(get_db)):
        terms = query_tokens(q)
        await require_schema(conn)
        if not terms:
            return {'sugestoes':[], 'algoritmo':ALGORITHM}
        rows = await conn.fetch('''WITH latest AS ('''+LATEST+'''), matching AS (
            SELECT * FROM latest r WHERE disponivel AND length(nome)<=255
            AND NOT EXISTS(SELECT 1 FROM unnest($1::text[]) term
                WHERE NOT EXISTS(SELECT 1 FROM unnest(r.tokens) word WHERE word LIKE term||'%')))
            SELECT DISTINCT ON (normalized_text) nome AS texto,category AS categoria,produto_id
            FROM matching ORDER BY normalized_text,produto_id LIMIT $2''', terms, limite)
        return {'sugestoes':[dict(row) for row in rows], 'algoritmo':ALGORITHM}

    @router.get('/nlp/analises', tags=['PLN'])
    async def results(produto_id:int|None=Query(None,gt=0),
                      limite:int=Query(20,ge=1,le=100),conn=Depends(get_db)):
        await require_schema(conn)
        rows = await conn.fetch('''SELECT r.*,o.nome FROM hunter_text_results r
            JOIN hunter_price_observations o ON o.id=r.observation_id
            WHERE ($1::bigint IS NULL OR r.produto_id=$1)
            ORDER BY r.processed_at DESC,r.observation_id DESC LIMIT $2''', produto_id, limite)
        counts = await conn.fetch('SELECT status,count(*) total FROM hunter_nlp_events GROUP BY status')
        return {'tecnica':'classificacao tematica por regras e extracao de palavras-chave',
                'estados_globais':{r['status']:r['total'] for r in counts},
                'resultados':[dict(row) for row in rows],
                'aviso':'Classificacao deterministica exploratoria; nao e modelo treinado nem analise de sentimento.'}

    @router.get('/analytics/categorias', tags=['Data Mining'])
    async def category_statistics(conn=Depends(get_db)):
        await require_schema(conn)
        rows = await conn.fetch('''WITH latest AS ('''+LATEST+''')
            SELECT r.category AS categoria,count(*) AS produtos,
                count(a.observation_id) AS precos_analisados,
                avg(a.change_percent) AS variacao_media_percentual,
                count(*) FILTER(WHERE a.drop_detected) AS quedas_detectadas
            FROM latest r LEFT JOIN hunter_analytics_results a USING(observation_id)
            GROUP BY r.category ORDER BY produtos DESC,r.category''')
        return {'categorias':[dict(row) for row in rows],
                'escopo':'Ultima analise textual por oferta retail, associada ao resultado numerico do mesmo evento.',
                'aviso':'Variacao nula significa ausencia de comparacao, nao estabilidade. Sem equivalencia de SKU entre lojas.'}

    return router
