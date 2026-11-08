"""Identidade e autorizacao compartilhadas pelas rotas."""

import re
from fastapi import Depends, HTTPException
from auth import get_current_user
from backend.database import get_db
from backend.repositories import accounts


async def usuario_autenticado(
    subject: str = Depends(get_current_user), conn=Depends(get_db)
):
    # ID estável: alterar o e-mail não muda a identidade da sessão.
    if not re.fullmatch(r"[0-9]{1,10}", subject) or not 0 < int(subject) <= 2147483647:
        raise HTTPException(
            401,
            "Entre novamente para atualizar sua sessão.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    usuario = await accounts.by_id(conn, int(subject))
    if not usuario:
        raise HTTPException(
            401,
            "Esta conta não está mais disponível.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario
