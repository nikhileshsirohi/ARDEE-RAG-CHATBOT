"""Tests for Redis-backed semantic cache service."""

import json
import uuid

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

    async def delete(self, *names: str) -> None:
        for name in names:
            self.values.pop(name, None)
            self.sets.pop(name, None)
            self.ttls.pop(name, None)


@pytest.mark.anyio
async def test_semantic_cache_returns_best_match_above_threshold() -> None:
    """Cache lookup should use cosine similarity over stored embeddings."""
    redis = FakeRedis()
    bot_id = uuid.uuid4()
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
        bot_id=bot_id,
    )

    hit = await service.get(query_embedding=[0.99, 0.01], bot_id=bot_id)

    assert hit is not None
    assert hit.answer == "Policy answer"
    assert hit.similarity > 0.9


@pytest.mark.anyio
async def test_semantic_cache_misses_below_threshold() -> None:
    """Low semantic similarity should not return cached answers."""
    redis = FakeRedis()
    bot_id = uuid.uuid4()
    service = SemanticCacheService(redis, Settings(semantic_cache_threshold=0.95))
    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[],
        input_tokens=10,
        output_tokens=5,
        bot_id=bot_id,
    )

    hit = await service.get(query_embedding=[0.0, 1.0], bot_id=bot_id)

    assert hit is None


@pytest.mark.anyio
async def test_semantic_cache_stores_payload_with_ttl() -> None:
    """Cache writes should persist entry payload and index TTL."""
    redis = FakeRedis()
    bot_id = uuid.uuid4()
    service = SemanticCacheService(redis, Settings(semantic_cache_ttl_seconds=123))

    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[{"source_number": 1}],
        input_tokens=10,
        output_tokens=5,
        bot_id=bot_id,
    )

    index_key = f"{SEMANTIC_CACHE_INDEX_KEY}:{bot_id}"
    cache_id = next(iter(redis.sets[index_key]))
    payload = json.loads(redis.values[f"semantic_cache:entry:{cache_id}"])

    assert payload["answer"] == "Policy answer"
    assert payload["source_citations"] == [{"source_number": 1}]
    assert redis.ttls[index_key] == 123


@pytest.mark.anyio
async def test_semantic_cache_clear_bot_removes_entries_and_index() -> None:
    """Invalidating a bot should delete all of its cached answers."""
    redis = FakeRedis()
    bot_id = uuid.uuid4()
    service = SemanticCacheService(redis, Settings(semantic_cache_ttl_seconds=123))

    await service.set(
        query="policy",
        query_embedding=[1.0, 0.0],
        answer="Policy answer",
        source_citations=[],
        input_tokens=10,
        output_tokens=5,
        bot_id=bot_id,
    )
    index_key = f"{SEMANTIC_CACHE_INDEX_KEY}:{bot_id}"
    cache_id = next(iter(redis.sets[index_key]))

    await service.clear_bot(bot_id=bot_id)

    assert index_key not in redis.sets
    assert f"semantic_cache:entry:{cache_id}" not in redis.values
