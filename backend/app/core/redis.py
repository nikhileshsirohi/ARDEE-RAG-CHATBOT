"""Async Redis client manager.

Design Decisions:
    - Uses redis.asyncio for true non-blocking Redis operations.
    - Connection pool is managed by the Redis client internally.
    - max_connections=50 covers semantic cache + rate limiting + session storage.
    - Lifecycle (init/close) is managed via the FastAPI lifespan manager.
    - Health check pings Redis and measures latency.

Why redis-py (redis.asyncio) over aioredis?
    - aioredis was merged into redis-py v4.2+. redis.asyncio IS aioredis now.
    - Single maintained library, official Redis support.
"""

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level reference — initialized in init_redis(), closed in close_redis()
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Get the Redis client, raising if not initialized."""
    if _redis_client is None:
        msg = "Redis client not initialized. Call init_redis() first."
        raise RuntimeError(msg)
    return _redis_client


async def init_redis() -> None:
    """Initialize the async Redis client with connection pooling.

    Called once during application startup via the lifespan manager.
    Verifies connectivity with a PING command.
    """
    global _redis_client

    settings = get_settings()

    _redis_client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

    # Verify connectivity
    await _redis_client.ping()

    logger.info(
        "Redis client initialized",
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
    )


async def close_redis() -> None:
    """Close the Redis client and release all connections.

    Called during application shutdown via the lifespan manager.
    """
    global _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Redis client closed")
        _redis_client = None


async def check_redis_health() -> dict[str, object]:
    """Check Redis connectivity and measure latency.

    Returns:
        Dict with status and latency_ms.
    """
    import time

    try:
        client = get_redis_client()
        start = time.monotonic()
        await client.ping()
        latency = (time.monotonic() - start) * 1000
        return {"status": "connected", "latency_ms": round(latency, 2)}
    except Exception as exc:
        logger.error("Redis health check failed", error=str(exc))
        return {"status": "disconnected", "error": str(exc)}
