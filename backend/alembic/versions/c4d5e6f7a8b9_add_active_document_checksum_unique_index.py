"""Add unique active bot document checksum index

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-07-22 07:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked_documents AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY bot_id, checksum_sha256
                    ORDER BY created_at DESC, id DESC
                ) AS duplicate_rank
            FROM rag_documents
            WHERE deleted_at IS NULL
        ),
        archived_documents AS (
            UPDATE rag_documents
            SET
                deleted_at = now(),
                status = 'ARCHIVED',
                updated_at = now()
            WHERE id IN (
                SELECT id
                FROM ranked_documents
                WHERE duplicate_rank > 1
            )
            RETURNING id
        )
        DELETE FROM document_chunks
        WHERE document_id IN (SELECT id FROM archived_documents)
        """
    )
    op.create_index(
        "uq_rag_documents_active_bot_checksum",
        "rag_documents",
        ["bot_id", "checksum_sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_rag_documents_active_bot_checksum", table_name="rag_documents")
