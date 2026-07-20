"""Tests for the health check endpoint.

Tests verify:
    - Correct HTTP status code (200)
    - Response body schema matches HealthResponse
    - Response values match configuration
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the async backend for tests."""
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    """Create an async test client for the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint should return HTTP 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_health_response_schema(client: AsyncClient) -> None:
    """Health endpoint response should match HealthResponse schema."""
    response = await client.get("/api/v1/health")
    data = response.json()

    assert "status" in data
    assert "version" in data
    assert "environment" in data


@pytest.mark.anyio
async def test_health_status_is_healthy(client: AsyncClient) -> None:
    """Health status should be 'healthy'."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.anyio
async def test_health_version_matches_config(client: AsyncClient) -> None:
    """Health version should match the configured app version."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["version"] == "0.1.0"


@pytest.mark.anyio
async def test_health_environment_is_development(client: AsyncClient) -> None:
    """Health environment should default to 'development'."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["environment"] == "development"
