from fastapi import FastAPI

from app.core.config import get_settings
from app.db.session import check_database_connection


settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/api/health")
async def health() -> dict[str, str]:
    database_available = await check_database_connection()

    return {
        "status": "ok",
        "environment": settings.app_env,
        "database": "available" if database_available else "unavailable",
    }
