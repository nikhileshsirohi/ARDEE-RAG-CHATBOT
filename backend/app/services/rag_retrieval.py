"""Embedding retrieval service for RAG."""

from app.config import Settings
from app.core.exceptions import BadRequestError
from app.repositories.rag_retrieval import HybridSearchResult, RagRetrievalRepository
from app.services.pdf_ingestion import OpenAIEmbeddingService


class RagRetrievalService:
    """Run embedding retrieval for user/admin RAG queries."""

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
        """Embed a query and retrieve the best matching chunks via hybrid search."""
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise BadRequestError("Search query is required")

        query_embedding = await self.embed_query(normalized_query)
        return await self.search_hybrid(
            query_text=normalized_query,
            query_embedding=query_embedding,
            top_k=top_k,
        )

    async def embed_query(self, query: str) -> list[float]:
        """Embed a normalized query."""
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise BadRequestError("Search query is required")

        embeddings = await self.embedding_service.embed_texts([normalized_query])
        return embeddings[0]

    async def search_by_embedding(
        self,
        *,
        query_embedding: list[float],
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        """Retrieve chunks using an existing query embedding (vector only)."""
        limit = top_k or self.settings.rag_top_k
        return await self.repository.vector_search(
            query_embedding=query_embedding,
            limit=limit,
        )

    async def search_hybrid(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        """Retrieve chunks by fusing vector similarity and keyword relevance."""
        limit = top_k or self.settings.rag_top_k
        return await self.repository.hybrid_search(
            query_text=query_text,
            query_embedding=query_embedding,
            limit=limit,
        )
