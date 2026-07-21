"""User repository for database operations.

Design Decisions:
    - Encapsulates SQLAlchemy queries away from the router/service layer.
    - Uses async sessions injected via dependencies.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Repository for User operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get a user by their UUID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Create a new user."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
