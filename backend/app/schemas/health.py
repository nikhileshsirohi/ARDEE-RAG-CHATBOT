"""Health check response schemas.

Separating schemas from routes follows the Single Responsibility Principle.
Schemas define *what* data looks like. Routes define *how* to handle requests.
"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response schema for the health check endpoint.

    Attributes:
        status: Current application health status.
        version: Application version string.
        environment: Current deployment environment.
    """

    status: str = Field(..., examples=["healthy"], description="Application health status")
    version: str = Field(..., examples=["0.1.0"], description="Application version")
    environment: str = Field(..., examples=["development"], description="Deployment environment")
