"""Global exception handlers for FastAPI.

Design Decisions:
    - Centralized exception handling ensures consistent error response format.
    - Custom exception classes map to HTTP status codes.
    - Unhandled exceptions return a safe 500 response (no stack trace leaking).
    - All errors are logged with structlog for observability.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base application error.

    All custom exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(AppError):
    """Authentication failed (401)."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message=message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    """Insufficient permissions (403)."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN)


class ConflictError(AppError):
    """Resource conflict (409)."""

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message=message, status_code=status.HTTP_409_CONFLICT)


class BadRequestError(AppError):
    """Invalid request (400)."""

    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(message=message, status_code=status.HTTP_400_BAD_REQUEST)


class RateLimitError(AppError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message=message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle custom application errors."""
        logger.warning(
            "Application error",
            status_code=exc.status_code,
            detail=exc.detail,
            path=str(request.url),
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "detail": exc.detail,
                    "status_code": exc.status_code,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with a clean response."""
        logger.warning(
            "Validation error",
            errors=exc.errors(),
            path=str(request.url),
            method=request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "message": "Validation error",
                    "detail": exc.errors(),
                    "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions. Never leaks stack traces."""
        logger.error(
            "Unhandled exception",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            path=str(request.url),
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "message": "Internal server error",
                    "detail": "An unexpected error occurred. Please try again later.",
                    "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                }
            },
        )
