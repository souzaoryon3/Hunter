"""Consultas explicitas para cada versao de esquema. Sem JWT ou HTTP."""
CATALOGO = """
    SELECT nome, preco, link, 'KaBuM!'::text AS loja,
        NULL::numeric AS preco_cartao, NULL::text AS pagamento, NULL::boolean AS frete_gratis,
        NULL::text AS frete_observacao, NULL::timestamptz AS coletado_em, 'legado_sem_data'::text AS fonte_coleta,
        NULL::bigint AS produto_id, NULL::text AS imagem_url, FALSE AS preco_verificado,
        FALSE AS historico_disponivel
    FROM (SELECT DISTINCT ON (nome,link) * FROM produtos_kabum ORDER BY nome,link,id DESC) k
    UNION ALL
    SELECT nome, preco, link, 'Mercado Livre'::text AS loja,
        NULL::numeric, NULL::text, NULL::boolean, NULL::text, NULL::timestamptz, 'legado_sem_data'::text,
        NULL::bigint, NULL::text, FALSE, FALSE
    FROM (SELECT DISTINCT ON (link) * FROM produtos_mercadolivre ORDER BY link,id DESC) m
    UNION ALL
    SELECT nome, preco::double precision, link, 'Pichau'::text AS loja,
        preco_cartao, pagamento, frete_gratis, frete_observacao, coletado_em, fonte_coleta,
        NULL::bigint, NULL::text, TRUE, FALSE
    FROM produtos_pichau WHERE disponivel
"""

CATALOGO_OBSERVADO = """
    WITH latest AS (
        SELECT DISTINCT ON (produto_id) * FROM hunter_price_observations
        ORDER BY produto_id, coletado_em DESC, id DESC
    )
    SELECT o.nome, o.preco::double precision AS preco, p.link, p.loja,
        o.preco_cartao, o.pagamento, o.frete_gratis, o.frete_observacao,
        o.coletado_em, o.fonte_coleta, p.id AS produto_id, o.imagem_url,
        TRUE AS preco_verificado, TRUE AS historico_disponivel
    FROM hunter_catalog_products p JOIN latest o ON o.produto_id=p.id
    WHERE o.disponivel
    UNION ALL
    SELECT l.* FROM (
    SELECT nome, preco, link, 'KaBuM!'::text AS loja,
        NULL::numeric AS preco_cartao, NULL::text AS pagamento, NULL::boolean AS frete_gratis,
        NULL::text AS frete_observacao, NULL::timestamptz AS coletado_em, 'legado_sem_data'::text AS fonte_coleta,
        NULL::bigint AS produto_id, NULL::text AS imagem_url, FALSE AS preco_verificado,
        FALSE AS historico_disponivel
    FROM (SELECT DISTINCT ON (nome,link) * FROM produtos_kabum ORDER BY nome,link,id DESC) k
    UNION ALL
    SELECT nome, preco, link, 'Mercado Livre'::text AS loja,
        NULL::numeric, NULL::text, NULL::boolean, NULL::text, NULL::timestamptz, 'legado_sem_data'::text,
        NULL::bigint, NULL::text, FALSE, FALSE
    FROM (SELECT DISTINCT ON (link) * FROM produtos_mercadolivre ORDER BY link,id DESC) m
    UNION ALL
    SELECT nome, preco::double precision, link, 'Pichau'::text AS loja,
        preco_cartao, pagamento, frete_gratis, frete_observacao, coletado_em, fonte_coleta,
        NULL::bigint, NULL::text, TRUE, FALSE
    FROM produtos_pichau WHERE disponivel
) l
    WHERE NOT EXISTS (SELECT 1 FROM hunter_catalog_products p WHERE p.loja=l.loja AND p.link=l.link)
"""

CATALOGO_MULTISTORE = """
    WITH latest AS (
        SELECT DISTINCT ON (produto_id) * FROM hunter_price_observations
        ORDER BY produto_id, coletado_em DESC, id DESC
    )
    SELECT o.nome, o.preco::double precision AS preco, p.link, p.loja,
        o.preco_cartao, o.pagamento, o.frete_gratis, o.frete_observacao,
        o.coletado_em, o.fonte_coleta, p.id AS produto_id, o.imagem_url,
        TRUE AS preco_verificado, TRUE AS historico_disponivel,p.channel,o.price_kind,o.promotion_terms
    FROM hunter_catalog_products p JOIN latest o ON o.produto_id=p.id
    WHERE o.disponivel AND p.channel='retail'
    UNION ALL
    SELECT l.*,'retail'::text AS channel,'regular'::text AS price_kind,NULL::text AS promotion_terms FROM (
    SELECT nome, preco, link, 'KaBuM!'::text AS loja,
        NULL::numeric AS preco_cartao, NULL::text AS pagamento, NULL::boolean AS frete_gratis,
        NULL::text AS frete_observacao, NULL::timestamptz AS coletado_em, 'legado_sem_data'::text AS fonte_coleta,
        NULL::bigint AS produto_id, NULL::text AS imagem_url, FALSE AS preco_verificado,
        FALSE AS historico_disponivel
    FROM (SELECT DISTINCT ON (nome,link) * FROM produtos_kabum ORDER BY nome,link,id DESC) k
    UNION ALL
    SELECT nome, preco, link, 'Mercado Livre'::text AS loja,
        NULL::numeric, NULL::text, NULL::boolean, NULL::text, NULL::timestamptz, 'legado_sem_data'::text,
        NULL::bigint, NULL::text, FALSE, FALSE
    FROM (SELECT DISTINCT ON (link) * FROM produtos_mercadolivre ORDER BY link,id DESC) m
    UNION ALL
    SELECT nome, preco::double precision, link, 'Pichau'::text AS loja,
        preco_cartao, pagamento, frete_gratis, frete_observacao, coletado_em, fonte_coleta,
        NULL::bigint, NULL::text, TRUE, FALSE
    FROM produtos_pichau WHERE disponivel
) l
    WHERE NOT EXISTS (SELECT 1 FROM hunter_catalog_products p WHERE p.loja=l.loja AND p.link=l.link)
"""

async def catalog_sql(conn):
    if await conn.fetchval("SELECT to_regclass('hunter_price_observations') IS NOT NULL"):
        if await conn.fetchval("SELECT to_regclass('hunter_catalog_shops') IS NOT NULL"):
            return CATALOGO_MULTISTORE
        return CATALOGO_OBSERVADO
    return CATALOGO

async def shops(conn):
    if await conn.fetchval("SELECT to_regclass('hunter_catalog_shops') IS NOT NULL"):
        return [r['loja'] for r in await conn.fetch('SELECT loja FROM hunter_catalog_shops ORDER BY loja')]
    return ['KaBuM!','Mercado Livre','Pichau']
