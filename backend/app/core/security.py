"""Security utilities for password hashing and JWT token management.

Design Decisions:
    - Passlib with bcrypt for secure password hashing.
    - PyJWT for token generation and validation.
    - Access tokens are short-lived (default 30m) for security.
    - Refresh tokens are long-lived (default 7d) for UX.
    - Claims include 'type' to distinguish between access and refresh tokens.
"""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.models.user import User

# Configure passlib to use bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash from a plain text password."""
    return pwd_context.hash(password)


def _create_token(user: User, token_type: str, expires_delta: timedelta) -> str:
    """Internal function to create a JWT."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + expires_delta

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "type": token_type,
    }

    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user: User) -> str:
    """Create a short-lived JWT access token for a user."""
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return _create_token(user, "access", expires_delta)


def create_refresh_token(user: User) -> str:
    """Create a long-lived JWT refresh token for a user."""
    settings = get_settings()
    expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    return _create_token(user, "refresh", expires_delta)
