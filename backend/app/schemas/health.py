"""Health check response schemas.

Separating schemas from routes follows the Single Responsibility Principle.
Schemas define *what* data looks like. Routes define *how* to handle requests.
"""

from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status of an individual service (database, Redis, etc.).

    Attributes:
        status: Connection status ('connected' or 'disconnected').
        latency_ms: Round-trip latency in milliseconds (None if disconnected).
        error: Error message if disconnected (None if connected).
    """

    status: str = Field(
        ...,
        examples=["connected"],
        description="Service connection status",
    )
    latency_ms: float | None = Field(
        default=None,
        examples=[1.23],
        description="Latency in milliseconds",
    )
    error: str | None = Field(
        default=None,
        description="Error message if service is disconnected",
    )


class HealthResponse(BaseModel):
    """Response schema for the health check endpoint.

    Shallow health (default): status, version, environment only.
    Deep health (?deep=true): includes database and Redis connectivity.

    Attributes:
        status: Overall application health status.
        version: Application version string.
        environment: Current deployment environment.
        database: Database health (only present in deep checks).
        redis: Redis health (only present in deep checks).
    """

    status: str = Field(
        ...,
        examples=["healthy"],
        description="Overall application health status",
    )
    version: str = Field(
        ...,
        examples=["0.1.0"],
        description="Application version",
    )
    environment: str = Field(
        ...,
        examples=["development"],
        description="Deployment environment",
    )
    database: ServiceHealth | None = Field(
        default=None,
        description="Database health (deep check only)",
    )
    redis: ServiceHealth | None = Field(
        default=None,
        description="Redis health (deep check only)",
    )
