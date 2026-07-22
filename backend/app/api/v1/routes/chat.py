"""Authenticated RAG chatbot routes."""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from app.api.dependencies.auth import ActiveUserDep, SessionDep
from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.redis import get_redis_client
from app.repositories.bot import BotRepository
from app.repositories.chat import ChatRepository
from app.repositories.metrics import MetricsRepository
from app.repositories.rag_retrieval import RagRetrievalRepository
from app.schemas.rag import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    ChatSessionUpdate,
    MyTokenUsageSummary,
)
from app.services.chat import ChatService, OpenAIChatAnswerService
from app.services.pdf_ingestion import OpenAIEmbeddingService
from app.services.rag_retrieval import RagRetrievalService
from app.services.semantic_cache import RedisLike, SemanticCacheService

router = APIRouter(prefix="/chat", tags=["Chat"])


def get_chat_service(session: SessionDep) -> ChatService:
    """Build chat service from request-scoped dependencies."""
    settings = get_settings()
    retrieval_service = RagRetrievalService(
        repository=RagRetrievalRepository(session),
        embedding_service=OpenAIEmbeddingService(settings),
        settings=settings,
    )
    return ChatService(
        chat_repository=ChatRepository(session),
        bot_repository=BotRepository(session),
        retrieval_service=retrieval_service,
        answer_service=OpenAIChatAnswerService(settings),
        settings=settings,
        semantic_cache_service=SemanticCacheService(cast(RedisLike, get_redis_client()), settings),
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_chat_repository(session: SessionDep) -> ChatRepository:
    """Build request-scoped chat repository."""
    return ChatRepository(session)


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]


def get_metrics_repository(session: SessionDep) -> MetricsRepository:
    """Build request-scoped metrics repository."""
    return MetricsRepository(session)


MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


@router.post("/ask", response_model=ChatAskResponse, summary="Ask the RAG chatbot")
async def ask_chatbot(
    request: ChatAskRequest,
    current_user: ActiveUserDep,
    service: ChatServiceDep,
) -> ChatAskResponse:
    """Ask a question against ingested RAG documents."""
    answer = await service.ask(
        user=current_user,
        question=request.question,
        bot_id=request.bot_id,
        session_id=request.session_id,
        top_k=request.top_k,
    )
    return ChatAskResponse(**answer.__dict__)


@router.post(
    "/ask/stream",
    summary="Ask the RAG chatbot with a streamed answer",
    response_class=StreamingResponse,
)
async def ask_chatbot_stream(
    request: ChatAskRequest,
    current_user: ActiveUserDep,
    service: ChatServiceDep,
) -> StreamingResponse:
    """Ask a question and stream the answer token-by-token via Server-Sent Events.

    Each SSE ``data:`` line carries a JSON event:
        - ``{"type": "meta", "session_id": ...}`` — emitted first.
        - ``{"type": "token", "text": ...}`` — incremental answer text.
        - ``{"type": "done", ...}`` — final message id, citations, and token usage.
        - ``{"type": "error", "message": ...}`` — a failure occurred mid-stream.
    """

    async def event_stream() -> AsyncGenerator[str]:
        try:
            async for event in service.ask_stream(
                user=current_user,
                question=request.question,
                bot_id=request.bot_id,
                session_id=request.session_id,
                top_k=request.top_k,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # surface a clean SSE error to the client
            payload = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/usage/me",
    response_model=MyTokenUsageSummary,
    summary="Get my token usage totals and per-session breakdown",
)
async def get_my_token_usage(
    current_user: ActiveUserDep,
    repository: MetricsRepositoryDep,
) -> MyTokenUsageSummary:
    """Return the authenticated user's own token usage: totals plus per session."""
    return await repository.get_user_usage_summary(user_id=current_user.id)


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
    summary="List my chat sessions",
)
async def list_my_chat_sessions(
    current_user: ActiveUserDep,
    repository: ChatRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    bot_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ChatSessionResponse]:
    """List only sessions owned by the authenticated user, optionally per bot."""
    sessions = await repository.list_user_sessions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        bot_id=bot_id,
    )
    token_totals = await repository.sum_tokens_by_session(
        session_ids=[session.id for session in sessions]
    )
    return [
        ChatSessionResponse(
            id=session.id,
            user_id=session.user_id,
            bot_id=session.bot_id,
            title=session.title,
            last_message_at=session.last_message_at,
            is_archived=session.is_archived,
            created_at=session.created_at,
            updated_at=session.updated_at,
            total_tokens=token_totals.get(session.id, 0),
        )
        for session in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="Get my chat session history",
)
async def get_my_chat_session(
    session_id: uuid.UUID,
    current_user: ActiveUserDep,
    repository: ChatRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatSessionDetailResponse:
    """Return one session and its messages only when owned by the current user."""
    chat_session = await repository.get_user_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    if chat_session is None:
        raise NotFoundError("Chat session not found")

    messages = await repository.list_session_messages(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    token_totals = await repository.sum_tokens_by_session(session_ids=[chat_session.id])
    session_payload = ChatSessionResponse.model_validate(chat_session).model_copy(
        update={"total_tokens": token_totals.get(chat_session.id, 0)}
    )
    return ChatSessionDetailResponse(
        session=session_payload,
        messages=[ChatMessageResponse.model_validate(message) for message in messages],
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Rename my chat session",
)
async def rename_my_chat_session(
    session_id: uuid.UUID,
    payload: ChatSessionUpdate,
    current_user: ActiveUserDep,
    repository: ChatRepositoryDep,
) -> ChatSessionResponse:
    """Rename a chat session owned by the current user."""
    chat_session = await repository.get_user_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    if chat_session is None:
        raise NotFoundError("Chat session not found")

    updated = await repository.rename_session(session=chat_session, title=payload.title)
    return ChatSessionResponse.model_validate(updated)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete my chat session",
)
async def delete_my_chat_session(
    session_id: uuid.UUID,
    current_user: ActiveUserDep,
    repository: ChatRepositoryDep,
) -> Response:
    """Delete a chat session and its messages, owned by the current user."""
    chat_session = await repository.get_user_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    if chat_session is None:
        raise NotFoundError("Chat session not found")

    await repository.delete_session(session=chat_session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
