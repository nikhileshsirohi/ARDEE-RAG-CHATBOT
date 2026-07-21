"""Business service for admin-managed RAG PDFs."""

import uuid

from fastapi import UploadFile

from app.core.exceptions import NotFoundError
from app.models.rag import RagDocument
from app.models.user import User
from app.repositories.rag_document import RagDocumentRepository
from app.services.pdf_storage import PdfStorageService


class RagDocumentService:
    """Coordinates PDF storage and RAG document database state."""

    def __init__(
        self,
        repository: RagDocumentRepository,
        storage_service: PdfStorageService,
    ) -> None:
        self.repository = repository
        self.storage_service = storage_service

    async def upload_pdf(self, *, title: str, file: UploadFile, uploaded_by: User) -> RagDocument:
        """Store a PDF and create its document record."""
        stored_pdf = await self.storage_service.save(file)
        document = RagDocument(
            title=title,
            original_filename=stored_pdf.original_filename,
            storage_path=stored_pdf.storage_path,
            content_type=stored_pdf.content_type,
            file_size_bytes=stored_pdf.file_size_bytes,
            checksum_sha256=stored_pdf.checksum_sha256,
            uploaded_by_id=uploaded_by.id,
        )

        try:
            return await self.repository.create(document)
        except Exception:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise

    async def list_documents(self, *, limit: int, offset: int) -> list[RagDocument]:
        """List active RAG documents."""
        return await self.repository.list_active(limit=limit, offset=offset)

    async def update_title(self, *, document_id: uuid.UUID, title: str) -> RagDocument:
        """Update document title."""
        document = await self._get_document_or_raise(document_id)
        return await self.repository.update_title(document, title=title)

    async def replace_pdf(self, *, document_id: uuid.UUID, file: UploadFile) -> RagDocument:
        """Replace a document PDF and reset ingestion metadata."""
        document = await self._get_document_or_raise(document_id)
        old_storage_path = document.storage_path
        stored_pdf = await self.storage_service.save(file)

        try:
            updated_document = await self.repository.replace_file(
                document,
                original_filename=stored_pdf.original_filename,
                storage_path=stored_pdf.storage_path,
                file_size_bytes=stored_pdf.file_size_bytes,
                checksum_sha256=stored_pdf.checksum_sha256,
            )
        except Exception:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise

        await self.storage_service.delete_path(old_storage_path)
        return updated_document

    async def delete_document(self, *, document_id: uuid.UUID) -> None:
        """Soft-delete a document and remove the physical PDF."""
        document = await self._get_document_or_raise(document_id)
        await self.repository.soft_delete(document)
        await self.storage_service.delete_path(document.storage_path)

    async def _get_document_or_raise(self, document_id: uuid.UUID) -> RagDocument:
        document = await self.repository.get_active_by_id(document_id)
        if document is None:
            raise NotFoundError("RAG document not found")
        return document
