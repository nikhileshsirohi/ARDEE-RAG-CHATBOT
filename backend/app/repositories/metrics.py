"""Repository for admin metrics and usage reporting."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.models.rag import Bot, ChatSession, TokenUsage
from app.models.user import User
from app.schemas.rag import (
    BotTokenUsageMetric,
    DailyTokenUsageMetric,
    MyTokenUsageSummary,
    SessionTokenUsageMetric,
    UserTokenUsageMetric,
)


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

    async def list_bot_token_usage(
        self,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
        offset: int,
    ) -> list[BotTokenUsageMetric]:
        """Aggregate token usage by bot, including bots with zero usage."""
        join_conditions = [TokenUsage.bot_id == Bot.id]
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
                Bot.id.label("bot_id"),
                Bot.name,
                input_tokens,
                output_tokens,
                embedding_tokens,
                total_tokens,
                request_count,
            )
            .outerjoin(TokenUsage, and_(*join_conditions))
            .where(Bot.deleted_at.is_(None))
            .group_by(Bot.id, Bot.name, Bot.created_at)
            .order_by(total_tokens.desc(), Bot.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return [
            BotTokenUsageMetric(
                bot_id=row["bot_id"],
                name=row["name"],
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                embedding_tokens=int(row["embedding_tokens"]),
                total_tokens=int(row["total_tokens"]),
                request_count=int(row["request_count"]),
            )
            for row in result.mappings().all()
        ]

    async def list_daily_token_usage(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        user_id: uuid.UUID | None,
        bot_id: uuid.UUID | None = None,
    ) -> list[DailyTokenUsageMetric]:
        """Aggregate token usage into per-day buckets for the usage chart.

        When ``user_id``/``bot_id`` are provided the buckets are scoped
        accordingly; otherwise they span every user. Days with no usage are
        omitted — the caller fills gaps so the chart always shows a full window.
        """
        conditions = [
            TokenUsage.created_at >= start_at,
            TokenUsage.created_at <= end_at,
        ]
        if user_id is not None:
            conditions.append(TokenUsage.user_id == user_id)
        if bot_id is not None:
            conditions.append(TokenUsage.bot_id == bot_id)

        day = cast(TokenUsage.created_at, Date).label("day")

        stmt: Select[Any] = (
            select(
                day,
                func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(TokenUsage.embedding_tokens), 0).label("embedding_tokens"),
                func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
                func.count(TokenUsage.id).label("request_count"),
            )
            .where(and_(*conditions))
            .group_by(day)
            .order_by(day)
        )

        result = await self.session.execute(stmt)
        return [
            DailyTokenUsageMetric(
                day=row["day"],
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                embedding_tokens=int(row["embedding_tokens"]),
                total_tokens=int(row["total_tokens"]),
                request_count=int(row["request_count"]),
            )
            for row in result.mappings().all()
        ]

    async def get_user_usage_summary(
        self,
        *,
        user_id: uuid.UUID,
    ) -> MyTokenUsageSummary:
        """Return one user's total token usage plus a per-session breakdown."""
        input_tokens = func.coalesce(func.sum(TokenUsage.input_tokens), 0)
        output_tokens = func.coalesce(func.sum(TokenUsage.output_tokens), 0)
        embedding_tokens = func.coalesce(func.sum(TokenUsage.embedding_tokens), 0)
        total_tokens = func.coalesce(func.sum(TokenUsage.total_tokens), 0)
        request_count = func.count(TokenUsage.id)

        totals_stmt: Select[Any] = select(
            input_tokens.label("input_tokens"),
            output_tokens.label("output_tokens"),
            embedding_tokens.label("embedding_tokens"),
            total_tokens.label("total_tokens"),
            request_count.label("request_count"),
        ).where(TokenUsage.user_id == user_id)
        totals_row = (await self.session.execute(totals_stmt)).mappings().one()

        sessions_stmt: Select[Any] = (
            select(
                ChatSession.id.label("session_id"),
                ChatSession.title,
                ChatSession.bot_id,
                Bot.name.label("bot_name"),
                ChatSession.last_message_at,
                input_tokens.label("input_tokens"),
                output_tokens.label("output_tokens"),
                embedding_tokens.label("embedding_tokens"),
                total_tokens.label("total_tokens"),
                request_count.label("request_count"),
            )
            .join(TokenUsage, TokenUsage.session_id == ChatSession.id)
            .outerjoin(Bot, Bot.id == ChatSession.bot_id)
            .where(ChatSession.user_id == user_id, ChatSession.is_archived.is_(False))
            .group_by(
                ChatSession.id,
                ChatSession.title,
                ChatSession.bot_id,
                Bot.name,
                ChatSession.last_message_at,
            )
            .order_by(total_tokens.desc(), ChatSession.last_message_at.desc().nullslast())
        )
        session_rows = (await self.session.execute(sessions_stmt)).mappings().all()

        sessions = [
            SessionTokenUsageMetric(
                session_id=row["session_id"],
                title=row["title"],
                bot_id=row["bot_id"],
                bot_name=row["bot_name"],
                last_message_at=row["last_message_at"],
                input_tokens=int(row["input_tokens"]),
                output_tokens=int(row["output_tokens"]),
                embedding_tokens=int(row["embedding_tokens"]),
                total_tokens=int(row["total_tokens"]),
                request_count=int(row["request_count"]),
            )
            for row in session_rows
        ]

        return MyTokenUsageSummary(
            input_tokens=int(totals_row["input_tokens"]),
            output_tokens=int(totals_row["output_tokens"]),
            embedding_tokens=int(totals_row["embedding_tokens"]),
            total_tokens=int(totals_row["total_tokens"]),
            request_count=int(totals_row["request_count"]),
            session_count=len(sessions),
            sessions=sessions,
        )
