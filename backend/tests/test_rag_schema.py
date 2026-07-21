"""Tests for RAG schema metadata and DTO validation."""

import uuid

from app.models import Base
from app.models.rag import EMBEDDING_DIMENSIONS, DocumentChunk, RagDocument, TokenUsage
from app.models.user import UserRole
from app.schemas.rag import RagDocumentCreate, UserTokenUsageMetric
from app.schemas.user import UserCreate


def test_rag_tables_are_registered_with_sqlalchemy_metadata() -> None:
    """Alembic can only discover models imported into Base metadata."""
    expected_tables = {
        "rag_documents",
        "document_chunks",
        "chat_sessions",
        "chat_messages",
        "token_usage",
        "semantic_cache_entries",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_document_chunk_embedding_dimension_matches_openai_default() -> None:
    """Vector schema must match text-embedding-3-small default dimensions."""
    embedding_type = DocumentChunk.__table__.c.embedding.type

    assert EMBEDDING_DIMENSIONS == 1536
    assert embedding_type.dim == EMBEDDING_DIMENSIONS


def test_rag_document_tracks_admin_uploader_and_processing_state() -> None:
    """Document schema should support admin audit and ingestion status."""
    columns = RagDocument.__table__.c

    assert "uploaded_by_id" in columns
    assert "status" in columns
    assert "deleted_at" in columns


def test_token_usage_links_to_user_for_admin_dashboard_metrics() -> None:
    """Token usage must be attributable to users for dashboard aggregation."""
    columns = TokenUsage.__table__.c

    assert "user_id" in columns
    assert "input_tokens" in columns
    assert "output_tokens" in columns
    assert "total_tokens" in columns


def test_user_create_accepts_optional_full_name() -> None:
    """Registration can capture a display name for admin dashboards."""
    user = UserCreate(
        email="admin@example.com",
        full_name="Admin User",
        password="".join(["valid", "-test", "-pass"]),
    )

    assert user.full_name == "Admin User"


def test_rag_document_create_validates_sha256_checksum() -> None:
    """Document uploads should carry immutable file identity metadata."""
    document = RagDocumentCreate(
        title="Employee Handbook",
        original_filename="handbook.pdf",
        storage_path="uploads/handbook.pdf",
        file_size_bytes=1024,
        checksum_sha256="a" * 64,
    )

    assert document.checksum_sha256 == "a" * 64


def test_user_token_usage_metric_contains_user_identity_and_tokens() -> None:
    """Admin metric rows need both identity and usage fields."""
    metric = UserTokenUsageMetric(
        user_id=uuid.uuid4(),
        full_name="Test User",
        email="user@example.com",
        role=UserRole.USER,
        input_tokens=10,
        output_tokens=20,
        embedding_tokens=30,
        total_tokens=60,
        request_count=1,
    )

    assert metric.email == "user@example.com"
    assert metric.total_tokens == 60
