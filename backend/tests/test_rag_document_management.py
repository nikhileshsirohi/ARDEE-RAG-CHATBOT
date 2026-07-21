"""Tests for admin RAG document management support."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.config import Settings
from app.core.exceptions import BadRequestError
from app.main import create_app
from app.services.pdf_storage import PdfStorageService


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


def test_rag_document_routes_are_registered() -> None:
    """The admin document router should be mounted under API v1."""
    app = create_app()
    route_paths = set(app.openapi()["paths"].keys())

    assert "/api/v1/rag/documents" in route_paths
    assert "/api/v1/rag/documents/{document_id}" in route_paths
    assert "/api/v1/rag/documents/{document_id}/file" in route_paths
