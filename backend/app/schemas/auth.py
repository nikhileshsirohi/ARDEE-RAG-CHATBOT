"""Authentication schemas.

Design Decisions:
    - Token schema follows OAuth2 specification (access_token, token_type).
    - Includes refresh_token for long-lived sessions.
    - TokenPayload represents the decoded JWT claims.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole


class Token(BaseModel):
    """Schema for returning OAuth2 tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type (always bearer)")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class TokenPayload(BaseModel):
    """Schema representing the decoded JWT claims."""

    sub: str = Field(..., description="Subject (User ID)")
    email: str = Field(..., description="User's email address")
    full_name: str | None = Field(default=None, description="User's display name")
    role: UserRole = Field(..., description="User's role")
    exp: datetime = Field(..., description="Expiration time")
    iat: datetime = Field(..., description="Issued at time")
    type: str = Field(..., description="Token type (access or refresh)")
