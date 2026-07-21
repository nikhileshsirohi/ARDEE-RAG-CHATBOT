"""Hybrid retrieval service for RAG."""

from app.config import Settings
from app.core.exceptions import BadRequestError
from app.repositories.rag_retrieval import HybridSearchResult, RagRetrievalRepository
from app.services.pdf_ingestion import OpenAIEmbeddingService


class RagRetrievalService:
    """Run hybrid retrieval for user/admin RAG queries."""

    def __init__(
        self,
        repository: RagRetrievalRepository,
        embedding_service: OpenAIEmbeddingService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.embedding_service = embedding_service
        self.settings = settings

    async def search(self, *, query: str, top_k: int | None = None) -> list[HybridSearchResult]:
        """Embed a query and retrieve the best matching document chunks."""
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise BadRequestError("Search query is required")

        limit = top_k or self.settings.rag_top_k
        embeddings = await self.embedding_service.embed_texts([normalized_query])

        return await self.repository.hybrid_search(
            query_text=normalized_query,
            query_embedding=embeddings[0],
            limit=limit,
        )
