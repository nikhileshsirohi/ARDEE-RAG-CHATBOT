"""Tests for admin metrics repository."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.models.user import UserRole
from app.repositories.metrics import MetricsRepository


class FakeMappingResult:
    """Minimal SQLAlchemy mapping result test double."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> "FakeMappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class FakeSession:
    """Capture executed statements and return predefined rows."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.statement: Any | None = None

    async def execute(self, statement: Any) -> FakeMappingResult:
        self.statement = statement
        return FakeMappingResult(self.rows)


@pytest.mark.anyio
async def test_metrics_repository_maps_user_token_usage_rows() -> None:
    """Repository should return dashboard-ready per-user usage metrics."""
    user_id = uuid.uuid4()
    session = FakeSession(
        [
            {
                "user_id": user_id,
                "full_name": "Demo User",
                "email": "demo@example.com",
                "role": UserRole.USER,
                "input_tokens": 100,
                "output_tokens": 25,
                "embedding_tokens": 10,
                "total_tokens": 135,
                "request_count": 3,
            }
        ]
    )
    repository = MetricsRepository(session)  # type: ignore[arg-type]

    rows = await repository.list_user_token_usage(
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 31, tzinfo=UTC),
        limit=50,
        offset=0,
    )

    assert session.statement is not None
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].full_name == "Demo User"
    assert rows[0].email == "demo@example.com"
    assert rows[0].input_tokens == 100
    assert rows[0].output_tokens == 25
    assert rows[0].embedding_tokens == 10
    assert rows[0].total_tokens == 135
    assert rows[0].request_count == 3


@pytest.mark.anyio
async def test_metrics_repository_returns_zero_usage_users() -> None:
    """Users without matching usage should still be representable with zero totals."""
    session = FakeSession(
        [
            {
                "user_id": uuid.uuid4(),
                "full_name": None,
                "email": "unused@example.com",
                "role": UserRole.USER,
                "input_tokens": 0,
                "output_tokens": 0,
                "embedding_tokens": 0,
                "total_tokens": 0,
                "request_count": 0,
            }
        ]
    )
    repository = MetricsRepository(session)  # type: ignore[arg-type]

    rows = await repository.list_user_token_usage(
        start_at=None,
        end_at=None,
        limit=50,
        offset=0,
    )

    assert rows[0].email == "unused@example.com"
    assert rows[0].total_tokens == 0
    assert rows[0].request_count == 0
