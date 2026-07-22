"""Business service for admin-managed RAG PDFs."""

import uuid

from fastapi import UploadFile

from app.core.exceptions import ConflictError, NotFoundError
from app.core.metrics import metrics_registry
from app.models.rag import RagDocument
from app.models.user import User
from app.repositories.rag_document import RagDocumentRepository
from app.services.pdf_ingestion import PdfIngestionService
from app.services.pdf_storage import PdfStorageService
from app.services.semantic_cache import SemanticCacheService


class RagDocumentService:
    """Coordinates PDF storage and RAG document database state."""

    def __init__(
        self,
        repository: RagDocumentRepository,
        storage_service: PdfStorageService,
        ingestion_service: PdfIngestionService,
        semantic_cache_service: SemanticCacheService | None = None,
    ) -> None:
        self.repository = repository
        self.storage_service = storage_service
        self.ingestion_service = ingestion_service
        self.semantic_cache_service = semantic_cache_service

    async def upload_pdf(
        self,
        *,
        title: str,
        file: UploadFile,
        uploaded_by: User,
        bot_id: uuid.UUID,
    ) -> RagDocument:
        """Store a PDF and create its document record, attached to a bot."""
        stored_pdf = await self.storage_service.save(file)
        duplicate_document = await self.repository.get_active_by_checksum(
            stored_pdf.checksum_sha256,
            bot_id=bot_id,
        )
        if duplicate_document is not None:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise ConflictError("This PDF has already been uploaded to this bot")

        document = RagDocument(
            bot_id=bot_id,
            title=title,
            original_filename=stored_pdf.original_filename,
            storage_path=stored_pdf.storage_path,
            content_type=stored_pdf.content_type,
            file_size_bytes=stored_pdf.file_size_bytes,
            checksum_sha256=stored_pdf.checksum_sha256,
            uploaded_by_id=uploaded_by.id,
        )

        try:
            created_document = await self.repository.create(document)
            return await self.ingestion_service.ingest(created_document)
        except Exception:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise

    async def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        bot_id: uuid.UUID | None = None,
    ) -> list[RagDocument]:
        """List active RAG documents, optionally scoped to a bot."""
        return await self.repository.list_active(limit=limit, offset=offset, bot_id=bot_id)

    async def update_title(self, *, document_id: uuid.UUID, title: str) -> RagDocument:
        """Update document title."""
        document = await self._get_document_or_raise(document_id)
        return await self.repository.update_title(document, title=title)

    async def replace_pdf(self, *, document_id: uuid.UUID, file: UploadFile) -> RagDocument:
        """Replace a document PDF and reset ingestion metadata."""
        document = await self._get_document_or_raise(document_id)
        old_storage_path = document.storage_path
        stored_pdf = await self.storage_service.save(file)
        duplicate_document = await self.repository.get_active_by_checksum(
            stored_pdf.checksum_sha256,
            bot_id=document.bot_id,
            exclude_document_id=document.id,
        )
        if duplicate_document is not None:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise ConflictError("This PDF has already been uploaded to this bot")

        try:
            updated_document = await self.repository.replace_file(
                document,
                original_filename=stored_pdf.original_filename,
                storage_path=stored_pdf.storage_path,
                file_size_bytes=stored_pdf.file_size_bytes,
                checksum_sha256=stored_pdf.checksum_sha256,
            )
            updated_document = await self.ingestion_service.ingest(updated_document)
        except Exception:
            await self.storage_service.delete_path(stored_pdf.storage_path)
            raise

        await self.storage_service.delete_path(old_storage_path)
        await self._clear_bot_cache(document.bot_id)
        return updated_document

    async def delete_document(self, *, document_id: uuid.UUID) -> None:
        """Soft-delete a document and remove the physical PDF."""
        document = await self._get_document_or_raise(document_id)
        bot_id = document.bot_id
        await self.repository.soft_delete(document)
        await self.storage_service.delete_path(document.storage_path)
        await self._clear_bot_cache(bot_id)
        await self._record_document_gauges()

    async def _get_document_or_raise(self, document_id: uuid.UUID) -> RagDocument:
        document = await self.repository.get_active_by_id(document_id)
        if document is None:
            raise NotFoundError("RAG document not found")
        return document

    async def _record_document_gauges(self) -> None:
        active_documents, total_chunks = await self.repository.get_document_chunk_metrics()
        metrics_registry.set_gauge("rag_active_documents", active_documents)
        metrics_registry.set_gauge("rag_total_chunks", total_chunks)

    async def _clear_bot_cache(self, bot_id: uuid.UUID | None) -> None:
        if bot_id is None or self.semantic_cache_service is None:
            return
        await self.semantic_cache_service.clear_bot(bot_id=bot_id)
