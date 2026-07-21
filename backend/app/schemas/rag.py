"""Pydantic schemas for RAG documents, chat history, cache, and metrics."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.rag import ChatMessageRole, RagDocumentStatus
from app.models.user import UserRole


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


class ChatAskRequest(BaseModel):
    """Authenticated request to ask the RAG chatbot."""

    question: str = Field(..., min_length=1, max_length=4000)
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
    title: str
    last_message_at: datetime | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RagSearchRequest(BaseModel):
    """Authenticated RAG retrieval request."""

    query: str = Field(..., min_length=1, max_length=4000)
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
