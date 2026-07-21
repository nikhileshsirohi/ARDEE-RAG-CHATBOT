"""Repository for admin metrics and usage reporting."""

from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import TokenUsage
from app.models.user import User
from app.schemas.rag import UserTokenUsageMetric


class MetricsRepository:
    """Database operations for admin dashboard metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_user_token_usage(
        self,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
        offset: int,
    ) -> list[UserTokenUsageMetric]:
        """Aggregate token usage by user, including users with zero usage."""
        join_conditions = [TokenUsage.user_id == User.id]
        if start_at is not None:
            join_conditions.append(TokenUsage.created_at >= start_at)
        if end_at is not None:
            join_conditions.append(TokenUsage.created_at <= end_at)

        input_tokens = func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens")
        output_tokens = func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens")
        embedding_tokens = func.coalesce(func.sum(TokenUsage.embedding_tokens), 0).label(
            "embedding_tokens"
        )
        total_tokens = func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens")
        request_count = func.count(TokenUsage.id).label("request_count")

        stmt: Select[Any] = (
            select(
                User.id.label("user_id"),
                User.full_name,
                User.email,
                User.role,
                input_tokens,
                output_tokens,
                embedding_tokens,
                total_tokens,
                request_count,
            )
            .outerjoin(TokenUsage, and_(*join_conditions))
            .group_by(User.id, User.full_name, User.email, User.role, User.created_at)
            .order_by(total_tokens.desc(), User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return [
            UserTokenUsageMetric(
                user_id=row["user_id"],
                full_name=row["full_name"],
                email=row["email"],
                role=row["role"],
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                embedding_tokens=int(row["embedding_tokens"]),
                total_tokens=int(row["total_tokens"]),
                request_count=int(row["request_count"]),
            )
            for row in result.mappings().all()
        ]
