"""Authentication API routes.

Endpoints:
    - POST /register: Create a new user account.
    - POST /login: Authenticate and receive access/refresh tokens.
    - POST /refresh: Exchange a valid refresh token for a new access token.
"""

from typing import Annotated

import jwt
from fastapi import APIRouter, Body, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError

from app.api.dependencies.auth import SessionDep
from app.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import Token, TokenPayload
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(
    user_in: UserCreate,
    session: SessionDep,
) -> UserResponse:
    """Register a new user with email and password.

    Fails if the email is already registered.
    """
    user_repo = UserRepository(session)

    # Check if user exists
    existing_user = await user_repo.get_by_email(user_in.email)
    if existing_user:
        raise ConflictError("User with this email already exists")

    # Hash password and create user
    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        password_hash=get_password_hash(user_in.password),
    )
    created_user = await user_repo.create(user)

    return UserResponse.model_validate(created_user)


@router.post(
    "/login",
    response_model=Token,
    summary="Login to get access and refresh tokens",
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    """OAuth2 compatible token login.

    Accepts form data (`username` and `password`).
    Returns short-lived access_token and long-lived refresh_token.
    """
    user_repo = UserRepository(session)

    # Fetch user by email (username field in OAuth2 form)
    user = await user_repo.get_by_email(form_data.username)
    if not user:
        raise UnauthorizedError("Incorrect email or password")

    # Verify password
    if not verify_password(form_data.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password")

    # Ensure user is active
    if not user.is_active:
        raise UnauthorizedError("Inactive user")

    # Generate tokens
    settings = get_settings()
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh access token",
)
async def refresh_token(
    refresh_token: Annotated[str, Body(embed=True)],
    session: SessionDep,
) -> Token:
    """Exchange a valid refresh token for a new access token.

    Verifies the refresh token is valid, hasn't expired, and belongs
    to an active user.
    """
    settings = get_settings()

    try:
        payload_dict = jwt.decode(
            refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        token_data = TokenPayload(**payload_dict)
    except (jwt.InvalidTokenError, ValidationError) as e:
        raise UnauthorizedError("Invalid refresh token") from e

    if token_data.type != "refresh":
        raise UnauthorizedError("Invalid token type. Expected refresh token.")

    # Fetch user and verify active status
    user_repo = UserRepository(session)
    import uuid

    user = await user_repo.get_by_id(uuid.UUID(token_data.sub))
    if not user or not user.is_active:
        raise UnauthorizedError("User is inactive or deleted")

    # Generate new tokens
    new_access_token = create_access_token(user)
    new_refresh_token = create_refresh_token(user)

    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )
