"""Health check endpoint.

This is the first endpoint any production service should have.
Used by:
    - Load balancers (AWS ALB, nginx) for health probes
    - Kubernetes liveness/readiness probes
    - Docker HEALTHCHECK
    - Monitoring dashboards (uptime checks)

Design:
    - Shallow check (default): Confirms the app process is running.
    - Deep check (?deep=true): Verifies database and Redis connectivity.
    - Shallow is fast and cheap — used for high-frequency liveness probes.
    - Deep is heavier — used for readiness probes before accepting traffic.
"""

from fastapi import APIRouter, Query, status

from app.config import get_settings
from app.core.database import check_db_health
from app.core.redis import check_redis_health
from app.schemas.health import HealthResponse, ServiceHealth

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description=(
        "Returns the current health status. "
        "Use ?deep=true to include database and Redis connectivity checks."
    ),
)
async def health_check(
    deep: bool = Query(
        default=False,
        description="Include database and Redis connectivity checks",
    ),
) -> HealthResponse:
    """Check application health.

    Args:
        deep: If True, checks database and Redis connectivity.

    Returns:
        HealthResponse with status, version, environment,
        and optionally database/redis health info.
    """
    settings = get_settings()

    response = HealthResponse(
        status="healthy",
        version=settings.app_version,
        environment=settings.app_env,
    )

    if deep:
        db_health = await check_db_health()
        redis_health = await check_redis_health()

        response.database = ServiceHealth.model_validate(db_health)
        response.redis = ServiceHealth.model_validate(redis_health)

        # Overall status is unhealthy if any dependency is down
        if db_health.get("status") != "connected" or redis_health.get("status") != "connected":
            response.status = "unhealthy"

    return response
