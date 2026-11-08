"""Pool e ciclo de vida; nenhuma conexao no import."""

from contextlib import asynccontextmanager
import asyncpg
from fastapi import FastAPI
from config.settings import APISettings, assert_runtime_role

db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    settings = APISettings.load()
    db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.pool_min,
        max_size=settings.pool_max,
        command_timeout=settings.command_timeout,
    )
    try:
        async with db_pool.acquire() as conn:
            await assert_runtime_role(conn)
        yield
    finally:
        await db_pool.close()


async def get_db():
    async with db_pool.acquire() as conn:
        yield conn
