"""Repository for RAG document persistence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, delete, select
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

    async def list_active(self, *, limit: int, offset: int) -> list[RagDocument]:
        """List non-deleted documents newest first."""
        stmt: Select[tuple[RagDocument]] = (
            select(RagDocument)
            .where(RagDocument.deleted_at.is_(None))
            .order_by(RagDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
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

    async def soft_delete(self, document: RagDocument) -> RagDocument:
        """Soft-delete a document so audit history remains intact."""
        document.deleted_at = datetime.now(UTC)
        document.status = RagDocumentStatus.ARCHIVED
        await self.session.flush()
        await self.session.refresh(document)
        return document
