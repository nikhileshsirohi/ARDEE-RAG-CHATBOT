"""Tests for RAG chatbot orchestration."""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.main import create_app
from app.models.rag import Bot, ChatMessage, ChatMessageRole, ChatSession
from app.models.user import User, UserRole
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.chat import (
    LOW_CONFIDENCE_ANSWER,
    AnswerStreamChunk,
    ChatService,
    GeneratedAnswer,
    OpenAIChatAnswerService,
)
from app.services.semantic_cache import SemanticCacheHit

BOT_ID = uuid.uuid4()


def make_bot() -> Bot:
    """Create a test bot model."""
    return Bot(
        id=BOT_ID,
        name="Test Bot",
        description="A test bot",
        system_prompt="You are a test bot.",
        is_active=True,
    )


class FakeBotRepository:
    """In-memory fake returning a single active bot."""

    def __init__(self, bot: Bot | None = None) -> None:
        self.bot = bot or make_bot()

    async def get_active_by_id(self, bot_id: uuid.UUID) -> Bot | None:
        _ = bot_id
        return self.bot


class FakeChatRepository:
    """In-memory fake for chat persistence tests."""

    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, ChatSession] = {}
        self.messages: list[ChatMessage] = []
        self.token_usage_records: list[dict[str, object]] = []
        self.recent_messages_call_count = 0

    async def create_session(
        self, *, user_id: uuid.UUID, title: str, bot_id: uuid.UUID | None = None
    ) -> ChatSession:
        chat_session = ChatSession(
            id=uuid.uuid4(), user_id=user_id, bot_id=bot_id, title=title
        )
        self.sessions[chat_session.id] = chat_session
        return chat_session

    async def get_user_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession | None:
        chat_session = self.sessions.get(session_id)
        if chat_session is None or chat_session.user_id != user_id:
            return None
        return chat_session

    async def list_user_sessions(
        self,
        *,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
        bot_id: uuid.UUID | None = None,
    ) -> list[ChatSession]:
        sessions = [
            session
            for session in self.sessions.values()
            if session.user_id == user_id
            and not session.is_archived
            and (bot_id is None or session.bot_id == bot_id)
        ]
        return sessions[offset : offset + limit]

    async def list_session_messages(
        self,
        *,
        session_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> list[ChatMessage]:
        messages = [message for message in self.messages if message.session_id == session_id]
        return messages[offset : offset + limit]

    async def list_recent_session_messages(
        self,
        *,
        session_id: uuid.UUID,
        limit: int,
    ) -> list[ChatMessage]:
        self.recent_messages_call_count += 1
        messages = [message for message in self.messages if message.session_id == session_id]
        return messages[-limit:]

    async def add_message(
        self,
        *,
        session: ChatSession,
        role: ChatMessageRole,
        content: str,
        source_citations: list[dict[str, object]] | None = None,
        latency_ms: int | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role=role,
            content=content,
            source_citations=source_citations or [],
            latency_ms=latency_ms,
        )
        self.messages.append(message)
        return message

    async def record_token_usage(self, **kwargs: object) -> None:
        self.token_usage_records.append(kwargs)

    async def commit(self) -> None:
        self.commit_call_count = getattr(self, "commit_call_count", 0) + 1

    async def rollback(self) -> None:
        self.rollback_call_count = getattr(self, "rollback_call_count", 0) + 1


class FakeRetrievalService:
    """Return deterministic RAG chunks."""

    def __init__(
        self,
        *,
        hybrid_scores: list[float] | None = None,
        vector_scores: list[float] | None = None,
        keyword_scores: list[float] | None = None,
    ) -> None:
        self.hybrid_scores = hybrid_scores or [0.7]
        self.vector_scores = vector_scores or [0.91 for _score in self.hybrid_scores]
        self.keyword_scores = keyword_scores or [0.5 for _score in self.hybrid_scores]
        self.search_call_count = 0
        self.query_embedding = [0.5] * 1536

    async def embed_query(self, query: str) -> list[float]:
        _ = query
        return self.query_embedding

    async def search(
        self,
        *,
        query: str,
        bot_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = query
        _ = top_k
        _ = bot_id
        return await self.search_by_embedding(query_embedding=self.query_embedding, top_k=top_k)

    async def search_hybrid(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        bot_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = query_text
        _ = bot_id
        return await self.search_by_embedding(query_embedding=query_embedding, top_k=top_k)

    async def search_by_embedding(
        self,
        *,
        query_embedding: list[float],
        bot_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = query_embedding
        _ = top_k
        _ = bot_id
        self.search_call_count += 1
        return [
            HybridSearchResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title=f"HR Policy {index}",
                original_filename="hr-policy.pdf",
                page_number=3,
                content=f"Context {index}",
                token_count=4,
                vector_score=self.vector_scores[index - 1],
                keyword_score=self.keyword_scores[index - 1],
                hybrid_score=hybrid_score,
            )
            for index, hybrid_score in enumerate(self.hybrid_scores, start=1)
        ]


class FakeAnswerService:
    """Return a deterministic answer."""

    def __init__(self) -> None:
        self.chat_history: list[ChatMessage] | None = None
        self.retrieved_chunks: list[HybridSearchResult] | None = None
        self.was_called = False
        self.greeting_called = False

    async def answer_greeting(self, *, question: str) -> GeneratedAnswer:
        self.greeting_called = True
        return GeneratedAnswer(
            answer=f"Hello! How can I help you with the documents? ({question})",
            input_tokens=3,
            output_tokens=9,
        )

    async def answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
        chat_history: list[ChatMessage],
        system_prompt: str = "",
    ) -> GeneratedAnswer:
        self.was_called = True
        self.chat_history = chat_history
        self.retrieved_chunks = retrieved_chunks
        self.system_prompt = system_prompt
        return GeneratedAnswer(
            answer=f"Answer for {question} with {len(retrieved_chunks)} source",
            input_tokens=11,
            output_tokens=7,
        )

    async def stream_answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
        chat_history: list[ChatMessage],
        system_prompt: str = "",
    ) -> AsyncIterator[AnswerStreamChunk]:
        self.was_called = True
        self.chat_history = chat_history
        self.system_prompt = system_prompt
        self.retrieved_chunks = retrieved_chunks
        answer = f"Answer for {question} with {len(retrieved_chunks)} source"
        for word in answer.split(" "):
            yield AnswerStreamChunk(text=f"{word} ")
        yield AnswerStreamChunk(input_tokens=11, output_tokens=7)


class FakeSemanticCacheService:
    """Fake semantic cache service for chat tests."""

    def __init__(self, hit: SemanticCacheHit | None = None) -> None:
        self.hit = hit
        self.get_call_count = 0
        self.set_call_count = 0
        self.set_payload: dict[str, object] | None = None

    async def get(
        self, *, query_embedding: list[float], bot_id: uuid.UUID | None = None
    ) -> SemanticCacheHit | None:
        _ = query_embedding
        _ = bot_id
        self.get_call_count += 1
        return self.hit

    async def set(
        self,
        *,
        query: str,
        query_embedding: list[float],
        answer: str,
        source_citations: list[dict[str, object]],
        input_tokens: int,
        output_tokens: int,
        bot_id: uuid.UUID | None = None,
    ) -> None:
        self.set_call_count += 1
        self.set_payload = {
            "query": query,
            "query_embedding": query_embedding,
            "answer": answer,
            "source_citations": source_citations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "bot_id": bot_id,
        }


def make_user() -> User:
    """Create a test user model."""
    return User(
        id=uuid.uuid4(),
        email="user@example.com",
        full_name="Test User",
        password_hash="".join(["hash", "ed"]),
        role=UserRole.USER,
        is_active=True,
    )


def test_openai_answer_service_builds_messages_with_history() -> None:
    """Prompt messages should include system, previous turns, then current grounded question."""
    chat_history = [
        ChatMessage(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            role=ChatMessageRole.USER,
            content="Earlier question",
        ),
        ChatMessage(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            role=ChatMessageRole.ASSISTANT,
            content="Earlier answer",
        ),
    ]

    messages = OpenAIChatAnswerService._build_messages(
        question="Current question",
        context="[Source 1] Policy\nPolicy text",
        chat_history=chat_history,
        system_prompt="You are a test bot.",
    )

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1]["content"] == (
        "Context:\n[Source 1] Policy\nPolicy text\n\nQuestion:\nCurrent question"
    )


@pytest.mark.anyio
async def test_chat_service_creates_session_and_records_answer() -> None:
    """Ask should create session, store messages, citations, and token usage."""
    repository = FakeChatRepository()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=5),
    )

    answer = await service.ask(
        user=make_user(),
        question="  What is   HR policy? ",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer.answer == "Answer for What is HR policy? with 1 source"
    assert answer.source_citations[0]["document_title"] == "HR Policy 1"
    assert [message.role for message in repository.messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]
    assert repository.token_usage_records[0]["input_tokens"] == 11
    assert repository.token_usage_records[0]["output_tokens"] == 7
    assert repository.token_usage_records[0]["embedding_tokens"] == 4
    assert answer.total_tokens == 22
    assert answer.semantic_cache_hit is False
    assert answer.semantic_cache_similarity is None
    assert answer_service.chat_history == []


@pytest.mark.anyio
async def test_chat_service_returns_semantic_cache_hit_without_retrieval_or_llm() -> None:
    """Semantic cache hit should skip retrieval and OpenAI generation."""
    repository = FakeChatRepository()
    retrieval_service = FakeRetrievalService()
    answer_service = FakeAnswerService()
    cache_service = FakeSemanticCacheService(
        SemanticCacheHit(
            answer="Cached answer",
            source_citations=[{"source_number": 1, "document_title": "Cached"}],
            input_tokens=99,
            output_tokens=9,
            similarity=0.98,
        )
    )
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=retrieval_service,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    answer = await service.ask(
        user=make_user(),
        question="What is policy?",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer.answer == "Cached answer"
    assert answer.input_tokens == 0
    assert answer.output_tokens == 0
    assert answer.semantic_cache_hit is True
    assert answer.semantic_cache_similarity == 0.98
    assert answer_service.was_called is False
    assert retrieval_service.search_call_count == 0
    assert cache_service.get_call_count == 1
    assert [message.role for message in repository.messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]
    assert repository.token_usage_records[0]["request_metadata"]["semantic_cache_hit"] is True


@pytest.mark.anyio
async def test_chat_service_stores_successful_answer_in_semantic_cache() -> None:
    """Successful grounded answers should be cached for similar future questions."""
    repository = FakeChatRepository()
    cache_service = FakeSemanticCacheService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    await service.ask(
        user=make_user(), question="What is policy?", bot_id=BOT_ID, session_id=None, top_k=None
    )

    assert cache_service.get_call_count == 1
    assert cache_service.set_call_count == 1
    assert cache_service.set_payload is not None
    assert cache_service.set_payload["query"] == "What is policy?"
    assert cache_service.set_payload["answer"] == "Answer for What is policy? with 1 source"


@pytest.mark.anyio
async def test_chat_service_does_not_cache_low_confidence_answer() -> None:
    """Safe low-confidence answers should not be written to semantic cache."""
    cache_service = FakeSemanticCacheService()
    service = ChatService(
        chat_repository=FakeChatRepository(),  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        # Both signals below threshold → genuinely low confidence.
        retrieval_service=FakeRetrievalService(  # type: ignore[arg-type]
            vector_scores=[0.01], keyword_scores=[0]
        ),
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(rag_min_vector_score=0.25, rag_min_keyword_score=0.1),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    await service.ask(
        user=make_user(), question="Unknown?", bot_id=BOT_ID, session_id=None, top_k=None
    )

    assert cache_service.get_call_count == 1
    assert cache_service.set_call_count == 0


@pytest.mark.anyio
async def test_chat_service_passes_existing_session_history_to_answer_service() -> None:
    """Continuing a session should include prior messages in the model prompt."""
    repository = FakeChatRepository()
    user = make_user()
    existing_session = ChatSession(
        id=uuid.uuid4(), user_id=user.id, bot_id=BOT_ID, title="Existing"
    )
    repository.sessions[existing_session.id] = existing_session
    repository.messages = [
        ChatMessage(
            id=uuid.uuid4(),
            session_id=existing_session.id,
            role=ChatMessageRole.USER,
            content="Earlier question",
        ),
        ChatMessage(
            id=uuid.uuid4(),
            session_id=existing_session.id,
            role=ChatMessageRole.ASSISTANT,
            content="Earlier answer",
        ),
    ]
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(chat_history_messages_limit=10),
    )

    await service.ask(
        user=user,
        question="Follow up?",
        session_id=existing_session.id,
        top_k=None,
    )

    assert answer_service.chat_history is not None
    assert [message.content for message in answer_service.chat_history] == [
        "Earlier question",
        "Earlier answer",
    ]


@pytest.mark.anyio
async def test_chat_service_uses_only_latest_configured_history_messages() -> None:
    """Only latest K previous messages should be passed to the prompt."""
    repository = FakeChatRepository()
    user = make_user()
    existing_session = ChatSession(
        id=uuid.uuid4(), user_id=user.id, bot_id=BOT_ID, title="Existing"
    )
    repository.sessions[existing_session.id] = existing_session
    repository.messages = [
        ChatMessage(
            id=uuid.uuid4(),
            session_id=existing_session.id,
            role=ChatMessageRole.USER,
            content=f"Message {index}",
        )
        for index in range(12)
    ]
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(chat_history_messages_limit=10),
    )

    await service.ask(
        user=user,
        question="Follow up?",
        session_id=existing_session.id,
        top_k=None,
    )

    assert answer_service.chat_history is not None
    assert [message.content for message in answer_service.chat_history] == [
        f"Message {index}" for index in range(2, 12)
    ]


@pytest.mark.anyio
async def test_chat_service_skips_llm_when_retrieval_confidence_is_low() -> None:
    """Low retrieval scores should produce a safe answer without using chat history."""
    repository = FakeChatRepository()
    user = make_user()
    existing_session = ChatSession(
        id=uuid.uuid4(), user_id=user.id, bot_id=BOT_ID, title="Existing"
    )
    repository.sessions[existing_session.id] = existing_session
    repository.messages = [
        ChatMessage(
            id=uuid.uuid4(),
            session_id=existing_session.id,
            role=ChatMessageRole.USER,
            content="Previous user message",
        )
    ]
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(  # type: ignore[arg-type]
            hybrid_scores=[0],
            vector_scores=[0.08631352608679232],
            keyword_scores=[0],
        ),
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(
            rag_min_vector_score=0.25,
            chat_history_messages_limit=10,
        ),
    )

    answer = await service.ask(
        user=user,
        question="Unrelated question?",
        session_id=existing_session.id,
        top_k=None,
    )

    assert answer.answer == (
        "I do not have enough information in the uploaded documents to answer this question."
    )
    assert answer.source_citations == []
    assert answer.input_tokens == 0
    assert answer.output_tokens == 0
    assert not answer_service.was_called
    assert answer_service.chat_history is None
    assert repository.recent_messages_call_count == 0
    assert repository.token_usage_records[0]["request_metadata"]["low_confidence"] is True
    assert (
        repository.token_usage_records[0]["request_metadata"]["retrieved_chunks_after_threshold"]
        == 0
    )
    assert repository.token_usage_records[0]["request_metadata"]["best_vector_score"] < 0.25


@pytest.mark.anyio
async def test_chat_service_skips_llm_when_hybrid_confidence_is_low() -> None:
    """A weak combined score should block chunks even when vector passes."""
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=FakeChatRepository(),  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(  # type: ignore[arg-type]
            hybrid_scores=[0.24],
            vector_scores=[0.35],
            keyword_scores=[0],
        ),
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_min_vector_score=0.25, rag_min_hybrid_score=0.3),
    )

    answer = await service.ask(
        user=make_user(),
        question="What is the lunch menu next Friday?",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer.answer == LOW_CONFIDENCE_ANSWER
    assert answer.source_citations == []
    assert answer_service.was_called is False


@pytest.mark.anyio
async def test_chat_service_filters_low_score_chunks_before_calling_llm() -> None:
    """Only chunks meeting signal and hybrid thresholds should reach the LLM prompt."""
    repository = FakeChatRepository()
    user = make_user()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(  # type: ignore[arg-type]
            hybrid_scores=[0.1, 0.4],
            vector_scores=[0.1, 0.31],
            keyword_scores=[0, 0],
        ),
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_min_vector_score=0.25),
    )

    answer = await service.ask(
        user=user,
        question="Relevant enough?",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer_service.was_called
    assert answer_service.retrieved_chunks is not None
    assert [chunk.vector_score for chunk in answer_service.retrieved_chunks] == [0.31]
    assert answer.source_citations[0]["vector_score"] == 0.31
    assert repository.token_usage_records[0]["request_metadata"]["low_confidence"] is False
    assert (
        repository.token_usage_records[0]["request_metadata"]["retrieved_chunks_after_threshold"]
        == 1
    )


@pytest.mark.anyio
async def test_chat_service_rejects_session_owned_by_another_user() -> None:
    """Users can only continue their own chat sessions."""
    repository = FakeChatRepository()
    existing_session = ChatSession(id=uuid.uuid4(), user_id=uuid.uuid4(), title="Other")
    repository.sessions[existing_session.id] = existing_session
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(),
    )

    with pytest.raises(NotFoundError, match="Chat session not found"):
        await service.ask(
            user=make_user(),
            question="Can I access this?",
            session_id=existing_session.id,
            top_k=None,
        )


def test_chat_ask_route_is_registered() -> None:
    """Ask route should be available under API v1."""
    app = create_app()
    route_paths = set(app.openapi()["paths"].keys())

    assert "/api/v1/chat/ask" in route_paths
    assert "/api/v1/chat/ask/stream" in route_paths
    assert "/api/v1/chat/sessions" in route_paths
    assert "/api/v1/chat/sessions/{session_id}" in route_paths
    assert "/api/v1/chat/usage/me" in route_paths


def test_chat_session_and_usage_routes_support_expected_methods() -> None:
    """Rename/delete a session and read own usage should be registered."""
    app = create_app()
    paths = app.openapi()["paths"]

    session_methods = set(paths["/api/v1/chat/sessions/{session_id}"].keys())
    assert {"get", "patch", "delete"}.issubset(session_methods)
    assert "get" in paths["/api/v1/chat/usage/me"]
    assert "get" in paths["/api/v1/admin/metrics/token-usage/daily"]


@pytest.mark.anyio
async def test_chat_service_streams_answer_tokens_and_records_usage() -> None:
    """Streaming should emit meta, token deltas, a done event, and persist usage."""
    repository = FakeChatRepository()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3),
    )

    events = [
        event
        async for event in service.ask_stream(
            user=make_user(),
            question="  What is   HR policy? ",
            bot_id=BOT_ID,
            session_id=None,
            top_k=None,
        )
    ]

    assert events[0]["type"] == "meta"
    token_events = [event for event in events if event["type"] == "token"]
    assert token_events, "expected streamed token events"
    streamed_text = "".join(str(event["text"]) for event in token_events).strip()
    done = events[-1]
    assert done["type"] == "done"
    assert done["answer"] == streamed_text
    assert done["answer"] == "Answer for What is HR policy? with 1 source"
    assert done["total_tokens"] == 11 + 7 + 4
    assert done["semantic_cache_hit"] is False
    assert getattr(repository, "commit_call_count", 0) == 1
    assert [message.role for message in repository.messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]


@pytest.mark.anyio
async def test_chat_service_answers_greeting_without_retrieval() -> None:
    """A greeting should be answered by the LLM, skipping retrieval and citations."""
    repository = FakeChatRepository()
    retrieval = FakeRetrievalService()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=retrieval,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3),
    )

    answer = await service.ask(
        user=make_user(),
        question="Hello there!",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer_service.greeting_called is True
    assert answer_service.was_called is False  # no RAG generation
    assert retrieval.search_call_count == 0  # no retrieval
    assert answer.source_citations == []
    assert answer.semantic_cache_hit is False
    assert answer.total_tokens == 3 + 9  # no embedding tokens for greetings
    assert repository.token_usage_records[0]["embedding_tokens"] == 0
    assert [message.role for message in repository.messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]


@pytest.mark.anyio
async def test_chat_service_streams_greeting_reply() -> None:
    """Streaming a greeting should emit tokens then a done event, no retrieval."""
    repository = FakeChatRepository()
    retrieval = FakeRetrievalService()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=retrieval,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3),
    )

    events = [
        event
        async for event in service.ask_stream(
            user=make_user(),
            question="good morning",
            bot_id=BOT_ID,
            session_id=None,
            top_k=None,
        )
    ]

    assert answer_service.greeting_called is True
    assert retrieval.search_call_count == 0
    done = events[-1]
    assert done["type"] == "done"
    assert done["source_citations"] == []
    assert done["total_tokens"] == 3 + 9
    assert getattr(repository, "commit_call_count", 0) == 1


@pytest.mark.anyio
async def test_chat_service_uses_hybrid_search_for_questions() -> None:
    """Real questions must go through hybrid search, passing the query text."""
    repository = FakeChatRepository()
    retrieval = FakeRetrievalService()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=retrieval,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3),
    )

    answer = await service.ask(
        user=make_user(),
        question="What is scaled dot-product attention?",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer_service.greeting_called is False
    assert retrieval.search_call_count == 1  # hybrid search delegates here
    assert answer.source_citations  # citations produced from retrieved chunks


@pytest.mark.anyio
async def test_chat_service_keeps_strong_keyword_only_chunks() -> None:
    """A low vector score but strong keyword match still counts as enough context."""
    repository = FakeChatRepository()
    # vector below threshold, keyword above the keyword threshold.
    retrieval = FakeRetrievalService(
        hybrid_scores=[0.5], vector_scores=[0.05], keyword_scores=[0.4]
    )
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=retrieval,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3, rag_min_vector_score=0.25, rag_min_keyword_score=0.1),
    )

    await service.ask(
        user=make_user(),
        question="What is the attention head count?",
        bot_id=BOT_ID,
        session_id=None,
        top_k=None,
    )

    assert answer_service.was_called is True  # keyword match kept the chunk


@pytest.mark.anyio
async def test_chat_service_streams_cache_hit_without_llm() -> None:
    """A semantic cache hit should stream the cached answer without the LLM."""
    repository = FakeChatRepository()
    answer_service = FakeAnswerService()
    cache = FakeSemanticCacheService(
        hit=SemanticCacheHit(
            answer="Cached answer text",
            source_citations=[{"document_title": "Doc"}],
            similarity=0.99,
            input_tokens=0,
            output_tokens=0,
        )
    )
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        bot_repository=FakeBotRepository(),  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=3),
        semantic_cache_service=cache,  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in service.ask_stream(
            user=make_user(),
            question="Cached question",
            bot_id=BOT_ID,
            session_id=None,
            top_k=None,
        )
    ]

    done = events[-1]
    assert answer_service.was_called is False
    assert done["semantic_cache_hit"] is True
    assert done["answer"] == "Cached answer text"
    streamed_text = "".join(
        str(event["text"]) for event in events if event["type"] == "token"
    )
    assert streamed_text == "Cached answer text"


@pytest.mark.anyio
async def test_fake_chat_repository_lists_only_owned_sessions() -> None:
    """Session list behavior must be scoped by current user."""
    repository = FakeChatRepository()
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    owned_session = ChatSession(id=uuid.uuid4(), user_id=owner_id, title="Mine")
    other_session = ChatSession(id=uuid.uuid4(), user_id=other_user_id, title="Other")
    repository.sessions[owned_session.id] = owned_session
    repository.sessions[other_session.id] = other_session

    sessions = await repository.list_user_sessions(user_id=owner_id, limit=10, offset=0)

    assert sessions == [owned_session]


@pytest.mark.anyio
async def test_fake_chat_repository_lists_session_messages() -> None:
    """Session detail behavior should return messages for one session."""
    repository = FakeChatRepository()
    session_id = uuid.uuid4()
    other_session_id = uuid.uuid4()
    repository.messages = [
        ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role=ChatMessageRole.USER,
            content="Question",
        ),
        ChatMessage(
            id=uuid.uuid4(),
            session_id=other_session_id,
            role=ChatMessageRole.USER,
            content="Other",
        ),
    ]

    messages = await repository.list_session_messages(session_id=session_id, limit=10, offset=0)

    assert len(messages) == 1
    assert messages[0].content == "Question"
