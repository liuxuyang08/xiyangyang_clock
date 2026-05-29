from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def _create_engine() -> AsyncEngine | None:
    settings = get_settings()

    if not settings.database_url:
        return None

    try:
        return create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
    except Exception:
        return None


engine = _create_engine()

SessionLocal = (
    async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    if engine is not None
    else None
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )

    async with SessionLocal() as session:
        yield session


async def check_database_connection() -> bool:
    if engine is None:
        return False

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

