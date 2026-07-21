"""Authenticated RAG hybrid search routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import ActiveUserDep, SessionDep
from app.config import get_settings
from app.repositories.rag_retrieval import RagRetrievalRepository
from app.schemas.rag import RagSearchRequest, RagSearchResponse, RagSearchResult
from app.services.pdf_ingestion import OpenAIEmbeddingService
from app.services.rag_retrieval import RagRetrievalService

router = APIRouter(prefix="/rag/search", tags=["RAG Search"])


def get_retrieval_service(session: SessionDep) -> RagRetrievalService:
    """Build retrieval service from request-scoped dependencies."""
    settings = get_settings()
    return RagRetrievalService(
        repository=RagRetrievalRepository(session),
        embedding_service=OpenAIEmbeddingService(settings),
        settings=settings,
    )


RetrievalServiceDep = Annotated[RagRetrievalService, Depends(get_retrieval_service)]


@router.post("", response_model=RagSearchResponse, summary="Hybrid search RAG chunks")
async def search_rag_chunks(
    request: RagSearchRequest,
    _current_user: ActiveUserDep,
    service: RetrievalServiceDep,
) -> RagSearchResponse:
    """Search ingested RAG chunks. Any active user can retrieve context."""
    normalized_query = " ".join(request.query.split())
    results = await service.search(query=normalized_query, top_k=request.top_k)

    return RagSearchResponse(
        query=normalized_query,
        results=[RagSearchResult(**result.__dict__) for result in results],
    )
