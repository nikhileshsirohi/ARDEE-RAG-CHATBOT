"""Redis-backed sliding window rate limiting middleware."""

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

import jwt
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60
SKIPPED_RATE_LIMIT_PREFIXES = (
    "/api/v1/health",
    "/api/v1/metrics",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RedisRateLimitClient(Protocol):
    """Redis operations required by the sliding-window limiter."""

    async def zremrangebyscore(
        self, name: str, min_score: float, max_score: float
    ) -> object:
        """Remove expired scores."""

    async def zcard(self, name: str) -> int:
        """Return sorted-set cardinality."""

    async def zadd(self, name: str, mapping: dict[str, float]) -> object:
        """Add current request marker."""

    async def expire(self, name: str, time: int) -> object:
        """Set key TTL."""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-user or per-IP Redis sliding-window request limits."""

    def __init__(
        self,
        app: ASGIApp,
        settings: Settings | None = None,
        redis_getter: Callable[[], RedisRateLimitClient] | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self.redis_getter = redis_getter or self._get_redis_client

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self._should_skip(request.url.path):
            return await call_next(request)

        identity = self._identity(request)
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SECONDS
        key = f"rate_limit:{identity}"

        try:
            redis_client = self.redis_getter()
            await redis_client.zremrangebyscore(key, 0, window_start)
            request_count = await redis_client.zcard(key)
            if request_count >= self.settings.rate_limit_per_minute:
                retry_after = RATE_LIMIT_WINDOW_SECONDS
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "message": "Rate limit exceeded",
                            "detail": "Too many requests. Please retry later.",
                            "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            await redis_client.zadd(key, {str(uuid.uuid4()): now})
            await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        except (RedisError, RuntimeError) as exc:
            logger.warning("Rate limit check skipped", error=str(exc))

        return await call_next(request)

    @staticmethod
    def _should_skip(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in SKIPPED_RATE_LIMIT_PREFIXES)

    def _identity(self, request: Request) -> str:
        token = self._bearer_token(request)
        if token:
            user_id = self._user_id_from_token(token)
            if user_id:
                return f"user:{user_id}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    @staticmethod
    def _bearer_token(request: Request) -> str | None:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return token

    def _user_id_from_token(self, token: str) -> str | None:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
            )
        except jwt.InvalidTokenError:
            return None

        if payload.get("type") != "access":
            return None
        subject = payload.get("sub")
        if isinstance(subject, str):
            return subject
        return None

    @staticmethod
    def _get_redis_client() -> RedisRateLimitClient:
        return cast(RedisRateLimitClient, get_redis_client())
