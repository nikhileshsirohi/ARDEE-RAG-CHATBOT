"""Tests for RAG chatbot orchestration."""

import uuid

import pytest

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.main import create_app
from app.models.rag import ChatMessage, ChatMessageRole, ChatSession
from app.models.user import User, UserRole
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.chat import ChatService, GeneratedAnswer, OpenAIChatAnswerService
from app.services.semantic_cache import SemanticCacheHit


class FakeChatRepository:
    """In-memory fake for chat persistence tests."""

    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, ChatSession] = {}
        self.messages: list[ChatMessage] = []
        self.token_usage_records: list[dict[str, object]] = []
        self.recent_messages_call_count = 0

    async def create_session(self, *, user_id: uuid.UUID, title: str) -> ChatSession:
        chat_session = ChatSession(id=uuid.uuid4(), user_id=user_id, title=title)
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
    ) -> list[ChatSession]:
        sessions = [
            session
            for session in self.sessions.values()
            if session.user_id == user_id and not session.is_archived
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


class FakeRetrievalService:
    """Return deterministic RAG chunks."""

    def __init__(
        self,
        *,
        hybrid_scores: list[float] | None = None,
        vector_scores: list[float] | None = None,
        keyword_scores: list[float] | None = None,
    ) -> None:
        self.hybrid_scores = hybrid_scores or [0.04]
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
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = query
        _ = top_k
        return await self.search_by_embedding(query_embedding=self.query_embedding, top_k=top_k)

    async def search_by_embedding(
        self,
        *,
        query_embedding: list[float],
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = query_embedding
        _ = top_k
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

    async def answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
        chat_history: list[ChatMessage],
    ) -> GeneratedAnswer:
        self.was_called = True
        self.chat_history = chat_history
        self.retrieved_chunks = retrieved_chunks
        return GeneratedAnswer(
            answer=f"Answer for {question} with {len(retrieved_chunks)} source",
            input_tokens=11,
            output_tokens=7,
        )


class FakeSemanticCacheService:
    """Fake semantic cache service for chat tests."""

    def __init__(self, hit: SemanticCacheHit | None = None) -> None:
        self.hit = hit
        self.get_call_count = 0
        self.set_call_count = 0
        self.set_payload: dict[str, object] | None = None

    async def get(self, *, query_embedding: list[float]) -> SemanticCacheHit | None:
        _ = query_embedding
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
    ) -> None:
        self.set_call_count += 1
        self.set_payload = {
            "query": query,
            "query_embedding": query_embedding,
            "answer": answer,
            "source_citations": source_citations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
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
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_top_k=5),
    )

    answer = await service.ask(
        user=make_user(),
        question="  What is   HR policy? ",
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
        retrieval_service=retrieval_service,  # type: ignore[arg-type]
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    answer = await service.ask(
        user=make_user(),
        question="What is policy?",
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
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    await service.ask(user=make_user(), question="What is policy?", session_id=None, top_k=None)

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
        retrieval_service=FakeRetrievalService(vector_scores=[0.01]),  # type: ignore[arg-type]
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(rag_min_vector_score=0.25),
        semantic_cache_service=cache_service,  # type: ignore[arg-type]
    )

    await service.ask(user=make_user(), question="Unknown?", session_id=None, top_k=None)

    assert cache_service.get_call_count == 1
    assert cache_service.set_call_count == 0


@pytest.mark.anyio
async def test_chat_service_passes_existing_session_history_to_answer_service() -> None:
    """Continuing a session should include prior messages in the model prompt."""
    repository = FakeChatRepository()
    user = make_user()
    existing_session = ChatSession(id=uuid.uuid4(), user_id=user.id, title="Existing")
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
    existing_session = ChatSession(id=uuid.uuid4(), user_id=user.id, title="Existing")
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
    existing_session = ChatSession(id=uuid.uuid4(), user_id=user.id, title="Existing")
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
async def test_chat_service_filters_low_score_chunks_before_calling_llm() -> None:
    """Only chunks meeting vector threshold should reach the LLM prompt."""
    repository = FakeChatRepository()
    user = make_user()
    answer_service = FakeAnswerService()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(  # type: ignore[arg-type]
            hybrid_scores=[0, 0],
            vector_scores=[0.1, 0.31],
            keyword_scores=[0, 0],
        ),
        answer_service=answer_service,  # type: ignore[arg-type]
        settings=Settings(rag_min_vector_score=0.25),
    )

    answer = await service.ask(
        user=user,
        question="Relevant enough?",
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
    assert "/api/v1/chat/sessions" in route_paths
    assert "/api/v1/chat/sessions/{session_id}" in route_paths


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
