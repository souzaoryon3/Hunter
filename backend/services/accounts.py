"""Hash e regras de acesso; sem SQL e sem conexoes criadas implicitamente."""

from starlette.concurrency import run_in_threadpool
from backend.repositories import accounts
from backend.security import create_access_token, get_password_hash, verify_password


class AccountError(ValueError):
    def __init__(self, status, detail):
        self.status = status
        self.detail = detail
        super().__init__(detail)


async def register(conn, data):
    hashed = await run_in_threadpool(get_password_hash, data.senha)
    return await accounts.create(conn, data.nome, data.email, hashed)


async def authenticate(conn, username, password):
    row = await accounts.by_email(conn, username.strip())
    if not row or not await run_in_threadpool(verify_password, password, row["senha"]):
        raise AccountError(401, "E-mail ou senha incorretos.")
    return create_access_token({"sub": str(row["id"])})


async def update(conn, data, user):
    changing = (
        data.email is not None and data.email != user["email"]
    ) or data.senha is not None
    if changing and (
        not data.senha_atual
        or not await run_in_threadpool(verify_password, data.senha_atual, user["senha"])
    ):
        raise AccountError(
            400, "Confirme sua senha atual para alterar e-mail ou senha."
        )
    changes = {
        key: getattr(data, key)
        for key in ("nome", "email", "senha")
        if getattr(data, key) is not None
    }
    if not changes:
        raise AccountError(400, "Nenhum campo para atualizar.")
    if "senha" in changes:
        changes["senha"] = await run_in_threadpool(get_password_hash, changes["senha"])
    await accounts.update(conn, user["id"], changes)
    return create_access_token({"sub": str(user["id"])})
