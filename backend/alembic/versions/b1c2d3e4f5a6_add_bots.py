"""Add bots table and bot_id scoping to documents, sessions, and token usage

Revision ID: b1c2d3e4f5a6
Revises: a8f2d7c1e9b4
Create Date: 2026-07-21 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a8f2d7c1e9b4"
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
    op.create_table(
        "bots",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bots_created_by_id"), "bots", ["created_by_id"])

    op.add_column("rag_documents", sa.Column("bot_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_rag_documents_bot_id",
        "rag_documents",
        "bots",
        ["bot_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_rag_documents_bot_id"), "rag_documents", ["bot_id"])

    op.add_column("chat_sessions", sa.Column("bot_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_chat_sessions_bot_id",
        "chat_sessions",
        "bots",
        ["bot_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_chat_sessions_bot_id"), "chat_sessions", ["bot_id"])

    op.add_column("token_usage", sa.Column("bot_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_token_usage_bot_id",
        "token_usage",
        "bots",
        ["bot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_token_usage_bot_created_at", "token_usage", ["bot_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_bot_created_at", table_name="token_usage")
    op.drop_constraint("fk_token_usage_bot_id", "token_usage", type_="foreignkey")
    op.drop_column("token_usage", "bot_id")

    op.drop_index(op.f("ix_chat_sessions_bot_id"), table_name="chat_sessions")
    op.drop_constraint("fk_chat_sessions_bot_id", "chat_sessions", type_="foreignkey")
    op.drop_column("chat_sessions", "bot_id")

    op.drop_index(op.f("ix_rag_documents_bot_id"), table_name="rag_documents")
    op.drop_constraint("fk_rag_documents_bot_id", "rag_documents", type_="foreignkey")
    op.drop_column("rag_documents", "bot_id")

    op.drop_index(op.f("ix_bots_created_by_id"), table_name="bots")
    op.drop_table("bots")
