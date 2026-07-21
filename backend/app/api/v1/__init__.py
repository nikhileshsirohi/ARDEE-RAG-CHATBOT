"""API v1 package — version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.rag_documents import router as rag_documents_router
from app.api.v1.routes.rag_search import router as rag_search_router

v1_router = APIRouter(prefix="/api/v1")

# Register all v1 route modules
v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(rag_documents_router)
v1_router.include_router(rag_search_router)
