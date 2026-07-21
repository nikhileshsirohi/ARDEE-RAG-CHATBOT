"""Tests for embedding RAG retrieval."""

import uuid

import pytest

from app.config import Settings
from app.core.exceptions import BadRequestError
from app.main import create_app
from app.repositories.rag_retrieval import HybridSearchResult, RagRetrievalRepository
from app.services.rag_retrieval import RagRetrievalService


class FakeRetrievalRepository:
    """Capture retrieval inputs and return deterministic results."""

    def __init__(self) -> None:
        self.query_embedding: list[float] | None = None
        self.query_text: str | None = None
        self.limit: int | None = None

    def _results(self) -> list[HybridSearchResult]:
        return [
            HybridSearchResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="Policy",
                original_filename="policy.pdf",
                page_number=1,
                content="Policy content",
                token_count=2,
                vector_score=0.9,
                keyword_score=0,
                hybrid_score=0,
            )
        ]

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        limit: int,
    ) -> list[HybridSearchResult]:
        self.query_embedding = query_embedding
        self.limit = limit
        return self._results()

    async def hybrid_search(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[HybridSearchResult]:
        self.query_text = query_text
        self.query_embedding = query_embedding
        self.limit = limit
        return self._results()


class FakeEmbeddingService:
    """Return a deterministic query embedding."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(texts[0]))] * 1536]


def test_vector_literal_format_is_pgvector_compatible() -> None:
    """Raw SQL binds vector values as pgvector literals."""
    literal = RagRetrievalRepository._to_vector_literal([0.1, -0.2, 3.0])

    assert literal == "[0.1,-0.2,3.0]"


@pytest.mark.anyio
async def test_retrieval_service_normalizes_query_and_uses_default_top_k() -> None:
    """Search service should normalize query text and use configured top_k."""
    repository = FakeRetrievalRepository()
    service = RagRetrievalService(
        repository=repository,  # type: ignore[arg-type]
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
        settings=Settings(rag_top_k=7),
    )

    results = await service.search(query="  employee   policy  ")

    assert len(results) == 1
    assert repository.limit == 7
    assert repository.query_embedding == [15.0] * 1536


@pytest.mark.anyio
async def test_retrieval_service_allows_request_top_k_override() -> None:
    """Request top_k should override configured default."""
    repository = FakeRetrievalRepository()
    service = RagRetrievalService(
        repository=repository,  # type: ignore[arg-type]
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
        settings=Settings(rag_top_k=7),
    )

    await service.search(query="policy", top_k=3)

    assert repository.limit == 3


@pytest.mark.anyio
async def test_retrieval_service_rejects_blank_query() -> None:
    """Whitespace-only queries should not call embeddings or retrieval."""
    service = RagRetrievalService(
        repository=FakeRetrievalRepository(),  # type: ignore[arg-type]
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
        settings=Settings(),
    )

    with pytest.raises(BadRequestError, match="Search query is required"):
        await service.search(query="   ")


def test_rag_search_route_is_registered() -> None:
    """Embedding search route should be available under API v1."""
    app = create_app()
    route_paths = set(app.openapi()["paths"].keys())

    assert "/api/v1/rag/search" in route_paths
