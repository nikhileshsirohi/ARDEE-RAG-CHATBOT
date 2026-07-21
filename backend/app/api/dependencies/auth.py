"""Authentication and Authorization dependencies.

Design Decisions:
    - Uses FastAPI's OAuth2PasswordBearer to automatically extract the token
      from the Authorization header and integrate with Swagger UI.
    - Decodes the JWT, extracts the user ID, and fetches the user from the DB.
    - get_current_active_user ensures the account isn't disabled.
    - RequireRole class enables declarative RBAC on endpoints.
"""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.auth import TokenPayload

# OAuth2 scheme configures Swagger UI to send tokens to the /login endpoint
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scheme_name="JWT",
)

TokenDep = Annotated[str, Depends(oauth2_scheme)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(token: TokenDep, session: SessionDep) -> User:
    """Dependency: Extract token, validate JWT, and fetch user."""
    settings = get_settings()

    try:
        payload_dict = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        token_data = TokenPayload(**payload_dict)
    except (jwt.InvalidTokenError, ValidationError) as e:
        raise UnauthorizedError("Could not validate credentials") from e

    if token_data.type != "access":
        raise UnauthorizedError("Invalid token type. Expected access token.")

    user_repo = UserRepository(session)
    try:
        user_id = uuid.UUID(token_data.sub)
    except ValueError as e:
        raise UnauthorizedError("Invalid user ID format in token") from e

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise UnauthorizedError("User not found")

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_active_user(current_user: CurrentUserDep) -> User:
    """Dependency: Ensure the current user account is active."""
    if not current_user.is_active:
        raise ForbiddenError("Inactive user")
    return current_user


ActiveUserDep = Annotated[User, Depends(get_current_active_user)]


class RequireRole:
    """Dependency class for Role-Based Access Control (RBAC).

    Usage:
        @router.get("/admin", dependencies=[Depends(RequireRole(UserRole.ADMIN))])
    """

    def __init__(self, allowed_role: UserRole) -> None:
        self.allowed_role = allowed_role

    async def __call__(self, current_user: ActiveUserDep) -> User:
        """Validate that the user has the required role."""
        if current_user.role != self.allowed_role:
            raise ForbiddenError(f"Requires role: {self.allowed_role.value}")
        return current_user
