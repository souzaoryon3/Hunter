"""Respostas de erro sem detalhes sensiveis do banco."""

import logging
import asyncpg
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def database_error(request, exc):
    logger.error("Falha no banco de dados: %s", type(exc).__name__)
    if isinstance(exc, asyncpg.UniqueViolationError):
        return JSONResponse(
            status_code=409, content={"detail": "Este e-mail já está cadastrado."}
        )
    return JSONResponse(
        status_code=503,
        content={"detail": "Serviço temporariamente indisponível. Tente novamente."},
    )
