"""Document ingestion helpers for the Corvail Invoices API."""
from __future__ import annotations

import io
from typing import Optional, Tuple

from fastapi import UploadFile
from starlette.datastructures import FormData

from src.core import FileTooLargeError, IngestionError, UnsupportedFileTypeError
from src.core.config import Settings

PDF_MAGIC = b'%PDF'
PDF_CONTENT_TYPES = {'application/pdf', 'application/x-pdf', 'binary/octet-stream'}


def _is_pdf_filename(filename: str) -> bool:
    """Return whether a filename looks like a PDF."""
    return filename.lower().endswith('.pdf')


def validate_pdf_integrity(pdf_bytes: bytes, filename: str = 'document') -> None:
    """Validate PDF integrity beyond magic bytes."""
    if len(pdf_bytes) < 1024:
        raise IngestionError(message=f'File too small to be a valid PDF ({len(pdf_bytes)} bytes)', error_code='PDF_TOO_SMALL')
    if pdf_bytes[:4] != PDF_MAGIC:
        raise UnsupportedFileTypeError()
    header_line = pdf_bytes[:20].decode('latin-1', errors='replace')
    if not any(f'%PDF-1.{i}' in header_line or f'%PDF-2.{i}' in header_line for i in range(10)):
        raise IngestionError(message='Unrecognised PDF version', error_code='INVALID_PDF_VERSION')
    tail = pdf_bytes[-1024:].decode('latin-1', errors='replace')
    if '%%EOF' not in tail:
        raise IngestionError(message='PDF appears truncated or corrupted — missing EOF marker', error_code='PDF_TRUNCATED')


def wipe_bytesio(buf: io.BytesIO | None) -> None:
    """Overwrite and close an in-memory buffer."""
    if buf is None:
        return
    try:
        view = buf.getbuffer()
        view[:] = b'\x00' * len(view)
        view.release()
    finally:
        buf.close()


async def ingest_from_sendgrid(form: FormData, settings: Settings) -> Tuple[Optional[str], str, bytes]:
    """Extract the first PDF attachment from a SendGrid form payload."""
    sender = form.get('from') or form.get('sender')
    for _, value in form.multi_items():
        if not isinstance(value, UploadFile):
            continue
        filename = value.filename or 'document.pdf'
        content_type = (value.content_type or '').lower()
        if content_type not in PDF_CONTENT_TYPES and not _is_pdf_filename(filename):
            continue
        data = await value.read()
        if len(data) > settings.max_upload_bytes:
            raise FileTooLargeError()
        validate_pdf_integrity(data, filename)
        return sender, filename, data
    raise IngestionError(message='No PDF attachment found in SendGrid payload')


async def ingest_from_upload(file: UploadFile, settings: Settings) -> Tuple[str, bytes]:
    """Read a direct upload into validated PDF bytes."""
    filename = file.filename or 'document.pdf'
    content_type = (file.content_type or '').lower()
    if content_type not in PDF_CONTENT_TYPES and not _is_pdf_filename(filename):
        raise UnsupportedFileTypeError()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError()
    validate_pdf_integrity(data, filename)
    return filename, data
