"""Contratos HTTP de notifications."""

from fastapi import APIRouter, Depends, HTTPException, Query
from backend.database import get_db
from backend.dependencies import usuario_autenticado

router = APIRouter()


@router.get("/notificacoes", tags=["Notificações"])
async def listar_notificacoes(
    pagina: int = Query(1, ge=1, le=100000),
    limite: int = Query(20, ge=1, le=100),
    usuario=Depends(usuario_autenticado),
    conn=Depends(get_db),
):
    return await repository.list_owned(conn, usuario["id"], pagina, limite)


@router.put("/notificacoes/{notificacao_id}/lida", tags=["Notificações"])
async def marcar_notificacao_lida(
    notificacao_id: int, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    result = await repository.mark_read(conn, usuario["id"], notificacao_id)
    if result == "UPDATE 0":
        raise HTTPException(404, "Notifica??o n?o encontrada.")
    return {"message": "Notifica??o marcada como lida."}


from backend.repositories import notifications as repository
