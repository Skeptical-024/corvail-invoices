from __future__ import annotations

import io
from typing import Optional, Tuple

from fastapi import UploadFile
from starlette.datastructures import FormData

from src.core import IngestionError
from src.core.config import Settings

PDF_MAGIC = b'%PDF'


def _is_pdf_file(upload: UploadFile) -> bool:
    """Return whether an upload looks like a PDF."""
    return bool((upload.content_type and 'pdf' in upload.content_type.lower()) or (upload.filename and upload.filename.lower().endswith('.pdf')))


def validate_pdf_buffer(buffer: io.BytesIO, settings: Settings) -> None:
    """Validate PDF size and magic bytes."""
    view = buffer.getvalue()
    if len(view) > settings.max_upload_bytes:
        raise IngestionError(message=f'PDF exceeds max upload size of {settings.max_upload_bytes} bytes')
    prefix = buffer.read(4)
    buffer.seek(0)
    if prefix != PDF_MAGIC:
        raise IngestionError(message='Invalid file type — PDF required', error_code='INVALID_FILE_TYPE', status_code=415)


async def ingest_from_sendgrid(form: FormData, settings: Settings) -> Tuple[io.BytesIO, Optional[str]]:
    """Extract the first PDF attachment from a SendGrid form payload."""
    sender = form.get('from') or form.get('sender')
    for _, value in form.multi_items():
        if isinstance(value, UploadFile) and _is_pdf_file(value):
            data = await value.read()
            buffer = io.BytesIO(data)
            validate_pdf_buffer(buffer, settings)
            return buffer, sender
    raise IngestionError(message='No PDF attachment found in SendGrid payload')


async def ingest_from_upload(file: UploadFile, settings: Settings) -> Tuple[io.BytesIO, Optional[str]]:
    """Read a direct upload into an in-memory PDF buffer."""
    if not _is_pdf_file(file):
        raise IngestionError(message='Uploaded file must be a PDF', error_code='INVALID_FILE_TYPE', status_code=415)
    data = await file.read()
    buffer = io.BytesIO(data)
    validate_pdf_buffer(buffer, settings)
    return buffer, None


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
