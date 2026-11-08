"""Feedback restrito ao proprietario em todas as operacoes."""


async def create(conn, user, message):
    return await conn.fetchval(
        """INSERT INTO feedbacks(usuario_id,nome,email,feedback)
        VALUES($1,$2,$3,$4) RETURNING id""",
        user["id"],
        user["nome"],
        user["email"],
        message,
    )


async def list_owned(conn, user_id):
    return await conn.fetch(
        "SELECT id,feedback,data_envio FROM feedbacks WHERE usuario_id=$1 ORDER BY id DESC",
        user_id,
    )


async def update(conn, user_id, item_id, message):
    return await conn.execute(
        "UPDATE feedbacks SET feedback=$1 WHERE id=$2 AND usuario_id=$3",
        message,
        item_id,
        user_id,
    )


async def delete(conn, user_id, item_id):
    return await conn.execute(
        "DELETE FROM feedbacks WHERE id=$1 AND usuario_id=$2", item_id, user_id
    )
