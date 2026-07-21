"""Tests for security headers middleware."""

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.middleware.security_headers import SecurityHeadersMiddleware


@pytest.mark.anyio
async def test_security_headers_are_present() -> None:
    """Middleware should attach baseline security headers."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=Settings(app_env="production"))

    @app.get("/demo")
    async def demo() -> dict[str, str]:
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/demo")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert (
        response.headers["Content-Security-Policy"]
        == "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
    )


@pytest.mark.anyio
async def test_security_headers_allow_swagger_assets_in_development() -> None:
    """Development CSP should not blank FastAPI Swagger UI CDN assets."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=Settings(app_env="development"))

    @app.get("/demo")
    async def demo() -> dict[str, str]:
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/demo")

    csp = response.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "script-src" in csp
    assert "style-src" in csp
