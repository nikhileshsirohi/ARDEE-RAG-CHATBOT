"""Repository for chat sessions, messages, and token usage."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import ChatMessage, ChatMessageRole, ChatSession, TokenUsage


class ChatRepository:
    """Database operations for user-owned chat history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, *, user_id: uuid.UUID, title: str) -> ChatSession:
        """Create a chat session for a user."""
        chat_session = ChatSession(user_id=user_id, title=title, last_message_at=datetime.now(UTC))
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
        request_metadata: dict[str, object] | None = None,
    ) -> TokenUsage:
        """Persist token usage for metrics and cost monitoring."""
        token_usage = TokenUsage(
            user_id=user_id,
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
