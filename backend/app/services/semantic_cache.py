"""Redis-backed semantic cache for RAG answers."""

import json
import math
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings

SEMANTIC_CACHE_INDEX_KEY = "semantic_cache:entries"
SEMANTIC_CACHE_ENTRY_PREFIX = "semantic_cache:entry:"


class RedisLike(Protocol):
    """Small Redis protocol used by the semantic cache service."""

    async def smembers(self, name: str) -> set[str]:
        """Return set members."""

    async def get(self, name: str) -> str | None:
        """Return a string value."""

    async def setex(self, name: str, time: int, value: str) -> object:
        """Set a string value with TTL."""

    async def sadd(self, name: str, *values: str) -> object:
        """Add values to a set."""

    async def expire(self, name: str, time: int) -> object:
        """Set key TTL."""


@dataclass(frozen=True)
class SemanticCacheHit:
    """Semantic cache hit payload."""

    answer: str
    source_citations: list[dict[str, object]]
    input_tokens: int
    output_tokens: int
    similarity: float


class SemanticCacheService:
    """Find and store semantically similar RAG answers in Redis."""

    def __init__(self, redis_client: RedisLike, settings: Settings) -> None:
        self.redis_client = redis_client
        self.settings = settings

    async def get(
        self,
        *,
        query_embedding: list[float],
    ) -> SemanticCacheHit | None:
        """Return the best cache hit above the configured similarity threshold."""
        best_hit: SemanticCacheHit | None = None

        for cache_id in await self.redis_client.smembers(SEMANTIC_CACHE_INDEX_KEY):
            raw_entry = await self.redis_client.get(self._entry_key(cache_id))
            if raw_entry is None:
                continue

            entry = json.loads(raw_entry)
            cached_embedding = [float(value) for value in entry["query_embedding"]]
            similarity = self._cosine_similarity(query_embedding, cached_embedding)
            if similarity < self.settings.semantic_cache_threshold:
                continue

            candidate = SemanticCacheHit(
                answer=entry["answer"],
                source_citations=entry["source_citations"],
                input_tokens=int(entry["input_tokens"]),
                output_tokens=int(entry["output_tokens"]),
                similarity=similarity,
            )
            if best_hit is None or candidate.similarity > best_hit.similarity:
                best_hit = candidate

        return best_hit

    async def set(
        self,
        *,
        query: str,
        query_embedding: list[float],
        answer: str,
        source_citations: list[dict[str, object]],
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Store an answer with its query embedding."""
        cache_id = str(uuid.uuid4())
        payload = {
            "query": query,
            "query_embedding": query_embedding,
            "answer": answer,
            "source_citations": source_citations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        ttl_seconds = self.settings.semantic_cache_ttl_seconds
        await self.redis_client.setex(
            self._entry_key(cache_id),
            ttl_seconds,
            json.dumps(payload),
        )
        await self.redis_client.sadd(SEMANTIC_CACHE_INDEX_KEY, cache_id)
        await self.redis_client.expire(SEMANTIC_CACHE_INDEX_KEY, ttl_seconds)

    @staticmethod
    def _entry_key(cache_id: str) -> str:
        return f"{SEMANTIC_CACHE_ENTRY_PREFIX}{cache_id}"

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0

        dot_product = sum(
            left_value * right_value for left_value, right_value in zip(left, right, strict=True)
        )
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0

        return dot_product / (left_norm * right_norm)
