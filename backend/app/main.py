"""FastAPI application factory.

Design Decisions:
    - Application Factory Pattern: create_app() returns a configured FastAPI instance.
      This makes testing easier (create fresh app per test) and follows FastAPI best practices.
    - Lifespan context manager handles startup/shutdown events (replaces deprecated on_event).
    - All cross-cutting concerns (CORS, logging, exceptions) are configured here.
    - Routers are mounted, not defined here — keeps this file thin.
    - Database and Redis connections are initialized at startup and disposed at shutdown.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import v1_router
from app.config import get_settings
from app.core.database import close_db, init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, init_redis

logger = get_logger(__name__)

APP_DESCRIPTION = (
    "Production-grade RAG chatbot with authentication, " "hybrid search, and semantic cache."
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager.

    Startup: Initialize logging, database, and Redis connections.
    Shutdown: Dispose database engine and close Redis client.
    """
    settings = get_settings()
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        debug=settings.app_debug,
    )

    # ── Startup ──────────────────────────────────────────────────────────────
    await init_db()
    await init_redis()

    logger.info("All services initialized successfully")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await close_redis()
    await close_db()
    logger.info("Application shut down gracefully")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI application instance.
    """
    # Initialize logging first — everything else depends on it
    setup_logging()

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=APP_DESCRIPTION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ───────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(v1_router)

    return app


# Application instance for uvicorn
app = create_app()
