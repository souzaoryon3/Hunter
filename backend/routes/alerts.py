"""Contratos HTTP de alerts."""

from fastapi import APIRouter, Depends, HTTPException
from backend.database import get_db
from backend.dependencies import usuario_autenticado
from backend.schemas import AlertaPreco, AlertaPrecoUpdate

router = APIRouter()


@router.post("/alerta-preco", tags=["Alertas"], status_code=201)
async def criar_alerta(
    alerta: AlertaPreco, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    item = await repository.create(conn, usuario["id"], alerta.produto, alerta.preco)
    return {"message": "Alerta salvo!", "id": item}


@router.get("/alertas", tags=["Alertas"])
async def listar_alertas(usuario=Depends(usuario_autenticado), conn=Depends(get_db)):
    rows = await repository.list_owned(conn, usuario["id"])
    return [
        {
            **dict(r),
            "atingido": r["preco_atual"] is not None and r["preco_atual"] <= r["preco"],
        }
        for r in rows
    ]


@router.put("/alerta/{alerta_id}", tags=["Alertas"])
async def atualizar_alerta(
    alerta_id: int,
    alerta: AlertaPrecoUpdate,
    usuario=Depends(usuario_autenticado),
    conn=Depends(get_db),
):
    changes = {
        key: getattr(alerta, key)
        for key in ("produto", "preco")
        if getattr(alerta, key) is not None
    }
    if not changes:
        raise HTTPException(400, "Nenhum campo para atualizar.")
    result = await repository.update(conn, usuario["id"], alerta_id, changes)
    if result == "UPDATE 0":
        raise HTTPException(404, "Alerta n?o encontrado.")
    return {"message": "Alerta atualizado."}


@router.delete("/alerta/{alerta_id}", tags=["Alertas"])
async def deletar_alerta(
    alerta_id: int, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    result = await repository.delete(conn, usuario["id"], alerta_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Alerta n?o encontrado.")
    return {"message": "Alerta exclu?do."}


from backend.repositories import alerts as repository
