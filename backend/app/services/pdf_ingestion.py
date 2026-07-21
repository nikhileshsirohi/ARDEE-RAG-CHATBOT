"""PDF ingestion services for RAG document chunks."""

import asyncio
import time
from dataclasses import dataclass

from llama_index.core.node_parser import SentenceSplitter
from openai import AsyncOpenAI
from pypdf import PdfReader

from app.config import Settings
from app.core.metrics import metrics_registry
from app.models.rag import DocumentChunk, RagDocument
from app.repositories.rag_document import RagDocumentRepository


@dataclass(frozen=True)
class ExtractedPage:
    """Text extracted from one PDF page."""

    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    """Chunk prepared for embedding and storage."""

    chunk_index: int
    page_number: int
    content: str
    token_count: int


class PdfTextExtractor:
    """Extract text from PDFs using pypdf."""

    async def extract_pages(self, storage_path: str) -> list[ExtractedPage]:
        """Extract non-empty text from each PDF page."""
        return await asyncio.to_thread(self._extract_pages_sync, storage_path)

    @staticmethod
    def _extract_pages_sync(storage_path: str) -> list[ExtractedPage]:
        reader = PdfReader(storage_path)
        pages: list[ExtractedPage] = []

        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(ExtractedPage(page_number=index, text=text))

        return pages


class LlamaIndexChunker:
    """Create retrieval chunks using LlamaIndex's sentence splitter."""

    def __init__(self, settings: Settings) -> None:
        self.splitter = SentenceSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )

    def chunk_pages(self, pages: list[ExtractedPage]) -> list[TextChunk]:
        """Split extracted PDF pages into ordered chunks."""
        chunks: list[TextChunk] = []

        for page in pages:
            for chunk_text in self.splitter.split_text(page.text):
                normalized_text = chunk_text.strip()
                if not normalized_text:
                    continue

                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        page_number=page.page_number,
                        content=normalized_text,
                        token_count=len(normalized_text.split()),
                    )
                )

        return chunks


class OpenAIEmbeddingService:
    """Generate embeddings through the OpenAI API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches."""
        embeddings: list[list[float]] = []
        batch_size = self.settings.rag_embedding_batch_size

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            started_at = time.monotonic()
            metrics_registry.increment_counter("embedding_calls_total")
            try:
                response = await self.client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=batch,
                    dimensions=self.settings.openai_embedding_dimensions,
                )
            finally:
                metrics_registry.observe_histogram(
                    "embedding_call_duration_seconds",
                    time.monotonic() - started_at,
                )
            embeddings.extend([item.embedding for item in response.data])

        return embeddings


class PdfIngestionService:
    """Extract, chunk, embed, and persist a PDF for retrieval."""

    def __init__(
        self,
        repository: RagDocumentRepository,
        extractor: PdfTextExtractor,
        chunker: LlamaIndexChunker,
        embedding_service: OpenAIEmbeddingService,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.chunker = chunker
        self.embedding_service = embedding_service

    async def ingest(self, document: RagDocument) -> RagDocument:
        """Ingest a PDF and update document processing status."""
        await self.repository.mark_processing(document)

        try:
            pages = await self.extractor.extract_pages(document.storage_path)
            if not pages:
                raise ValueError("PDF has no extractable text")

            text_chunks = self.chunker.chunk_pages(pages)
            if not text_chunks:
                raise ValueError("PDF produced no searchable chunks")

            embeddings = await self.embedding_service.embed_texts(
                [chunk.content for chunk in text_chunks]
            )
            if len(embeddings) != len(text_chunks):
                raise ValueError("Embedding count does not match chunk count")

            document_chunks = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=embedding,
                    metadata_={
                        "document_title": document.title,
                        "original_filename": document.original_filename,
                    },
                )
                for chunk, embedding in zip(text_chunks, embeddings, strict=True)
            ]
            completed_document = await self.repository.complete_ingestion(
                document,
                chunks=document_chunks,
                page_count=max(page.page_number for page in pages),
            )
            metrics_registry.increment_counter("rag_documents_ingested_total")
            await self._record_document_gauges()
            return completed_document
        except Exception as exc:
            metrics_registry.increment_counter("rag_ingestion_errors_total")
            return await self.repository.mark_failed(document, error_message=str(exc))

    async def _record_document_gauges(self) -> None:
        active_documents, total_chunks = await self.repository.get_document_chunk_metrics()
        metrics_registry.set_gauge("rag_active_documents", active_documents)
        metrics_registry.set_gauge("rag_total_chunks", total_chunks)
