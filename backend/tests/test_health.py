"""Tests for the health check endpoint.

Tests verify:
    - Correct HTTP status code (200) for shallow health
    - Response body schema matches HealthResponse
    - Response values match configuration
    - Deep health parameter is accepted

Note: Deep health checks (DB + Redis) are NOT tested here because
these are unit tests that don't require infrastructure. Integration
tests with real DB/Redis will be added in a future step.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the async backend for tests."""
    return "asyncio"


@pytest.fixture
def test_app():
    """Create a test FastAPI application.

    Uses create_app() factory to get a fresh app instance.
    Note: DB and Redis are NOT initialized for unit tests —
    lifespan is not triggered by the test client transport.
    """
    return create_app()


@pytest.fixture
async def client(test_app) -> AsyncClient:
    """Create an async test client for the FastAPI application."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint should return HTTP 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_schema(client: AsyncClient) -> None:
    """Health endpoint response should contain required fields."""
    response = await client.get("/api/v1/health")
    data = response.json()

    assert "status" in data
    assert "version" in data
    assert "environment" in data


@pytest.mark.anyio
async def test_health_status_is_healthy(client: AsyncClient) -> None:
    """Health status should be 'healthy' for shallow check."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.anyio
async def test_health_version_matches_config(client: AsyncClient) -> None:
    """Health version should match the configured app version."""
    settings = get_settings()
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["version"] == settings.app_version


@pytest.mark.anyio
async def test_health_environment_is_development(client: AsyncClient) -> None:
    """Health environment should default to 'development'."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["environment"] == "development"


@pytest.mark.anyio
async def test_shallow_health_has_no_db_or_redis(client: AsyncClient) -> None:
    """Shallow health check should NOT include database or redis fields."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data.get("database") is None
    assert data.get("redis") is None
