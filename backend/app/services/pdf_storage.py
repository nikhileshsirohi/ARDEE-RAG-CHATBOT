"""Local PDF storage service for RAG uploads."""

import asyncio
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import Settings
from app.core.exceptions import BadRequestError

PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StoredPdf:
    """Metadata for a stored PDF file."""

    original_filename: str
    storage_path: str
    content_type: str
    file_size_bytes: int
    checksum_sha256: str


class PdfStorageService:
    """Validate and store uploaded PDF files atomically on local disk."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.upload_dir = settings.upload_dir_path

    async def save(self, upload: UploadFile) -> StoredPdf:
        """Validate and persist a PDF upload."""
        original_filename = self._validate_filename(upload.filename)
        content_type = upload.content_type or "application/octet-stream"
        self._validate_content_type(content_type)

        destination = self.upload_dir / f"{uuid.uuid4()}.pdf"
        temp_destination = destination.with_suffix(".tmp")
        await asyncio.to_thread(self.upload_dir.mkdir, parents=True, exist_ok=True)

        digest = hashlib.sha256()
        total_size = 0

        try:
            with temp_destination.open("wb") as file_obj:
                while chunk := await upload.read(CHUNK_SIZE_BYTES):
                    total_size += len(chunk)
                    if total_size > self.settings.max_upload_size_bytes:
                        raise BadRequestError(
                            f"PDF exceeds {self.settings.max_upload_size_mb} MB upload limit"
                        )
                    digest.update(chunk)
                    await asyncio.to_thread(file_obj.write, chunk)

            if total_size == 0:
                raise BadRequestError("Uploaded PDF is empty")

            await asyncio.to_thread(os.replace, temp_destination, destination)
        except Exception:
            await self.delete_path(str(temp_destination))
            raise
        finally:
            await upload.close()

        return StoredPdf(
            original_filename=original_filename,
            storage_path=str(destination),
            content_type=content_type,
            file_size_bytes=total_size,
            checksum_sha256=digest.hexdigest(),
        )

    async def delete_path(self, storage_path: str) -> None:
        """Remove a file if it exists."""
        path = Path(storage_path)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    def _validate_filename(self, filename: str | None) -> str:
        if not filename:
            raise BadRequestError("PDF filename is required")

        normalized = Path(filename).name
        if Path(normalized).suffix.lower() not in self.settings.allowed_extensions_list:
            raise BadRequestError("Only PDF uploads are allowed")

        return normalized

    @staticmethod
    def _validate_content_type(content_type: str) -> None:
        if content_type not in PDF_CONTENT_TYPES:
            raise BadRequestError("Uploaded file must have a PDF content type")
