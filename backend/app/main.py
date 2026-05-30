from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events_router, reminders_router, voice_router, ws_router
from app.core.config import get_settings
from app.core.redis import check_redis_connection, close_redis_client
from app.db.session import check_database_connection
from app.services.reminder_scheduler import ReminderScheduler


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    reminder_scheduler = ReminderScheduler()
    await reminder_scheduler.start()
    app.state.reminder_scheduler = reminder_scheduler
    try:
        yield
    finally:
        await reminder_scheduler.stop()
        await close_redis_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events_router)
app.include_router(reminders_router)
app.include_router(voice_router)
app.include_router(ws_router)


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
