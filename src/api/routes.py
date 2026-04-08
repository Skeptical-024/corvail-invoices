import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, UploadFile
from fastapi.responses import JSONResponse

from src.api.dependencies import verify_webhook_auth
from src.core import AuthenticationError, CorvailInvoicesError
from src.core.config import Settings, get_settings
from src.models import InvoiceResponse, ProcessingStatus
from src.services import (
    deliver_to_erp,
    extract_invoice_data,
    fire_alerts,
    ingest_from_sendgrid,
    ingest_from_upload,
    validate_invoice,
    wipe_bytesio,
)

logger = logging.getLogger("corvail.invoices.routes")

router = APIRouter()


def _require_api_key(x_api_key: Optional[str], settings: Settings) -> None:
    if not x_api_key or x_api_key != settings.api_secret:
        raise AuthenticationError("Invalid API key")


def _error_response(
    exc: CorvailInvoicesError,
    sender_email: Optional[str],
    duration_ms: float,
) -> JSONResponse:
    payload = InvoiceResponse(
        status=ProcessingStatus.REJECTED,
        invoice=None,
        processing_time_ms=duration_ms,
        sender_email=sender_email,
        error=exc.message,
        warnings=[],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@router.post("/api/v1/webhooks/sendgrid")
async def sendgrid_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_webhook_auth),
):
    start = time.monotonic()
    buf = None
    sender_email = None
    try:
        form = await request.form()
        buf, sender_email = await ingest_from_sendgrid(form, settings)
        invoice, _ = extract_invoice_data(buf, settings)
        status, warnings = validate_invoice(invoice)
        response = InvoiceResponse(
            status=status,
            invoice=invoice,
            processing_time_ms=(time.monotonic() - start) * 1000,
            sender_email=sender_email,
            warnings=warnings,
            error=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await deliver_to_erp(response, settings)
        logger.info("pipeline_complete duration_ms=%.2f", response.processing_time_ms)
        return response
    except CorvailInvoicesError as exc:
        duration_ms = (time.monotonic() - start) * 1000
        await fire_alerts(
            settings,
            error_type=exc.error_code,
            message=exc.message,
            sender_email=sender_email,
            invoice_number=None,
            level="error",
        )
        logger.error("pipeline_error code=%s message=%s", exc.error_code, exc.message)
        return _error_response(exc, sender_email, duration_ms)
    finally:
        if buf is not None:
            wipe_bytesio(buf)


@router.post("/api/v1/invoices/analyze")
async def analyze_invoice(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    start = time.monotonic()
    buf = None
    try:
        _require_api_key(x_api_key, settings)
        buf, _ = await ingest_from_upload(file, settings)
        invoice, _ = extract_invoice_data(buf, settings)
        status, warnings = validate_invoice(invoice)
        response = InvoiceResponse(
            status=status,
            invoice=invoice,
            processing_time_ms=(time.monotonic() - start) * 1000,
            sender_email=None,
            warnings=warnings,
            error=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await deliver_to_erp(response, settings)
        logger.info("pipeline_complete duration_ms=%.2f", response.processing_time_ms)
        return response
    except CorvailInvoicesError as exc:
        duration_ms = (time.monotonic() - start) * 1000
        await fire_alerts(
            settings,
            error_type=exc.error_code,
            message=exc.message,
            sender_email=None,
            invoice_number=None,
            level="error",
        )
        logger.error("pipeline_error code=%s message=%s", exc.error_code, exc.message)
        return _error_response(exc, None, duration_ms)
    finally:
        if buf is not None:
            wipe_bytesio(buf)


@router.get("/healthz")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "version": "1.0.0",
        "product": "corvail-invoices",
        "environment": settings.environment,
    }
