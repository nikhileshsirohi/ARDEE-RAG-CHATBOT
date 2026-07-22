"""Repository for RAG retrieval."""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class HybridSearchResult:
    """One retrieved document chunk with ranking metadata."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    original_filename: str
    page_number: int | None
    content: str
    token_count: int
    vector_score: float
    keyword_score: float
    hybrid_score: float


class RagRetrievalRepository:
    """Vector retrieval over ingested document chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def vector_search(
        self,
        *,
        query_embedding: list[float],
        limit: int,
        bot_id: uuid.UUID,
    ) -> list[HybridSearchResult]:
        """Search READY document chunks (for one bot) by embedding similarity."""
        embedding_literal = self._to_vector_literal(query_embedding)
        stmt = text(
            """
            WITH query AS (
                SELECT CAST(:query_embedding AS vector) AS embedding
            )
            SELECT
                dc.id AS chunk_id,
                dc.document_id,
                rd.title AS document_title,
                rd.original_filename,
                dc.page_number,
                dc.content,
                dc.token_count,
                1 - (dc.embedding <=> query.embedding) AS vector_score,
                0.0 AS keyword_score,
                0.0 AS hybrid_score
            FROM document_chunks dc
            JOIN rag_documents rd ON rd.id = dc.document_id
            CROSS JOIN query
            WHERE rd.status = 'READY'
              AND rd.deleted_at IS NULL
              AND rd.bot_id = :bot_id
            ORDER BY dc.embedding <=> query.embedding
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            stmt,
            {
                "query_embedding": embedding_literal,
                "limit": limit,
                "bot_id": str(bot_id),
            },
        )

        return [
            HybridSearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                original_filename=row["original_filename"],
                page_number=row["page_number"],
                content=row["content"],
                token_count=row["token_count"],
                vector_score=float(row["vector_score"] or 0),
                keyword_score=0.0,
                hybrid_score=0.0,
            )
            for row in result.mappings().all()
        ]

    async def hybrid_search(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        limit: int,
        bot_id: uuid.UUID,
    ) -> list[HybridSearchResult]:
        """Search READY chunks with vector + keyword retrieval.

        Two candidate sets are gathered independently: nearest neighbors by
        embedding cosine distance, and best full-text matches via ``ts_rank_cd``.
        The final ``hybrid_score`` is a calibrated 0-1 confidence value derived
        from the actual vector score and normalized keyword strength, so it is
        useful both for ranking and for explaining retrieval confidence.
        """
        candidate_limit = max(limit * 5, 20)
        embedding_literal = self._to_vector_literal(query_embedding)

        stmt = text(
            """
            WITH query AS (
                SELECT
                    CAST(:query_embedding AS vector) AS embedding,
                    websearch_to_tsquery('english', :query_text) AS ts_query
            ),
            vector_results AS (
                SELECT
                    dc.id AS chunk_id,
                    dc.document_id,
                    rd.title AS document_title,
                    rd.original_filename,
                    dc.page_number,
                    dc.content,
                    dc.token_count,
                    1 - (dc.embedding <=> query.embedding) AS vector_score,
                    0.0 AS keyword_score,
                    row_number() OVER (ORDER BY dc.embedding <=> query.embedding) AS vector_rank,
                    NULL::bigint AS keyword_rank
                FROM document_chunks dc
                JOIN rag_documents rd ON rd.id = dc.document_id
                CROSS JOIN query
                WHERE rd.status = 'READY'
                  AND rd.deleted_at IS NULL
                  AND rd.bot_id = :bot_id
                ORDER BY dc.embedding <=> query.embedding
                LIMIT :candidate_limit
            ),
            keyword_results AS (
                SELECT
                    dc.id AS chunk_id,
                    dc.document_id,
                    rd.title AS document_title,
                    rd.original_filename,
                    dc.page_number,
                    dc.content,
                    dc.token_count,
                    0.0 AS vector_score,
                    ts_rank_cd(dc.search_vector, query.ts_query) AS keyword_score,
                    NULL::bigint AS vector_rank,
                    row_number() OVER (
                        ORDER BY ts_rank_cd(dc.search_vector, query.ts_query) DESC
                    ) AS keyword_rank
                FROM document_chunks dc
                JOIN rag_documents rd ON rd.id = dc.document_id
                CROSS JOIN query
                WHERE rd.status = 'READY'
                  AND rd.deleted_at IS NULL
                  AND rd.bot_id = :bot_id
                  AND query.ts_query IS NOT NULL
                  AND dc.search_vector @@ query.ts_query
                ORDER BY keyword_score DESC
                LIMIT :candidate_limit
            ),
            combined AS (
                SELECT * FROM vector_results
                UNION ALL
                SELECT * FROM keyword_results
            )
            SELECT
                chunk_id,
                document_id,
                document_title,
                original_filename,
                page_number,
                content,
                token_count,
                max(vector_score) AS vector_score,
                max(keyword_score) AS keyword_score,
                least(
                    1.0,
                    greatest(
                        0.0,
                        0.7 * greatest(max(vector_score), 0.0)
                        + 0.3 * (
                            max(keyword_score) / nullif(max(keyword_score) + 0.1, 0)
                        )
                    )
                ) AS hybrid_score
            FROM combined
            GROUP BY
                chunk_id,
                document_id,
                document_title,
                original_filename,
                page_number,
                content,
                token_count
            ORDER BY hybrid_score DESC, vector_score DESC, keyword_score DESC
            LIMIT :limit
            """
        )
        result = await self.session.execute(
            stmt,
            {
                "query_embedding": embedding_literal,
                "query_text": query_text,
                "candidate_limit": candidate_limit,
                "limit": limit,
                "bot_id": str(bot_id),
            },
        )
        return [
            HybridSearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                original_filename=row["original_filename"],
                page_number=row["page_number"],
                content=row["content"],
                token_count=row["token_count"],
                vector_score=float(row["vector_score"] or 0),
                keyword_score=float(row["keyword_score"] or 0),
                hybrid_score=float(row["hybrid_score"] or 0),
            )
            for row in result.mappings().all()
        ]

    @staticmethod
    def _to_vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(value) for value in embedding) + "]"
