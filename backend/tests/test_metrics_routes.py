"""Tests for metrics API route."""

import pytest

from app.api.v1.routes.metrics import PROMETHEUS_CONTENT_TYPE, prometheus_metrics


@pytest.mark.anyio
async def test_prometheus_metrics_route_returns_text_response() -> None:
    """Metrics route should return Prometheus text exposition content."""
    response = await prometheus_metrics()

    assert response.media_type == PROMETHEUS_CONTENT_TYPE
    assert b"http_requests_total" in response.body
