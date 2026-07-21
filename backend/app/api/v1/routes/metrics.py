"""Prometheus metrics route."""

from fastapi import APIRouter, Response

from app.core.metrics import metrics_registry

router = APIRouter(tags=["Metrics"])

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/metrics", summary="Prometheus Metrics")
async def prometheus_metrics() -> Response:
    """Return application metrics in Prometheus text format."""
    return Response(
        content=metrics_registry.render_prometheus(),
        media_type=PROMETHEUS_CONTENT_TYPE,
    )
