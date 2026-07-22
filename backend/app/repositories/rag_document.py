"""Repository for RAG document persistence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import DocumentChunk, RagDocument, RagDocumentStatus


class RagDocumentRepository:
    """Database operations for admin-managed RAG documents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, document: RagDocument) -> RagDocument:
        """Create a RAG document record."""
        self.session.add(document)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def list_active(
        self,
        *,
        limit: int,
        offset: int,
        bot_id: uuid.UUID | None = None,
    ) -> list[RagDocument]:
        """List non-deleted documents newest first, optionally scoped to a bot."""
        stmt: Select[tuple[RagDocument]] = select(RagDocument).where(
            RagDocument.deleted_at.is_(None)
        )
        if bot_id is not None:
            stmt = stmt.where(RagDocument.bot_id == bot_id)
        stmt = stmt.order_by(RagDocument.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_id(self, document_id: uuid.UUID) -> RagDocument | None:
        """Get one non-deleted document by ID."""
        stmt = select(RagDocument).where(
            RagDocument.id == document_id,
            RagDocument.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_checksum(
        self,
        checksum_sha256: str,
        *,
        bot_id: uuid.UUID | None,
        exclude_document_id: uuid.UUID | None = None,
    ) -> RagDocument | None:
        """Get an active bot document by file checksum, optionally excluding one document."""
        stmt = select(RagDocument).where(
            RagDocument.checksum_sha256 == checksum_sha256,
            RagDocument.deleted_at.is_(None),
        )
        if bot_id is None:
            stmt = stmt.where(RagDocument.bot_id.is_(None))
        else:
            stmt = stmt.where(RagDocument.bot_id == bot_id)
        if exclude_document_id is not None:
            stmt = stmt.where(RagDocument.id != exclude_document_id)
        stmt = stmt.order_by(RagDocument.created_at.desc(), RagDocument.id.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_title(self, document: RagDocument, *, title: str) -> RagDocument:
        """Update document metadata."""
        document.title = title
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def replace_file(
        self,
        document: RagDocument,
        *,
        original_filename: str,
        storage_path: str,
        file_size_bytes: int,
        checksum_sha256: str,
    ) -> RagDocument:
        """Replace the physical PDF metadata and reset ingestion state."""
        document.original_filename = original_filename
        document.storage_path = storage_path
        document.file_size_bytes = file_size_bytes
        document.checksum_sha256 = checksum_sha256
        document.version += 1
        document.status = RagDocumentStatus.PENDING
        document.page_count = None
        document.chunk_count = 0
        document.error_message = None
        document.processed_at = None

        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def mark_processing(self, document: RagDocument) -> RagDocument:
        """Mark a document as currently being ingested."""
        document.status = RagDocumentStatus.PROCESSING
        document.error_message = None
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def complete_ingestion(
        self,
        document: RagDocument,
        *,
        chunks: list[DocumentChunk],
        page_count: int,
    ) -> RagDocument:
        """Persist chunks and mark a document ready for retrieval."""
        self.session.add_all(chunks)
        document.status = RagDocumentStatus.READY
        document.page_count = page_count
        document.chunk_count = len(chunks)
        document.error_message = None
        document.processed_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def mark_failed(self, document: RagDocument, *, error_message: str) -> RagDocument:
        """Mark ingestion failure without deleting the admin-uploaded PDF."""
        document.status = RagDocumentStatus.FAILED
        document.error_message = error_message[:4000]
        document.processed_at = None
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def soft_delete(self, document: RagDocument) -> RagDocument:
        """Soft-delete a document and remove its searchable chunks."""
        document.deleted_at = datetime.now(UTC)
        document.status = RagDocumentStatus.ARCHIVED
        await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        await self.session.flush()
        await self.session.refresh(document)
        return document

    async def get_document_chunk_metrics(self) -> tuple[int, int]:
        """Return active ready document and chunk totals for gauges."""
        stmt = select(
            func.count(RagDocument.id),
            func.coalesce(func.sum(RagDocument.chunk_count), 0),
        ).where(
            RagDocument.deleted_at.is_(None),
            RagDocument.status == RagDocumentStatus.READY,
        )
        result = await self.session.execute(stmt)
        active_documents, total_chunks = result.one()
        return int(active_documents), int(total_chunks)
