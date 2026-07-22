"""Repository for chat sessions, messages, and token usage."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import ChatMessage, ChatMessageRole, ChatSession, TokenUsage


class ChatRepository:
    """Database operations for user-owned chat history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        bot_id: uuid.UUID | None = None,
    ) -> ChatSession:
        """Create a chat session for a user, scoped to a bot."""
        chat_session = ChatSession(
            user_id=user_id,
            bot_id=bot_id,
            title=title,
            last_message_at=datetime.now(UTC),
        )
        self.session.add(chat_session)
        await self.session.flush()
        await self.session.refresh(chat_session)
        return chat_session

    async def get_user_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession | None:
        """Return a session only when it belongs to the current user."""
        stmt: Select[tuple[ChatSession]] = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.is_archived.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def rename_session(
        self,
        *,
        session: ChatSession,
        title: str,
    ) -> ChatSession:
        """Rename a chat session owned by the user."""
        session.title = title
        self.session.add(session)
        await self.session.flush()
        await self.session.refresh(session)
        return session

    async def delete_session(self, *, session: ChatSession) -> None:
        """Delete a chat session and its messages.

        Token usage rows survive (their ``session_id`` is set NULL by the FK),
        so aggregate usage metrics remain accurate after deletion.
        """
        await self.session.delete(session)
        await self.session.flush()

    async def list_user_sessions(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
        bot_id: uuid.UUID | None = None,
    ) -> list[ChatSession]:
        """List active sessions owned by a user, optionally scoped to a bot."""
        stmt: Select[tuple[ChatSession]] = select(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.is_archived.is_(False),
        )
        if bot_id is not None:
            stmt = stmt.where(ChatSession.bot_id == bot_id)
        stmt = (
            stmt.order_by(
                ChatSession.last_message_at.desc().nullslast(), ChatSession.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def sum_tokens_by_session(
        self,
        *,
        session_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Return total token usage keyed by chat session id."""
        if not session_ids:
            return {}
        stmt = (
            select(
                TokenUsage.session_id,
                func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            )
            .where(TokenUsage.session_id.in_(session_ids))
            .group_by(TokenUsage.session_id)
        )
        result = await self.session.execute(stmt)
        return {
            row.session_id: int(row.total_tokens)
            for row in result.all()
            if row.session_id is not None
        }

    async def list_session_messages(
        self,
        *,
        session_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[ChatMessage]:
        """List messages for one owned session."""
        stmt: Select[tuple[ChatMessage]] = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_session_messages(
        self,
        *,
        session_id: uuid.UUID,
        limit: int,
    ) -> list[ChatMessage]:
        """List recent messages for prompt memory in chronological order."""
        stmt: Select[tuple[ChatMessage]] = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def add_message(
        self,
        *,
        session: ChatSession,
        role: ChatMessageRole,
        content: str,
        source_citations: list[dict[str, object]] | None = None,
        latency_ms: int | None = None,
    ) -> ChatMessage:
        """Append a message to a chat session."""
        message = ChatMessage(
            session_id=session.id,
            role=role,
            content=content,
            source_citations=source_citations or [],
            latency_ms=latency_ms,
        )
        session.last_message_at = datetime.now(UTC)
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def record_token_usage(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        message_id: uuid.UUID | None,
        model_name: str,
        embedding_model_name: str | None,
        input_tokens: int,
        output_tokens: int,
        embedding_tokens: int,
        bot_id: uuid.UUID | None = None,
        request_metadata: dict[str, object] | None = None,
    ) -> TokenUsage:
        """Persist token usage for metrics and cost monitoring."""
        token_usage = TokenUsage(
            user_id=user_id,
            bot_id=bot_id,
            session_id=session_id,
            message_id=message_id,
            model_name=model_name,
            embedding_model_name=embedding_model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
            total_tokens=input_tokens + output_tokens + embedding_tokens,
            request_metadata=request_metadata or {},
        )
        self.session.add(token_usage)
        await self.session.flush()
        await self.session.refresh(token_usage)
        return token_usage

    async def commit(self) -> None:
        """Persist the current transaction.

        Used by the streaming chat endpoint, where the response body is produced
        by a generator that runs after the route returns, so persistence must be
        committed explicitly instead of relying on the request-scoped auto-commit.
        """
        await self.session.commit()

    async def rollback(self) -> None:
        """Discard uncommitted work (used when a streamed answer fails mid-flight)."""
        await self.session.rollback()
