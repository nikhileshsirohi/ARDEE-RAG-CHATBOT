"""User ORM model.

Design Decisions:
    - Inherits from Base to get UUID primary key and timestamps.
    - email is unique and indexed for fast lookups during login.
    - password_hash stores the bcrypt hashed password (never plain text).
    - role enum (USER, ADMIN) enables basic RBAC.
    - is_active allows disabling accounts without deleting their data.
"""

from enum import StrEnum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(StrEnum):
    """User roles for Role-Based Access Control (RBAC)."""

    USER = "USER"
    ADMIN = "ADMIN"


class User(Base):
    """User database model.

    Attributes:
        email: Unique email address used for login.
        password_hash: Bcrypt hashed password.
        role: User role (default: USER).
        is_active: Whether the account is active and can log in.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
