"""Enable pgvector extension.

Revision ID: 001
Revises: None
Create Date: 2026-07-21

This is the first migration. It enables the pgvector extension in PostgreSQL,
which is required before any vector columns can be created.

The pgvector extension provides:
    - vector data type for storing embeddings
    - Cosine similarity, L2 distance, inner product operators
    - IVFFlat and HNSW indexes for approximate nearest neighbor search
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable the pgvector extension."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable the pgvector extension."""
    op.execute("DROP EXTENSION IF EXISTS vector")
