"""Leitura parametrizada e limitada; sem DDL/DML ou dados legados sem data."""
REAL_SOURCES = ('html_publico', 'http_publico', 'html_publico_jsonld', 'captura_publica',
                'api_oficial_mercadolivre', 'scrapling_browser_card', 'scrapling_public_card')
MAX_ROWS = 20000


async def observations(conn, days=90, product_id=None):
    retail=" AND p.channel='retail'" if await conn.fetchval("SELECT to_regclass('hunter_catalog_shops') IS NOT NULL") else ''
    rows = await conn.fetch('''SELECT o.id,o.produto_id,p.loja,o.nome,o.preco,o.disponivel,
        o.coletado_em,o.fonte_coleta FROM hunter_price_observations o
        JOIN hunter_catalog_products p ON p.id=o.produto_id
        WHERE o.fonte_coleta=ANY($1::text[])
          AND o.coletado_em >= now()-$2 * interval '1 day' AND o.coletado_em <= now()
          AND ($3::bigint IS NULL OR o.produto_id=$3)
        '''+retail+''' ORDER BY o.coletado_em,o.id LIMIT $4''',list(REAL_SOURCES),days,product_id,MAX_ROWS+1)
    if len(rows)>MAX_ROWS:
        raise ValueError('Há mais de 20.000 observações. Reduza o período ou selecione um produto.')
    return [dict(row) for row in rows]
