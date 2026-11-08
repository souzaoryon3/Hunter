"""Persistencia de contas; nomes de colunas dinamicos tem whitelist fechada."""


async def create(conn, name, email, password_hash):
    return await conn.fetchval(
        "INSERT INTO usuarios(nome,email,senha) VALUES($1,$2,$3) RETURNING id",
        name,
        email,
        password_hash,
    )


async def by_email(conn, email):
    return await conn.fetchrow("SELECT id,senha FROM usuarios WHERE email=$1", email)


async def by_id(conn, user_id):
    return await conn.fetchrow(
        "SELECT id,nome,email,senha FROM usuarios WHERE id=$1", user_id
    )


async def update(conn, user_id, changes):
    if not changes or set(changes) - {"nome", "email", "senha"}:
        raise ValueError("Campos de conta invalidos.")
    fields = [f"{name}=${i}" for i, name in enumerate(changes, 1)]
    await conn.execute(
        f"UPDATE usuarios SET {','.join(fields)} WHERE id=${len(fields) + 1}",
        *changes.values(),
        user_id,
    )


async def delete(conn, user_id):
    await conn.execute("DELETE FROM usuarios WHERE id=$1", user_id)
