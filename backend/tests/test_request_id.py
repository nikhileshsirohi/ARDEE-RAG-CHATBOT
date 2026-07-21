"""Tests for request ID middleware."""

import re

import httpx
import pytest
from fastapi import FastAPI

from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def make_app() -> FastAPI:
    """Create a small app with request ID middleware."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/demo")
    async def demo() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.mark.anyio
async def test_request_id_generation() -> None:
    """Middleware should generate request IDs when callers do not provide one."""
    transport = httpx.ASGITransport(app=make_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/demo")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.status_code == 200
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        request_id,
    )


@pytest.mark.anyio
async def test_request_id_passthrough() -> None:
    """Middleware should return provided request IDs for client correlation."""
    transport = httpx.ASGITransport(app=make_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/demo", headers={REQUEST_ID_HEADER: "request-123"})

    assert response.headers[REQUEST_ID_HEADER] == "request-123"
