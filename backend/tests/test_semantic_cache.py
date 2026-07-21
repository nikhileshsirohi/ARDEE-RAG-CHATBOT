"""Tests for Redis-backed semantic cache service."""

import json

import pytest

from app.config import Settings
from app.services.semantic_cache import (
    SEMANTIC_CACHE_INDEX_KEY,
    SemanticCacheService,
)


class FakeRedis:
    """In-memory Redis fake for semantic cache tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}

    async def smembers(self, name: str) -> set[str]:
        return self.sets.get(name, set())

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def setex(self, name: str, time: int, value: str) -> None:
        self.values[name] = value
        self.ttls[name] = time

    async def sadd(self, name: str, *values: str) -> None:
        self.sets.setdefault(name, set()).update(values)

    async def expire(self, name: str, time: int) -> None:
        self.ttls[name] = time


@pytest.mark.anyio
async def test_semantic_cache_returns_best_match_above_threshold() -> None:
    """Cache lookup should use cosine similarity over stored embeddings."""
    redis = FakeRedis()
    service = SemanticCacheService(
        redis,
        Settings(semantic_cache_threshold=0.9, semantic_cache_ttl_seconds=60),
    )
    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[],
        input_tokens=10,
        output_tokens=5,
    )

    hit = await service.get(query_embedding=[0.99, 0.01])

    assert hit is not None
    assert hit.answer == "Policy answer"
    assert hit.similarity > 0.9


@pytest.mark.anyio
async def test_semantic_cache_misses_below_threshold() -> None:
    """Low semantic similarity should not return cached answers."""
    redis = FakeRedis()
    service = SemanticCacheService(redis, Settings(semantic_cache_threshold=0.95))
    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[],
        input_tokens=10,
        output_tokens=5,
    )

    hit = await service.get(query_embedding=[0.0, 1.0])

    assert hit is None


@pytest.mark.anyio
async def test_semantic_cache_stores_payload_with_ttl() -> None:
    """Cache writes should persist entry payload and index TTL."""
    redis = FakeRedis()
    service = SemanticCacheService(redis, Settings(semantic_cache_ttl_seconds=123))

    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[{"source_number": 1}],
        input_tokens=10,
        output_tokens=5,
    )

    cache_id = next(iter(redis.sets[SEMANTIC_CACHE_INDEX_KEY]))
    payload = json.loads(redis.values[f"semantic_cache:entry:{cache_id}"])

    assert payload["answer"] == "Policy answer"
    assert payload["source_citations"] == [{"source_number": 1}]
    assert redis.ttls[SEMANTIC_CACHE_INDEX_KEY] == 123
