"""RAG ORM models.

These tables support admin-managed PDFs, searchable document chunks, user-owned
chat history, semantic caching, and per-user token metrics.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

EMBEDDING_DIMENSIONS = 1536


class RagDocumentStatus(StrEnum):
    """Processing state for admin-uploaded PDF documents."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class ChatMessageRole(StrEnum):
    """Supported chat message roles."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class RagDocument(Base):
    """PDF document uploaded and managed by admins."""

    __tablename__ = "rag_documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100), default="application/pdf", server_default="application/pdf", nullable=False
    )
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[RagDocumentStatus] = mapped_column(
        Enum(RagDocumentStatus, native_enum=False),
        default=RagDocumentStatus.PENDING,
        server_default=RagDocumentStatus.PENDING.value,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    uploaded_by = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """Searchable text chunk generated from an uploaded PDF."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        Index("ix_document_chunks_document_page", "document_id", "page_number"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    document = relationship("RagDocument", back_populates="chunks")


class ChatSession(Base):
    """User-owned RAG chat session."""

    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="New chat", nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    token_usage_records = relationship("TokenUsage", back_populates="session")


class ChatMessage(Base):
    """Message stored within a user-owned chat session."""

    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(ChatMessageRole, native_enum=False), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session = relationship("ChatSession", back_populates="messages")
    token_usage_records = relationship("TokenUsage", back_populates="message")


class TokenUsage(Base):
    """Per-request token usage for admin metrics and cost monitoring."""

    __tablename__ = "token_usage"
    __table_args__ = (
        Index("ix_token_usage_user_created_at", "user_id", "created_at"),
        Index("ix_token_usage_session_created_at", "session_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    embedding_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)

    user = relationship("User", back_populates="token_usage_records")
    session = relationship("ChatSession", back_populates="token_usage_records")
    message = relationship("ChatMessage", back_populates="token_usage_records")


class SemanticCacheEntry(Base):
    """Persistent semantic cache entry for repeated RAG questions."""

    __tablename__ = "semantic_cache_entries"
    __table_args__ = (
        Index(
            "ix_semantic_cache_embedding_hnsw",
            "query_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"query_embedding": "vector_cosine_ops"},
        ),
        Index("ix_semantic_cache_expires_at", "expires_at"),
    )

    query_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    query_embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
