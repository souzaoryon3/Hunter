"""Contratos HTTP de products."""

from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.database import get_db

router = APIRouter()


@router.get("/lojas", tags=["Produtos"])
async def lojas(conn=Depends(get_db)):
    return {"lojas": await repository.shops(conn)}


@router.get("/buscar-produtos", tags=["Produtos"])
async def buscar_produtos(
    nome: str = Query(..., min_length=1, max_length=255),
    preco_min: Optional[float] = Query(
        None, ge=0, le=1_000_000_000, allow_inf_nan=False
    ),
    preco_max: Optional[float] = Query(
        None, ge=0, le=1_000_000_000, allow_inf_nan=False
    ),
    loja: Optional[str] = Query(None, max_length=100),
    ordem: Literal["priceAsc", "priceDesc"] = "priceAsc",
    frete_gratis: bool = False,
    priorizar_observados: bool = True,
    pagina: int = Query(1, ge=1, le=100000),
    limite: int = Query(24, ge=1, le=100),
    conn=Depends(get_db),
):
    nome = nome.strip()
    if loja is not None and loja not in await repository.shops(conn):
        raise HTTPException(422, "Loja nao cadastrada.")
    if not nome:
        raise HTTPException(422, "Digite o nome de um produto.")
    if preco_min is not None and preco_max is not None and preco_min > preco_max:
        raise HTTPException(422, "O pre?o m?nimo n?o pode ser maior que o m?ximo.")
    return await repository.search(
        conn,
        nome,
        preco_min,
        preco_max,
        loja,
        ordem,
        frete_gratis,
        priorizar_observados,
        pagina,
        limite,
    )


@router.get("/produtos/{produto_id}/historico", tags=["Produtos"])
async def historico_produto(
    produto_id: int,
    pagina: int = Query(1, ge=1),
    limite: int = Query(30, ge=1, le=100),
    conn=Depends(get_db),
):
    if not await repository.history_available(conn):
        raise HTTPException(503, "Hist?rico ainda n?o ativado neste ambiente.")
    item = await repository.product(conn, produto_id)
    if not item:
        raise HTTPException(404, "Produto n?o encontrado.")
    return await repository.history(conn, item, pagina, limite)


from backend.repositories import products as repository
