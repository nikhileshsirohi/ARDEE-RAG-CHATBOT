"""Replace global document checksum index with per-bot index

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-22 08:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rag_documents_active_checksum")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_documents_active_bot_checksum
        ON rag_documents (bot_id, checksum_sha256)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rag_documents_active_bot_checksum")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_documents_active_checksum
        ON rag_documents (checksum_sha256)
        WHERE deleted_at IS NULL
        """
    )
