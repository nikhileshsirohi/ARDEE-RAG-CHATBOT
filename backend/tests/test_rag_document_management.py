"""Tests for admin RAG document management support."""

import uuid
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.config import Settings
from app.core.exceptions import BadRequestError, ConflictError
from app.main import create_app
from app.models.rag import RagDocument
from app.models.user import User, UserRole
from app.services.pdf_storage import PdfStorageService, StoredPdf
from app.services.rag_document import RagDocumentService


def make_upload_file(
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> UploadFile:
    """Create an in-memory upload file for tests."""
    return UploadFile(
        BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.anyio
async def test_pdf_storage_saves_valid_pdf(tmp_path: Path) -> None:
    """Valid PDF uploads should be persisted with checksum metadata."""
    settings = Settings(upload_dir=str(tmp_path), max_upload_size_mb=1)
    storage = PdfStorageService(settings)
    upload = make_upload_file(filename="handbook.pdf", content=b"%PDF-1.4\ncontent")

    stored_pdf = await storage.save(upload)

    stored_path = Path(stored_pdf.storage_path)
    assert stored_path.exists()
    assert stored_pdf.original_filename == "handbook.pdf"
    assert stored_pdf.file_size_bytes == len(b"%PDF-1.4\ncontent")
    assert len(stored_pdf.checksum_sha256) == 64


@pytest.mark.anyio
async def test_pdf_storage_rejects_non_pdf_extension(tmp_path: Path) -> None:
    """Only configured PDF extensions are accepted."""
    settings = Settings(upload_dir=str(tmp_path), max_upload_size_mb=1)
    storage = PdfStorageService(settings)
    upload = make_upload_file(filename="notes.txt", content=b"not a pdf")

    with pytest.raises(BadRequestError, match="Only PDF uploads are allowed"):
        await storage.save(upload)


@pytest.mark.anyio
async def test_pdf_storage_rejects_non_pdf_content_type(tmp_path: Path) -> None:
    """Content type must also be PDF."""
    settings = Settings(upload_dir=str(tmp_path), max_upload_size_mb=1)
    storage = PdfStorageService(settings)
    upload = make_upload_file(
        filename="handbook.pdf",
        content=b"not a pdf",
        content_type="text/plain",
    )

    with pytest.raises(BadRequestError, match="PDF content type"):
        await storage.save(upload)


class FakeDocumentRepository:
    """In-memory repository capturing duplicate lookups and chunk deletion."""

    def __init__(
        self,
        *,
        existing_titles: set[str] | None = None,
        existing_filenames: set[str] | None = None,
    ) -> None:
        self.existing_titles = {t.lower() for t in (existing_titles or set())}
        self.existing_filenames = {f.lower() for f in (existing_filenames or set())}
        self.created: list[RagDocument] = []
        self.deleted_chunk_document_ids: list[uuid.UUID] = []
        self.soft_deleted: list[RagDocument] = []

    async def get_active_by_title(self, title: str) -> RagDocument | None:
        return RagDocument() if title.strip().lower() in self.existing_titles else None

    async def get_active_by_original_filename(self, original_filename: str) -> RagDocument | None:
        return (
            RagDocument() if original_filename.strip().lower() in self.existing_filenames else None
        )

    async def create(self, document: RagDocument) -> RagDocument:
        document.id = uuid.uuid4()
        self.created.append(document)
        return document

    async def get_active_by_id(self, document_id: uuid.UUID) -> RagDocument | None:
        document = RagDocument()
        document.id = document_id
        document.storage_path = "/tmp/x.pdf"
        return document

    async def delete_chunks(self, document_id: uuid.UUID) -> None:
        self.deleted_chunk_document_ids.append(document_id)

    async def soft_delete(self, document: RagDocument) -> RagDocument:
        self.soft_deleted.append(document)
        return document

    async def get_document_chunk_metrics(self) -> tuple[int, int]:
        return 0, 0


class FakeStorageService:
    """Records save/delete calls."""

    def __init__(self) -> None:
        self.saved = False
        self.deleted_paths: list[str] = []

    async def save(self, upload: UploadFile) -> StoredPdf:
        self.saved = True
        return StoredPdf(
            original_filename=upload.filename or "file.pdf",
            storage_path="/tmp/stored.pdf",
            content_type="application/pdf",
            file_size_bytes=10,
            checksum_sha256="a" * 64,
        )

    async def delete_path(self, storage_path: str) -> None:
        self.deleted_paths.append(storage_path)


class FakeIngestionService:
    """Returns the document unchanged."""

    async def ingest(self, document: RagDocument) -> RagDocument:
        return document


def make_admin() -> User:
    return User(id=uuid.uuid4(), email="admin@example.com", role=UserRole.ADMIN, is_active=True)


@pytest.mark.anyio
async def test_upload_rejects_duplicate_document_name() -> None:
    """Uploading a PDF whose title already exists is rejected before storing."""
    repository = FakeDocumentRepository(existing_titles={"Employee Handbook"})
    storage = FakeStorageService()
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
    )
    upload = make_upload_file(filename="new.pdf", content=b"%PDF-1.4")

    with pytest.raises(ConflictError, match="already exists"):
        await service.upload_pdf(title="employee handbook", file=upload, uploaded_by=make_admin())

    assert storage.saved is False  # rejected before touching disk


@pytest.mark.anyio
async def test_upload_rejects_duplicate_file_name() -> None:
    """Uploading a PDF whose source filename already exists is rejected."""
    repository = FakeDocumentRepository(existing_filenames={"handbook.pdf"})
    storage = FakeStorageService()
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
    )
    upload = make_upload_file(filename="Handbook.pdf", content=b"%PDF-1.4")

    with pytest.raises(ConflictError, match="file named"):
        await service.upload_pdf(title="Fresh title", file=upload, uploaded_by=make_admin())

    assert storage.saved is False


@pytest.mark.anyio
async def test_delete_document_removes_chunks_and_file() -> None:
    """Deleting a document hard-deletes its chunks and removes the PDF file."""
    repository = FakeDocumentRepository()
    storage = FakeStorageService()
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
    )
    document_id = uuid.uuid4()

    await service.delete_document(document_id=document_id)

    assert repository.deleted_chunk_document_ids == [document_id]  # chunks/embeddings removed
    assert len(repository.soft_deleted) == 1
    assert storage.deleted_paths == ["/tmp/x.pdf"]


def test_rag_document_routes_are_registered() -> None:
    """The admin document router should be mounted under API v1."""
    app = create_app()
    route_paths = set(app.openapi()["paths"].keys())

    assert "/api/v1/rag/documents" in route_paths
    assert "/api/v1/rag/documents/{document_id}" in route_paths
    assert "/api/v1/rag/documents/{document_id}/file" in route_paths


class FakeDocumentRepository:
    """Small fake for document service policy tests."""

    def __init__(self) -> None:
        self.duplicate: RagDocument | None = None
        self.created: RagDocument | None = None
        self.deleted: RagDocument | None = None
        self.active_document: RagDocument | None = None
        self.checksum_lookup_bot_id: object | None = None

    async def get_active_by_checksum(
        self,
        checksum_sha256: str,
        *,
        bot_id: object | None,
        exclude_document_id: object | None = None,
    ) -> RagDocument | None:
        _ = checksum_sha256
        _ = exclude_document_id
        self.checksum_lookup_bot_id = bot_id
        if self.duplicate is not None and self.duplicate.bot_id != bot_id:
            return None
        return self.duplicate

    async def create(self, document: RagDocument) -> RagDocument:
        document.id = uuid4()
        self.created = document
        return document

    async def get_active_by_id(self, document_id: object) -> RagDocument | None:
        _ = document_id
        return self.active_document

    async def soft_delete(self, document: RagDocument) -> RagDocument:
        self.deleted = document
        return document

    async def get_document_chunk_metrics(self) -> tuple[int, int]:
        return 0, 0


class FakeStorageService:
    """Fake PDF storage that records cleanup."""

    def __init__(self, stored_pdf: StoredPdf) -> None:
        self.stored_pdf = stored_pdf
        self.deleted_paths: list[str] = []

    async def save(self, upload: UploadFile) -> StoredPdf:
        _ = upload
        return self.stored_pdf

    async def delete_path(self, storage_path: str) -> None:
        self.deleted_paths.append(storage_path)


class FakeIngestionService:
    """Fake ingestion that returns the document unchanged."""

    async def ingest(self, document: RagDocument) -> RagDocument:
        return document


class FakeSemanticCacheService:
    """Fake cache service that records invalidated bots."""

    def __init__(self) -> None:
        self.cleared_bot_ids: list[object] = []

    async def clear_bot(self, *, bot_id: object) -> None:
        self.cleared_bot_ids.append(bot_id)


def make_stored_pdf(checksum: str = "a" * 64) -> StoredPdf:
    """Create stored PDF metadata for service tests."""
    return StoredPdf(
        original_filename="handbook.pdf",
        storage_path="/uploads/handbook.pdf",
        content_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256=checksum,
    )


def make_admin_user() -> User:
    """Create a test admin user."""
    return User(
        id=uuid4(),
        email="admin@example.com",
        password_hash="test-password-hash",  # noqa: S106
        role=UserRole.ADMIN,
    )


@pytest.mark.anyio
async def test_document_service_rejects_duplicate_active_pdf_upload() -> None:
    """An active document with the same checksum should block duplicate uploads."""
    stored_pdf = make_stored_pdf()
    bot_id = uuid4()
    repository = FakeDocumentRepository()
    repository.duplicate = RagDocument(
        id=uuid4(),
        bot_id=bot_id,
        title="Existing",
        original_filename="existing.pdf",
        storage_path="/uploads/existing.pdf",
        file_size_bytes=10,
        checksum_sha256=stored_pdf.checksum_sha256,
    )
    storage = FakeStorageService(stored_pdf)
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
    )

    with pytest.raises(ConflictError, match="already been uploaded"):
        await service.upload_pdf(
            title="Duplicate",
            file=make_upload_file(filename="handbook.pdf", content=b"%PDF"),
            uploaded_by=make_admin_user(),
            bot_id=bot_id,
        )

    assert repository.created is None
    assert repository.checksum_lookup_bot_id == bot_id
    assert storage.deleted_paths == [stored_pdf.storage_path]


@pytest.mark.anyio
async def test_document_service_allows_same_pdf_upload_to_different_bot() -> None:
    """The same PDF checksum may be active once in each bot."""
    stored_pdf = make_stored_pdf()
    source_bot_id = uuid4()
    target_bot_id = uuid4()
    repository = FakeDocumentRepository()
    repository.duplicate = RagDocument(
        id=uuid4(),
        bot_id=source_bot_id,
        title="Existing",
        original_filename="existing.pdf",
        storage_path="/uploads/existing.pdf",
        file_size_bytes=10,
        checksum_sha256=stored_pdf.checksum_sha256,
    )
    storage = FakeStorageService(stored_pdf)
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
    )

    document = await service.upload_pdf(
        title="Allowed",
        file=make_upload_file(filename="handbook.pdf", content=b"%PDF"),
        uploaded_by=make_admin_user(),
        bot_id=target_bot_id,
    )

    assert document.bot_id == target_bot_id
    assert repository.created is document
    assert repository.checksum_lookup_bot_id == target_bot_id
    assert storage.deleted_paths == []


@pytest.mark.anyio
async def test_document_service_delete_clears_bot_semantic_cache() -> None:
    """Deleting a document should invalidate cached answers for that bot."""
    bot_id = uuid4()
    document = RagDocument(
        id=uuid4(),
        bot_id=bot_id,
        title="Policy",
        original_filename="policy.pdf",
        storage_path="/uploads/policy.pdf",
        file_size_bytes=10,
        checksum_sha256="b" * 64,
    )
    repository = FakeDocumentRepository()
    repository.active_document = document
    storage = FakeStorageService(make_stored_pdf())
    cache = FakeSemanticCacheService()
    service = RagDocumentService(
        repository=repository,  # type: ignore[arg-type]
        storage_service=storage,  # type: ignore[arg-type]
        ingestion_service=FakeIngestionService(),  # type: ignore[arg-type]
        semantic_cache_service=cache,  # type: ignore[arg-type]
    )

    await service.delete_document(document_id=document.id)

    assert repository.deleted is document
    assert storage.deleted_paths == [document.storage_path]
    assert cache.cleared_bot_ids == [bot_id]
