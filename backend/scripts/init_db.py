import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app import models  # noqa: F401


async def init_db() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(init_db())
    except Exception as exc:
        raise SystemExit(f"Database initialization failed: {exc}") from exc

    print("Database tables initialized.")


if __name__ == "__main__":
    main()

