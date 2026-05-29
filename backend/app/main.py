from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import events_router, reminders_router
from app.core.config import get_settings
from app.core.redis import check_redis_connection, close_redis_client
from app.db.session import check_database_connection


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await close_redis_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(events_router)
app.include_router(reminders_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    database_available = await check_database_connection()
    redis_available = await check_redis_connection()

    return {
        "status": "ok",
        "environment": settings.app_env,
        "database": "available" if database_available else "unavailable",
        "redis": "available" if redis_available else "unavailable",
    }
