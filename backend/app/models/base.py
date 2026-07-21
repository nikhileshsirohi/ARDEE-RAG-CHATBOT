"""Base ORM model with shared columns for all database tables.

Design Decisions:
    - UUID primary keys: Globally unique, no enumeration attacks, merge-safe
      across distributed systems. Uses PostgreSQL's gen_random_uuid() for
      server-side generation (no Python dependency for UUID creation).
    - created_at / updated_at timestamps: Essential for auditing, debugging,
      and cache invalidation. Server-side defaults ensure consistency even
      if the application layer forgets to set them.
    - DeclarativeBase: SQLAlchemy 2.0 style. Type-safe, supports Mapped[] annotations.
    - All models inherit from Base to get these columns automatically.

Why UUID over auto-increment?
    - Auto-increment exposes record counts (security risk).
    - Auto-increment is not safe for multi-database merges or sharding.
    - UUID v4 is random, preventing prediction attacks.
    - Tradeoff: 16 bytes vs 4 bytes, slightly slower B-tree scans.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Abstract base class for all ORM models.

    Provides:
        - id: UUID primary key (server-generated)
        - created_at: Timestamp set on INSERT
        - updated_at: Timestamp set on INSERT and UPDATE
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
