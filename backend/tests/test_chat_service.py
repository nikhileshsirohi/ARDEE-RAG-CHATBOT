"""Tests for RAG chatbot orchestration."""

import uuid

import pytest

from app.config import Settings
from app.core.exceptions import NotFoundError
from app.main import create_app
from app.models.rag import ChatMessage, ChatMessageRole, ChatSession
from app.models.user import User, UserRole
from app.repositories.rag_retrieval import HybridSearchResult
from app.services.chat import ChatService, GeneratedAnswer


class FakeChatRepository:
    """In-memory fake for chat persistence tests."""

    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, ChatSession] = {}
        self.messages: list[ChatMessage] = []
        self.token_usage_records: list[dict[str, object]] = []

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

    async def search(
        self,
        *,
        query: str,
        top_k: int | None = None,
    ) -> list[HybridSearchResult]:
        _ = top_k
        return [
            HybridSearchResult(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="HR Policy",
                original_filename="hr-policy.pdf",
                page_number=3,
                content=f"Context for {query}",
                token_count=4,
                vector_score=0.91,
                keyword_score=0.5,
                hybrid_score=0.04,
            )
        ]


class FakeAnswerService:
    """Return a deterministic answer."""

    async def answer_question(
        self,
        *,
        question: str,
        retrieved_chunks: list[HybridSearchResult],
    ) -> GeneratedAnswer:
        return GeneratedAnswer(
            answer=f"Answer for {question} with {len(retrieved_chunks)} source",
            input_tokens=11,
            output_tokens=7,
        )


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


@pytest.mark.anyio
async def test_chat_service_creates_session_and_records_answer() -> None:
    """Ask should create session, store messages, citations, and token usage."""
    repository = FakeChatRepository()
    service = ChatService(
        chat_repository=repository,  # type: ignore[arg-type]
        retrieval_service=FakeRetrievalService(),  # type: ignore[arg-type]
        answer_service=FakeAnswerService(),  # type: ignore[arg-type]
        settings=Settings(rag_top_k=5),
    )

    answer = await service.ask(
        user=make_user(),
        question="  What is   HR policy? ",
        session_id=None,
        top_k=None,
    )

    assert answer.answer == "Answer for What is HR policy? with 1 source"
    assert answer.source_citations[0]["document_title"] == "HR Policy"
    assert [message.role for message in repository.messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]
    assert repository.token_usage_records[0]["input_tokens"] == 11
    assert repository.token_usage_records[0]["output_tokens"] == 7
    assert repository.token_usage_records[0]["embedding_tokens"] == 4
    assert answer.total_tokens == 22


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
