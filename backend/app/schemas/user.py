"""User Pydantic schemas.

Design Decisions:
    - Separate schemas for creating (requires plain text password) and returning
      (never includes password).
    - Email validation using Pydantic's EmailStr (requires email-validator).
    - Role is validated against the UserRole enum.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema with shared attributes."""

    email: EmailStr = Field(..., description="User's email address")
    full_name: str | None = Field(default=None, max_length=255, description="User's full name")
    role: UserRole = Field(default=UserRole.USER, description="User role")
    is_active: bool = Field(default=True, description="Account status")


class UserCreate(BaseModel):
    """Schema for creating a new user (Registration)."""

    email: EmailStr = Field(..., description="User's email address")
    full_name: str | None = Field(default=None, max_length=255, description="User's full name")
    password: str = Field(..., min_length=8, description="Plain text password (min 8 chars)")


class UserResponse(UserBase):
    """Schema for returning user data (never includes password)."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Schema for updating user data (all fields optional)."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8)
