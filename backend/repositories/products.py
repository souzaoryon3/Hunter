"""Catalogo compartilhado e consultas paginadas; nenhum HTTP ou coletor."""

from messaging.catalog import catalog_sql
from messaging.catalog import shops as shops


async def search(
    conn, name, min_price, max_price, store, order, free, observed, page, limit
):
    where = "WHERE strpos(lower(nome),lower($1))>0 AND ($2::double precision IS NULL OR preco >= $2) AND ($3::double precision IS NULL OR preco <= $3) AND ($4::text IS NULL OR loja=$4)"
    if free:
        where += " AND frete_gratis IS TRUE"
    params = [name, min_price, max_price, store]
    catalog = await catalog_sql(conn)
    total = await conn.fetchval(
        f"SELECT count(*) FROM ({catalog}) catalogo {where}", *params
    )
    direction = {"priceAsc": "ASC", "priceDesc": "DESC"}[order]
    priority = "(produto_id IS NOT NULL) DESC, " if observed else ""
    rows = await conn.fetch(
        f"""SELECT * FROM ({catalog}) catalogo {where}
        ORDER BY {priority}preco {direction},nome,loja,link LIMIT $5 OFFSET $6""",
        *params,
        limit,
        (page - 1) * limit,
    )
    return {
        "produtos": [{**dict(r), "preco_atual": r["preco"]} for r in rows],
        "total": total,
        "pagina": page,
        "limite": limit,
        "frete_disponivel": True,
        "priorizar_observados": observed,
    }


async def history_available(conn):
    return await conn.fetchval(
        "SELECT to_regclass('hunter_price_observations') IS NOT NULL"
    )


async def product(conn, product_id):
    extended = await conn.fetchval(
        "SELECT to_regclass('hunter_catalog_shops') IS NOT NULL"
    )
    columns = "id,loja,link,channel" if extended else "id,loja,link"
    return await conn.fetchrow(
        f"SELECT {columns} FROM hunter_catalog_products WHERE id=$1", product_id
    )


async def history(conn, item, page, limit):
    fields = "id,nome,imagem_url,preco,preco_cartao,pagamento,disponivel,coletado_em,registrado_em,fonte_coleta,fonte_url"
    if "channel" in item:
        fields += ",price_kind,promotion_terms"
    total = await conn.fetchval(
        "SELECT count(*) FROM hunter_price_observations WHERE produto_id=$1", item["id"]
    )
    rows = await conn.fetch(
        f"""SELECT {fields} FROM hunter_price_observations WHERE produto_id=$1
        ORDER BY coletado_em DESC,id DESC LIMIT $2 OFFSET $3""",
        item["id"],
        limit,
        (page - 1) * limit,
    )
    return {
        "produto": dict(item),
        "historico": [dict(r) for r in rows],
        "total": total,
        "pagina": page,
        "limite": limit,
    }
