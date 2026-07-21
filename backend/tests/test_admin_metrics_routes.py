"""Tests for admin metrics routes."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.v1.routes.admin_metrics import list_user_token_usage_metrics
from app.core.exceptions import BadRequestError


class FakeMetricsRepository:
    """Capture route parameters."""

    def __init__(self) -> None:
        self.call: dict[str, Any] | None = None

    async def list_user_token_usage(
        self,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
        offset: int,
    ) -> list[object]:
        self.call = {
            "start_at": start_at,
            "end_at": end_at,
            "limit": limit,
            "offset": offset,
        }
        return []


@pytest.mark.anyio
async def test_admin_metrics_route_passes_filters_to_repository() -> None:
    """Route should pass validated filters and pagination to the repository."""
    repository = FakeMetricsRepository()
    start_at = datetime(2026, 1, 1, tzinfo=UTC)
    end_at = datetime(2026, 1, 31, tzinfo=UTC)

    response = await list_user_token_usage_metrics(
        _admin_user=object(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        start_at=start_at,
        end_at=end_at,
        limit=25,
        offset=10,
    )

    assert response == []
    assert repository.call == {
        "start_at": start_at,
        "end_at": end_at,
        "limit": 25,
        "offset": 10,
    }


@pytest.mark.anyio
async def test_admin_metrics_route_rejects_invalid_date_range() -> None:
    """Route should reject inverted date ranges before querying."""
    repository = FakeMetricsRepository()

    with pytest.raises(BadRequestError, match="start_at must be before or equal to end_at"):
        await list_user_token_usage_metrics(
            _admin_user=object(),  # type: ignore[arg-type]
            repository=repository,  # type: ignore[arg-type]
            start_at=datetime(2026, 2, 1, tzinfo=UTC),
            end_at=datetime(2026, 1, 1, tzinfo=UTC),
            limit=50,
            offset=0,
        )

    assert repository.call is None
