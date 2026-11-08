"""Contratos HTTP de feedback."""

from fastapi import APIRouter, Depends, HTTPException
from backend.database import get_db
from backend.dependencies import usuario_autenticado
from backend.schemas import Feedback, FeedbackUpdate

router = APIRouter()


@router.post("/feedback", tags=["Feedback"], status_code=201)
async def enviar_feedback(
    feedback: Feedback, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    item = await repository.create(conn, usuario, feedback.feedback)
    return {
        "message": "Mensagem enviada. Obrigado por ajudar a melhorar o Hunter!",
        "id": item,
    }


@router.get("/feedbacks", tags=["Feedback"])
async def listar_feedbacks(usuario=Depends(usuario_autenticado), conn=Depends(get_db)):
    return [dict(row) for row in await repository.list_owned(conn, usuario["id"])]


@router.put("/feedback/{feedback_id}", tags=["Feedback"])
async def atualizar_feedback(
    feedback_id: int,
    novo: FeedbackUpdate,
    usuario=Depends(usuario_autenticado),
    conn=Depends(get_db),
):
    result = await repository.update(conn, usuario["id"], feedback_id, novo.feedback)
    if result == "UPDATE 0":
        raise HTTPException(404, "Mensagem n?o encontrada.")
    return {"message": "Mensagem atualizada."}


@router.delete("/feedback/{feedback_id}", tags=["Feedback"])
async def deletar_feedback(
    feedback_id: int, usuario=Depends(usuario_autenticado), conn=Depends(get_db)
):
    result = await repository.delete(conn, usuario["id"], feedback_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Mensagem n?o encontrada.")
    return {"message": "Mensagem exclu?da."}


from backend.repositories import feedback as repository
