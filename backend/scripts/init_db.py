import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models.user import User
from app import models  # noqa: F401

DEFAULT_DEMO_USER_ID = "u001"


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
            await connection.run_sync(seed_default_demo_user)
    finally:
        await engine.dispose()


def seed_default_demo_user(connection) -> None:
    existing_user_id = connection.execute(
        select(User.id).where(User.id == DEFAULT_DEMO_USER_ID)
    ).scalar_one_or_none()
    if existing_user_id is not None:
        return

    connection.execute(
        User.__table__.insert().values(
            id=DEFAULT_DEMO_USER_ID,
            nickname="Demo User",
            timezone="Asia/Shanghai",
            default_reminder_minutes=15,
        )
    )


def main() -> None:
    try:
        asyncio.run(init_db())
    except Exception as exc:
        raise SystemExit(f"Database initialization failed: {exc}") from exc

    print("Database tables initialized and demo user seeded.")


if __name__ == "__main__":
    main()
