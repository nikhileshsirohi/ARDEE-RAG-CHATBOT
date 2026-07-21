"""Admin metrics routes."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.auth import RequireRole, SessionDep
from app.core.exceptions import BadRequestError
from app.models.user import User, UserRole
from app.repositories.metrics import MetricsRepository
from app.schemas.rag import UserTokenUsageMetric

router = APIRouter(prefix="/admin/metrics", tags=["Admin Metrics"])

AdminDep = Annotated[User, Depends(RequireRole(UserRole.ADMIN))]


def get_metrics_repository(session: SessionDep) -> MetricsRepository:
    """Build request-scoped metrics repository."""
    return MetricsRepository(session)


MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


@router.get(
    "/token-usage/users",
    response_model=list[UserTokenUsageMetric],
    summary="List per-user token usage metrics",
)
async def list_user_token_usage_metrics(
    _admin_user: AdminDep,
    repository: MetricsRepositoryDep,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserTokenUsageMetric]:
    """Return per-user token usage totals for the admin dashboard."""
    if start_at is not None and end_at is not None and start_at > end_at:
        raise BadRequestError("start_at must be before or equal to end_at")

    return await repository.list_user_token_usage(
        start_at=start_at,
        end_at=end_at,
        limit=limit,
        offset=offset,
    )
