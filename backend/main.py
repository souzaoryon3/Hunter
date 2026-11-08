"""Composicao FastAPI; executar uvicorn backend.main:app ou app:app."""

import asyncpg
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.database import lifespan, get_db
from backend.errors import database_error
from backend.routes import accounts, alerts, feedback, notifications, products
from config.settings import cors_origins
from data_mining.api import create_router
from backend.services.accounts import AccountError
from fastapi.responses import JSONResponse


def create_app():
    application = FastAPI(title="Hunter API", version="1.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins()),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.add_exception_handler(asyncpg.PostgresError, database_error)

    @application.exception_handler(AccountError)
    async def account_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    for router in (
        accounts.router,
        alerts.router,
        feedback.router,
        notifications.router,
        products.router,
        create_router(get_db),
    ):
        application.include_router(router)

    @application.get("/", include_in_schema=False)
    async def root():
        return {"message": "API Hunter est? online!"}

    @application.get("/health/live", include_in_schema=False)
    async def live():
        return {"status": "live"}

    @application.get("/health/ready", include_in_schema=False)
    async def ready(conn=Depends(get_db)):
        if not await conn.fetchval(
            "SELECT to_regclass('hunter_collection_control') IS NOT NULL"
        ):
            raise HTTPException(503, "Esquema ainda nao preparado.")
        return {"status": "ready"}

    return application


app = create_app()
