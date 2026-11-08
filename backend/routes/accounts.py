"""Contratos HTTP de accounts."""

from fastapi import APIRouter, Depends, Form
from backend.database import get_db
from backend.dependencies import usuario_autenticado
from backend.schemas import Usuario, UsuarioUpdate

router = APIRouter()


@router.post("/cadastrar", tags=["Usuários"], status_code=201)
async def cadastrar_usuario(usuario: Usuario, conn=Depends(get_db)):
    user_id = await service.register(conn, usuario)
    return {"message": "Conta criada com sucesso!", "usuario_id": user_id}


@router.post("/login", tags=["Usuários"])
async def login(
    username: str = Form(...), password: str = Form(...), conn=Depends(get_db)
):
    token = await service.authenticate(conn, username, password)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/usuario", tags=["Usuários"])
async def obter_usuario(usuario=Depends(usuario_autenticado)):
    return {"id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"]}


@router.put("/usuario", tags=["Usuários"])
async def atualizar_usuario(
    dados: UsuarioUpdate, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    token = await service.update(conn, dados, usuario)
    return {
        "message": "Dados atualizados!",
        "access_token": token,
        "token_type": "bearer",
    }


@router.delete("/usuario", tags=["Usuários"])
async def deletar_usuario(usuario=Depends(usuario_autenticado), conn=Depends(get_db)):
    await repository.delete(conn, usuario["id"])
    return {"message": "Conta exclu?da com sucesso."}


from backend.services import accounts as service
from backend.repositories import accounts as repository
