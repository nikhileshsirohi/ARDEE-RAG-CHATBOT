"""API v1 package — version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1.routes import health

v1_router = APIRouter(prefix="/api/v1")

# Register all v1 route modules
v1_router.include_router(health.router)
