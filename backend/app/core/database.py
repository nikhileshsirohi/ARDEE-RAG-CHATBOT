"""Async SQLAlchemy database engine and session management.

Design Decisions:
    - AsyncEngine with asyncpg for true non-blocking I/O.
    - Connection pooling (pool_size=20, max_overflow=10) handles 100+ concurrent users.
    - async_sessionmaker creates sessions that auto-rollback on exceptions.
    - get_db_session is a FastAPI dependency that yields a session per request.
    - Engine is created once at startup and disposed at shutdown via lifespan.

Why async over sync?
    - Sync SQLAlchemy with psycopg2 blocks the event loop.
    - Under 100 concurrent users, sync would require thread pooling, adding complexity
      and memory overhead. Async handles concurrency natively.

Connection Pool Parameters:
    - pool_size=20: Number of persistent connections kept in the pool.
    - max_overflow=10: Additional connections allowed during burst traffic (20+10=30 max).
    - pool_timeout=30: Seconds to wait for a connection before raising an error.
    - pool_recycle=3600: Replace connections older than 1 hour to prevent stale connections.
    - pool_pre_ping=True: Test connections before use to avoid "connection reset" errors.
"""

import time
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level references — initialized in init_db(), disposed in close_db()
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Get the async engine, raising if not initialized."""
    if _engine is None:
        msg = "Database engine not initialized. Call init_db() first."
        raise RuntimeError(msg)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory, raising if not initialized."""
    if _session_factory is None:
        msg = "Session factory not initialized. Call init_db() first."
        raise RuntimeError(msg)
    return _session_factory


async def init_db() -> None:
    """Initialize the async database engine and session factory.

    Called once during application startup via the lifespan manager.
    Creates the connection pool and verifies connectivity.
    """
    global _engine, _session_factory

    settings = get_settings()

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.app_debug and not settings.is_production,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Verify connectivity
    async with _engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

    logger.info(
        "Database engine initialized",
        url=settings.database_url.split("@")[-1],  # Log host only, not credentials
        pool_size=20,
        max_overflow=10,
    )


async def close_db() -> None:
    """Dispose the async database engine and release all connections.

    Called during application shutdown via the lifespan manager.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed")
        _engine = None
        _session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that yields an async database session.

    Usage::

        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(select(Model))

    The session auto-commits if no exception occurs.
    On exception, the session auto-rollbacks.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> dict[str, object]:
    """Check database connectivity and measure latency.

    Returns:
        Dict with status and latency_ms.
    """
    try:
        engine = _get_engine()
        start = time.monotonic()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000
        return {"status": "connected", "latency_ms": round(latency, 2)}
    except Exception as exc:
        logger.error("Database health check failed", error=str(exc))
        return {"status": "disconnected", "error": str(exc)}
