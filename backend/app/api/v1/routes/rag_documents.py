"""Admin RAG document management routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.api.dependencies.auth import RequireRole, SessionDep
from app.config import get_settings
from app.models.user import User, UserRole
from app.repositories.rag_document import RagDocumentRepository
from app.schemas.rag import RagDocumentResponse, RagDocumentUpdate
from app.services.pdf_storage import PdfStorageService
from app.services.rag_document import RagDocumentService

router = APIRouter(prefix="/rag/documents", tags=["RAG Documents"])

AdminDep = Annotated[User, Depends(RequireRole(UserRole.ADMIN))]


def get_document_service(session: SessionDep) -> RagDocumentService:
    """Build document service from request-scoped dependencies."""
    settings = get_settings()
    return RagDocumentService(
        repository=RagDocumentRepository(session),
        storage_service=PdfStorageService(settings),
    )


DocumentServiceDep = Annotated[RagDocumentService, Depends(get_document_service)]


@router.post(
    "",
    response_model=RagDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF for RAG",
)
async def upload_document(
    admin_user: AdminDep,
    service: DocumentServiceDep,
    title: Annotated[str, Form(min_length=1, max_length=255)],
    file: Annotated[UploadFile, File()],
) -> RagDocumentResponse:
    """Upload a PDF document. Admin-only."""
    document = await service.upload_pdf(title=title, file=file, uploaded_by=admin_user)
    return RagDocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=list[RagDocumentResponse],
    summary="List uploaded RAG PDFs",
)
async def list_documents(
    _admin_user: AdminDep,
    service: DocumentServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RagDocumentResponse]:
    """List active RAG documents. Admin-only."""
    documents = await service.list_documents(limit=limit, offset=offset)
    return [RagDocumentResponse.model_validate(document) for document in documents]


@router.patch(
    "/{document_id}",
    response_model=RagDocumentResponse,
    summary="Update RAG PDF metadata",
)
async def update_document(
    document_id: uuid.UUID,
    document_in: RagDocumentUpdate,
    _admin_user: AdminDep,
    service: DocumentServiceDep,
) -> RagDocumentResponse:
    """Update document metadata. Admin-only."""
    document = await service.update_title(document_id=document_id, title=document_in.title)
    return RagDocumentResponse.model_validate(document)


@router.put(
    "/{document_id}/file",
    response_model=RagDocumentResponse,
    summary="Replace a RAG PDF file",
)
async def replace_document_file(
    document_id: uuid.UUID,
    _admin_user: AdminDep,
    service: DocumentServiceDep,
    file: Annotated[UploadFile, File()],
) -> RagDocumentResponse:
    """Replace the PDF file for an existing document. Admin-only."""
    document = await service.replace_pdf(document_id=document_id, file=file)
    return RagDocumentResponse.model_validate(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a RAG PDF",
)
async def delete_document(
    document_id: uuid.UUID,
    _admin_user: AdminDep,
    service: DocumentServiceDep,
) -> Response:
    """Soft-delete a RAG document. Admin-only."""
    await service.delete_document(document_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
