"""Tests for PDF ingestion services."""

import uuid

import pytest

from app.config import Settings
from app.models.rag import DocumentChunk, RagDocument, RagDocumentStatus
from app.services.pdf_ingestion import (
    ExtractedPage,
    LlamaIndexChunker,
    PdfIngestionService,
)


class FakeRepository:
    """Minimal repository fake for ingestion tests."""

    def __init__(self) -> None:
        self.saved_chunks: list[DocumentChunk] = []

    async def mark_processing(self, document: RagDocument) -> RagDocument:
        document.status = RagDocumentStatus.PROCESSING
        return document

    async def complete_ingestion(
        self,
        document: RagDocument,
        *,
        chunks: list[DocumentChunk],
        page_count: int,
    ) -> RagDocument:
        self.saved_chunks = chunks
        document.status = RagDocumentStatus.READY
        document.page_count = page_count
        document.chunk_count = len(chunks)
        document.error_message = None
        return document

    async def mark_failed(self, document: RagDocument, *, error_message: str) -> RagDocument:
        document.status = RagDocumentStatus.FAILED
        document.error_message = error_message
        return document

    async def get_document_chunk_metrics(self) -> tuple[int, int]:
        return 1, len(self.saved_chunks)


class FakeExtractor:
    """Return preconfigured extracted pages."""

    def __init__(self, pages: list[ExtractedPage]) -> None:
        self.pages = pages

    async def extract_pages(self, _storage_path: str) -> list[ExtractedPage]:
        return self.pages


class FakeEmbeddingService:
    """Return deterministic fake embeddings."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1536 for _text in texts]


def make_document() -> RagDocument:
    """Build a document model without database access."""
    return RagDocument(
        id=uuid.uuid4(),
        title="Policy",
        original_filename="policy.pdf",
        storage_path="policy.pdf",
        content_type="application/pdf",
        file_size_bytes=100,
        checksum_sha256="a" * 64,
        uploaded_by_id=uuid.uuid4(),
    )


def test_llama_index_chunker_creates_ordered_chunks() -> None:
    """Chunker should preserve page metadata and produce ordered indexes."""
    settings = Settings(rag_chunk_size=20, rag_chunk_overlap=2)
    chunker = LlamaIndexChunker(settings)

    chunks = chunker.chunk_pages(
        [
            ExtractedPage(page_number=1, text="First policy paragraph. Second policy paragraph."),
            ExtractedPage(page_number=2, text="Third policy paragraph."),
        ]
    )

    assert chunks
    assert chunks[0].chunk_index == 0
    assert {chunk.page_number for chunk in chunks} == {1, 2}


@pytest.mark.anyio
async def test_pdf_ingestion_marks_document_ready_and_saves_chunks() -> None:
    """Successful ingestion should persist embedded chunks and mark READY."""
    repository = FakeRepository()
    document = make_document()
    ingestion = PdfIngestionService(
        repository=repository,  # type: ignore[arg-type]
        extractor=FakeExtractor([ExtractedPage(page_number=1, text="Policy text.")]),  # type: ignore[arg-type]
        chunker=LlamaIndexChunker(Settings(rag_chunk_size=20, rag_chunk_overlap=2)),
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
    )

    ingested_document = await ingestion.ingest(document)

    assert ingested_document.status == RagDocumentStatus.READY
    assert ingested_document.chunk_count == 1
    assert repository.saved_chunks[0].embedding == [0.01] * 1536


@pytest.mark.anyio
async def test_pdf_ingestion_marks_document_failed_when_no_text() -> None:
    """Documents with no extractable text should be visible as FAILED."""
    document = make_document()
    ingestion = PdfIngestionService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        extractor=FakeExtractor([]),  # type: ignore[arg-type]
        chunker=LlamaIndexChunker(Settings(rag_chunk_size=20, rag_chunk_overlap=2)),
        embedding_service=FakeEmbeddingService(),  # type: ignore[arg-type]
    )

    ingested_document = await ingestion.ingest(document)

    assert ingested_document.status == RagDocumentStatus.FAILED
    assert ingested_document.error_message == "PDF has no extractable text"
