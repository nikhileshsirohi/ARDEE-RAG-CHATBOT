"""Pydantic schemas for RAG documents, chat history, cache, and metrics."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.rag import ChatMessageRole, RagDocumentStatus
from app.models.user import UserRole


class BotCreate(BaseModel):
    """Admin request body for creating a bot."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    system_prompt: str = Field(..., min_length=1, max_length=8000)


class BotUpdate(BaseModel):
    """Admin request body for updating a bot (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    is_active: bool | None = None


class BotResponse(BaseModel):
    """Bot summary response for listing and detail views."""

    id: uuid.UUID
    name: str
    description: str | None
    system_prompt: str
    is_active: bool
    created_by_id: uuid.UUID | None
    document_count: int = 0
    ready_document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotDetailResponse(BotResponse):
    """Bot detail response including its knowledge-base documents."""

    documents: list["RagDocumentResponse"] = Field(default_factory=list)


class RagDocumentCreate(BaseModel):
    """Metadata required when an admin uploads a PDF."""

    title: str = Field(..., min_length=1, max_length=255)
    original_filename: str = Field(..., min_length=1, max_length=255)
    storage_path: str = Field(..., min_length=1, max_length=1024)
    file_size_bytes: int = Field(..., ge=1)
    checksum_sha256: str = Field(..., min_length=64, max_length=64)


class RagDocumentUpdate(BaseModel):
    """Admin request body for updating document metadata."""

    title: str = Field(..., min_length=1, max_length=255)


class RagDocumentResponse(BaseModel):
    """Admin-facing document response."""

    id: uuid.UUID
    bot_id: uuid.UUID | None
    title: str
    original_filename: str
    status: RagDocumentStatus
    version: int
    page_count: int | None
    chunk_count: int
    uploaded_by_id: uuid.UUID | None
    processed_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionCreate(BaseModel):
    """Request body for creating a user-owned chat session."""

    title: str = Field(default="New chat", min_length=1, max_length=255)


class ChatSessionUpdate(BaseModel):
    """Request body for renaming a user-owned chat session."""

    title: str = Field(..., min_length=1, max_length=255)


class ChatAskRequest(BaseModel):
    """Authenticated request to ask the RAG chatbot.

    ``bot_id`` selects which bot answers. It is required when starting a new
    session (``session_id`` omitted); when continuing a session the bot is
    inferred from the session.
    """

    question: str = Field(..., min_length=1, max_length=4000)
    bot_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatAskResponse(BaseModel):
    """RAG chatbot answer response."""

    session_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    source_citations: list[dict[str, object]]
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    latency_ms: int = Field(..., ge=0)
    semantic_cache_hit: bool
    semantic_cache_similarity: float | None = Field(default=None, ge=0, le=1)


class ChatSessionResponse(BaseModel):
    """User-facing chat session response."""

    id: uuid.UUID
    user_id: uuid.UUID
    bot_id: uuid.UUID | None
    title: str
    last_message_at: datetime | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    total_tokens: int = Field(default=0, ge=0)

    model_config = ConfigDict(from_attributes=True)


class RagSearchRequest(BaseModel):
    """Authenticated RAG retrieval request."""

    query: str = Field(..., min_length=1, max_length=4000)
    bot_id: uuid.UUID
    top_k: int | None = Field(default=None, ge=1, le=20)


class RagSearchResult(BaseModel):
    """Retrieved chunk with hybrid ranking metadata."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    original_filename: str
    page_number: int | None
    content: str
    vector_score: float
    keyword_score: float
    hybrid_score: float


class RagSearchResponse(BaseModel):
    """Authenticated RAG retrieval response."""

    query: str
    results: list[RagSearchResult]


class ChatMessageResponse(BaseModel):
    """User-facing chat message response."""

    id: uuid.UUID
    session_id: uuid.UUID
    role: ChatMessageRole
    content: str
    source_citations: list[dict[str, object]]
    latency_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionDetailResponse(BaseModel):
    """User-facing chat session with message history."""

    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class UserTokenUsageMetric(BaseModel):
    """Admin dashboard aggregate by user."""

    user_id: uuid.UUID
    full_name: str | None
    email: str
    role: UserRole
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    embedding_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    request_count: int = Field(..., ge=0)


class DailyTokenUsageMetric(BaseModel):
    """Per-day token usage bucket for the admin usage chart."""

    day: date
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    embedding_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    request_count: int = Field(..., ge=0)


class SessionTokenUsageMetric(BaseModel):
    """Per-session token usage for a single user."""

    session_id: uuid.UUID
    title: str
    bot_id: uuid.UUID | None = None
    bot_name: str | None = None
    last_message_at: datetime | None
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    embedding_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    request_count: int = Field(..., ge=0)


class BotTokenUsageMetric(BaseModel):
    """Admin dashboard aggregate by bot."""

    bot_id: uuid.UUID | None
    name: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    embedding_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    request_count: int = Field(..., ge=0)


class MyTokenUsageSummary(BaseModel):
    """A user's own aggregate token usage plus per-session breakdown."""

    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    embedding_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    request_count: int = Field(..., ge=0)
    session_count: int = Field(..., ge=0)
    sessions: list[SessionTokenUsageMetric]


BotDetailResponse.model_rebuild()
