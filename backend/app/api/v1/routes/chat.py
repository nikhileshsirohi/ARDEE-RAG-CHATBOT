"""Authenticated RAG chatbot routes."""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query

from app.api.dependencies.auth import ActiveUserDep, SessionDep
from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.redis import get_redis_client
from app.repositories.chat import ChatRepository
from app.repositories.rag_retrieval import RagRetrievalRepository
from app.schemas.rag import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
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
        session_id=request.session_id,
        top_k=request.top_k,
    )
    return ChatAskResponse(**answer.__dict__)


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
) -> list[ChatSessionResponse]:
    """List only sessions owned by the authenticated user."""
    sessions = await repository.list_user_sessions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [ChatSessionResponse.model_validate(session) for session in sessions]


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
    return ChatSessionDetailResponse(
        session=ChatSessionResponse.model_validate(chat_session),
        messages=[ChatMessageResponse.model_validate(message) for message in messages],
    )
