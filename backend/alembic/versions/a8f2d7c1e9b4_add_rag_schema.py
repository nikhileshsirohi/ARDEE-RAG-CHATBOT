"""Add RAG document, chat, cache, and metrics schema

Revision ID: a8f2d7c1e9b4
Revises: d73d14f93a0e
Create Date: 2026-07-21 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8f2d7c1e9b4"
down_revision: str | None = "d73d14f93a0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=255), nullable=True))

    op.create_table(
        "rag_documents",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=100),
            server_default="application/pdf",
            nullable=False,
        ),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "READY",
                "FAILED",
                "ARCHIVED",
                name="ragdocumentstatus",
                native_enum=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index(op.f("ix_rag_documents_checksum_sha256"), "rag_documents", ["checksum_sha256"])
    op.create_index(op.f("ix_rag_documents_uploaded_by_id"), "rag_documents", ["uploaded_by_id"])

    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )
    op.create_index(
        "ix_document_chunks_document_page", "document_chunks", ["document_id", "page_number"]
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "chat_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_sessions_user_id"), "chat_sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "ASSISTANT", "SYSTEM", name="chatmessagerole", native_enum=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"])

    op.create_table(
        "token_usage",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("embedding_model_name", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_usage_user_created_at", "token_usage", ["user_id", "created_at"])
    op.create_index(
        "ix_token_usage_session_created_at", "token_usage", ["session_id", "created_at"]
    )

    op.create_table(
        "semantic_cache_entries",
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("query_embedding", Vector(1536), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("source_citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_hash"),
    )
    op.create_index(
        "ix_semantic_cache_embedding_hnsw",
        "semantic_cache_entries",
        ["query_embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"query_embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_semantic_cache_expires_at", "semantic_cache_entries", ["expires_at"])

    op.execute(
        """
        CREATE FUNCTION update_document_chunk_search_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', coalesce(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_chunks_search_vector
        BEFORE INSERT OR UPDATE OF content ON document_chunks
        FOR EACH ROW EXECUTE FUNCTION update_document_chunk_search_vector();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_document_chunks_search_vector ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS update_document_chunk_search_vector")
    op.drop_index("ix_semantic_cache_expires_at", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_embedding_hnsw", table_name="semantic_cache_entries")
    op.drop_table("semantic_cache_entries")
    op.drop_index("ix_token_usage_session_created_at", table_name="token_usage")
    op.drop_index("ix_token_usage_user_created_at", table_name="token_usage")
    op.drop_table("token_usage")
    op.drop_index(op.f("ix_chat_messages_session_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_chat_sessions_user_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_page", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_rag_documents_uploaded_by_id"), table_name="rag_documents")
    op.drop_index(op.f("ix_rag_documents_checksum_sha256"), table_name="rag_documents")
    op.drop_table("rag_documents")
    op.drop_column("users", "full_name")
