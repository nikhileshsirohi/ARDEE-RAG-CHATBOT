"""Tests for Redis-backed rate limiting middleware."""

import time
import uuid

import httpx
import jwt
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.middleware.rate_limit import RateLimitMiddleware


class FakeRedisRateLimitClient:
    """In-memory Redis sorted-set fake for rate limit tests."""

    def __init__(self) -> None:
        self.sorted_sets: dict[str, dict[str, float]] = {}

    async def zremrangebyscore(
        self, name: str, min_score: float, max_score: float
    ) -> object:
        values = self.sorted_sets.setdefault(name, {})
        for member, score in list(values.items()):
            if min_score <= score <= max_score:
                del values[member]
        return None

    async def zcard(self, name: str) -> int:
        return len(self.sorted_sets.setdefault(name, {}))

    async def zadd(self, name: str, mapping: dict[str, float]) -> object:
        self.sorted_sets.setdefault(name, {}).update(mapping)
        return None

    async def expire(self, name: str, time: int) -> object:
        _ = name
        _ = time
        return None


def make_rate_limited_app(redis_client: FakeRedisRateLimitClient) -> FastAPI:
    """Create an app with a strict one-request rate limit."""
    settings = Settings(rate_limit_per_minute=1)
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        settings=settings,
        redis_getter=lambda: redis_client,
    )

    @app.get("/api/v1/chat/sessions")
    async def sessions() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/v1/metrics")
    async def metrics() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_test_access_token(user_id: uuid.UUID) -> str:
    """Create a JWT matching middleware expectations."""
    settings = Settings()
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.mark.anyio
async def test_rate_limit_applies_per_authenticated_user() -> None:
    """Authenticated requests should be limited by JWT subject."""
    redis_client = FakeRedisRateLimitClient()
    transport = httpx.ASGITransport(app=make_rate_limited_app(redis_client))
    token = create_test_access_token(uuid.uuid4())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = await client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"


@pytest.mark.anyio
async def test_rate_limit_bypasses_health_and_metrics() -> None:
    """Health and metrics endpoints should not consume rate limit quota."""
    redis_client = FakeRedisRateLimitClient()
    transport = httpx.ASGITransport(app=make_rate_limited_app(redis_client))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health_response = await client.get("/api/v1/health")
        metrics_response = await client.get("/api/v1/metrics")

    assert health_response.status_code == 200
    assert metrics_response.status_code == 200
    assert redis_client.sorted_sets == {}
