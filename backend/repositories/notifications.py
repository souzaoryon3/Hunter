"""Leitura paginada e marcacao idempotente, sempre por proprietario."""


async def list_owned(conn, user_id, page, limit):
    total = await conn.fetchval(
        "SELECT count(*) FROM hunter_notifications WHERE usuario_id=$1", user_id
    )
    unread = await conn.fetchval(
        "SELECT count(*) FROM hunter_notifications WHERE usuario_id=$1 AND read_at IS NULL",
        user_id,
    )
    rows = await conn.fetch(
        """SELECT id,produto,preco,preco_desejado,loja,link,created_at,read_at
        FROM hunter_notifications WHERE usuario_id=$1 ORDER BY id DESC LIMIT $2 OFFSET $3""",
        user_id,
        limit,
        (page - 1) * limit,
    )
    return {
        "notificacoes": [dict(r) for r in rows],
        "total": total,
        "nao_lidas": unread,
        "pagina": page,
        "limite": limit,
    }


async def mark_read(conn, user_id, item_id):
    return await conn.execute(
        """UPDATE hunter_notifications SET read_at=COALESCE(read_at,now())
        WHERE id=$1 AND usuario_id=$2""",
        item_id,
        user_id,
    )
