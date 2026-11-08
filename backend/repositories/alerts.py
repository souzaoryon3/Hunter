"""Alertas HTTP; protocolo e processamento RabbitMQ permanecem em messaging/."""

from messaging.catalog import catalog_sql


async def create(conn, user_id, product, price):
    return await conn.fetchval(
        "INSERT INTO alertas_preco(usuario_id,produto,preco) VALUES($1,$2,$3) RETURNING id",
        user_id,
        product,
        price,
    )


async def list_owned(conn, user_id):
    catalog = await catalog_sql(conn)
    return await conn.fetch(
        f"""SELECT a.id,a.produto,a.preco,a.created_at AS data,
        oferta.preco AS preco_atual,oferta.link,oferta.loja FROM alertas_preco a
        LEFT JOIN LATERAL (SELECT p.preco,p.link,p.loja FROM ({catalog}) p
            WHERE strpos(lower(p.nome),lower(a.produto))>0
            ORDER BY p.preco,p.nome,p.link LIMIT 1) oferta ON TRUE
        WHERE a.usuario_id=$1 ORDER BY a.id DESC""",
        user_id,
    )


async def update(conn, user_id, item_id, changes):
    if not changes or set(changes) - {"produto", "preco"}:
        raise ValueError("Campos de alerta invalidos.")
    fields = [f"{name}=${i}" for i, name in enumerate(changes, 1)]
    return await conn.execute(
        f"UPDATE alertas_preco SET {','.join(fields)} WHERE id=${len(fields) + 1} AND usuario_id=${len(fields) + 2}",
        *changes.values(),
        item_id,
        user_id,
    )


async def delete(conn, user_id, item_id):
    return await conn.execute(
        "DELETE FROM alertas_preco WHERE id=$1 AND usuario_id=$2", item_id, user_id
    )
