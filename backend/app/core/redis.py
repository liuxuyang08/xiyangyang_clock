from redis.asyncio import Redis

from app.core.config import get_settings


_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    if not settings.redis_url:
        return None

    try:
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=30,
        )
    except Exception:
        _redis_client = None

    return _redis_client


async def check_redis_connection() -> bool:
    client = get_redis_client()
    if client is None:
        return False

    try:
        return bool(await client.ping())
    except Exception:
        return False


async def close_redis_client() -> None:
    global _redis_client

    if _redis_client is None:
        return

    await _redis_client.aclose()
    _redis_client = None

