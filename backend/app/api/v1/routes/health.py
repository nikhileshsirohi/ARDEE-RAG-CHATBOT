"""Health check endpoint.

This is the first endpoint any production service should have.
Used by:
    - Load balancers (AWS ALB, nginx) for health probes
    - Kubernetes liveness/readiness probes
    - Docker HEALTHCHECK
    - Monitoring dashboards (uptime checks)

Design: Returns minimal info — status, version, environment.
Future enhancement: Check DB and Redis connectivity for deep health checks.
"""

from fastapi import APIRouter, status

from app.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Returns the current health status, version, and environment of the application.",
)
async def health_check() -> HealthResponse:
    """Check application health.

    Returns:
        HealthResponse with status, version, and environment.
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        environment=settings.app_env,
    )
