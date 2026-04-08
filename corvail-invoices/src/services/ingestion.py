import io
import logging
from typing import Optional, Tuple

from fastapi import UploadFile
from starlette.datastructures import FormData

from src.core import IngestionError
from src.core.config import Settings

logger = logging.getLogger("corvail.invoices.ingestion")

PDF_MAGIC = b"%PDF"


def _log_form_fields(form: FormData) -> None:
    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            logger.info(
                "sendgrid_field file=%s filename=%s content_type=%s",
                key,
                value.filename,
                value.content_type,
            )
        else:
            logger.info("sendgrid_field key=%s value=%s", key, value)


def _is_pdf_file(upload: UploadFile) -> bool:
    if upload.content_type and "pdf" in upload.content_type.lower():
        return True
    if upload.filename and upload.filename.lower().endswith(".pdf"):
        return True
    return False


def _validate_pdf_bytes(data: bytes, settings: Settings) -> None:
    if len(data) > settings.max_upload_bytes:
        raise IngestionError(f"PDF exceeds max upload size of {settings.max_upload_bytes} bytes")
    if not data.startswith(PDF_MAGIC):
        raise IngestionError("Uploaded file is not a valid PDF")


def _to_bytesio(data: bytes) -> io.BytesIO:
    buf = io.BytesIO()
    buf.write(data)
    buf.seek(0)
    return buf


def _wipe_bytes(data: bytearray) -> None:
    for i in range(len(data)):
        data[i] = 0


async def ingest_from_sendgrid(form: FormData, settings: Settings) -> Tuple[io.BytesIO, Optional[str]]:
    _log_form_fields(form)
    sender = form.get("from") or form.get("sender")

    candidate_files: list[UploadFile] = []
    for _, value in form.multi_items():
        if isinstance(value, UploadFile) and _is_pdf_file(value):
            candidate_files.append(value)

    if not candidate_files:
        raise IngestionError("No PDF attachment found in SendGrid payload")

    file = candidate_files[0]
    data = await file.read()
    data_bytes = bytearray(data)
    _validate_pdf_bytes(data, settings)
    buf = _to_bytesio(data)
    _wipe_bytes(data_bytes)
    return buf, sender


async def ingest_from_upload(file: UploadFile, settings: Settings) -> Tuple[io.BytesIO, Optional[str]]:
    if not _is_pdf_file(file):
        raise IngestionError("Uploaded file must be a PDF")

    data = await file.read()
    data_bytes = bytearray(data)
    _validate_pdf_bytes(data, settings)
    buf = _to_bytesio(data)
    _wipe_bytes(data_bytes)
    return buf, None


def wipe_bytesio(buf: io.BytesIO) -> None:
    try:
        view = buf.getbuffer()
        view[:] = b"\x00" * len(view)
        view.release()
    except Exception:
        logger.warning("Failed to wipe buffer", exc_info=True)
    finally:
        try:
            buf.close()
        except Exception:
            logger.warning("Failed to close buffer", exc_info=True)
