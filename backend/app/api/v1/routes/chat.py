"""Authenticated RAG chatbot routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import ActiveUserDep, SessionDep
from app.config import get_settings
from app.repositories.chat import ChatRepository
from app.repositories.rag_retrieval import RagRetrievalRepository
from app.schemas.rag import ChatAskRequest, ChatAskResponse
from app.services.chat import ChatService, OpenAIChatAnswerService
from app.services.pdf_ingestion import OpenAIEmbeddingService
from app.services.rag_retrieval import RagRetrievalService

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
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


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
