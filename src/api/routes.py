from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile

from src.api.dependencies import require_api_key, verify_webhook_auth
from src.core import CorvailInvoicesError
from src.core.config import Settings, get_settings
from src.middleware.request_id import get_request_id
from src.models import InvoiceResponse, ProcessingStatus
from src.services.alerts import fire_alerts
from src.services.egress import deliver_to_erp
from src.services.extraction import extract_invoice_data
from src.services.ingestion import ingest_from_sendgrid, ingest_from_upload, wipe_bytesio
from src.services.metrics import metrics
from src.services.validation import validate_invoice

logger = logging.getLogger(__name__)
router = APIRouter()


def _set_timing_headers(response: Response, duration_ms: float) -> None:
    """Attach processing headers to the outgoing response."""
    response.headers['X-Processing-Time-Ms'] = str(round(duration_ms, 2))


@router.get('/healthz', tags=['Health'])
async def health(settings: Settings = Depends(get_settings)) -> dict:
    """Return a detailed health payload."""
    return {'status': 'ok', 'product': 'corvail-invoices', 'version': '1.0.0', 'environment': settings.environment, 'uptime_seconds': metrics.uptime_seconds(), 'gemini_model': settings.gemini_model}


@router.get('/metrics', tags=['Health'])
async def metrics_endpoint() -> dict:
    """Return process metrics without authentication."""
    payload = metrics.to_dict()
    payload.update({'product': 'corvail-invoices', 'version': '1.0.0'})
    return payload


@router.post('/api/v1/webhooks/sendgrid', response_model=InvoiceResponse, tags=['Processing'])
async def sendgrid_webhook(request: Request, response: Response, settings: Settings = Depends(get_settings), _auth: None = Depends(verify_webhook_auth)) -> InvoiceResponse:
    """Process an invoice delivered by SendGrid."""
    started = time.perf_counter()
    buf = None
    sender_email = None
    status_code = 200
    try:
        form = await request.form()
        buf, sender_email = await ingest_from_sendgrid(form, settings)
        invoice, _ = await extract_invoice_data(buf, settings)
        status, warnings = validate_invoice(invoice)
        payload = InvoiceResponse(status=status, invoice=invoice, processing_time_ms=round((time.perf_counter() - started) * 1000, 2), sender_email=sender_email, warnings=warnings, error=None, timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
        await deliver_to_erp(payload, settings)
        if status == ProcessingStatus.REJECTED:
            metrics.requests_rejected += 1
        else:
            metrics.requests_success += 1
        return payload
    except CorvailInvoicesError as exc:
        status_code = exc.status_code
        if exc.status_code < 500:
            metrics.requests_rejected += 1
        else:
            metrics.requests_failed += 1
        await fire_alerts(settings, exc.error_code, exc.message, sender_email, None)
        raise
    except Exception:
        status_code = 500
        metrics.requests_failed += 1
        await fire_alerts(settings, 'INTERNAL_ERROR', 'Unexpected pipeline failure', sender_email, None)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.requests_total += 1
        metrics.total_processing_ms += duration_ms
        request.state.processing_time_ms = duration_ms
        _set_timing_headers(response, duration_ms)
        logger.info('[corvail-invoices] request_complete | path=%s | method=%s | status=%s | duration_ms=%s | request_id=%s', request.url.path, request.method, status_code, duration_ms, get_request_id())
        wipe_bytesio(buf)


@router.post('/api/v1/invoices/analyze', response_model=InvoiceResponse, tags=['Processing'])
async def analyze_invoice(request: Request, response: Response, file: UploadFile = File(...), settings: Settings = Depends(get_settings), _auth: None = Depends(require_api_key)) -> InvoiceResponse:
    """Process a directly uploaded invoice PDF."""
    started = time.perf_counter()
    buf = None
    status_code = 200
    try:
        buf, _ = await ingest_from_upload(file, settings)
        invoice, _ = await extract_invoice_data(buf, settings)
        status, warnings = validate_invoice(invoice)
        payload = InvoiceResponse(status=status, invoice=invoice, processing_time_ms=round((time.perf_counter() - started) * 1000, 2), sender_email=None, warnings=warnings, error=None, timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
        await deliver_to_erp(payload, settings)
        if status == ProcessingStatus.REJECTED:
            metrics.requests_rejected += 1
        else:
            metrics.requests_success += 1
        return payload
    except CorvailInvoicesError as exc:
        status_code = exc.status_code
        if exc.status_code < 500:
            metrics.requests_rejected += 1
        else:
            metrics.requests_failed += 1
        await fire_alerts(settings, exc.error_code, exc.message, None, None)
        raise
    except Exception:
        status_code = 500
        metrics.requests_failed += 1
        await fire_alerts(settings, 'INTERNAL_ERROR', 'Unexpected pipeline failure', None, None)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.requests_total += 1
        metrics.total_processing_ms += duration_ms
        request.state.processing_time_ms = duration_ms
        _set_timing_headers(response, duration_ms)
        logger.info('[corvail-invoices] request_complete | path=%s | method=%s | status=%s | duration_ms=%s | request_id=%s', request.url.path, request.method, status_code, duration_ms, get_request_id())
        wipe_bytesio(buf)
