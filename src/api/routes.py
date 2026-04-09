"""API routes for the Corvail Invoices service."""
from __future__ import annotations

import io
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile

from src.api.dependencies import require_api_key, verify_sendgrid_signature, verify_webhook_auth
from src.core import CorvailInvoicesError
from src.core.config import Settings, get_settings
from src.middleware.request_id import get_request_id
from src.models import InvoiceData, InvoiceResponse, ProcessingStatus
from src.services.alerts import fire_alerts
from src.services.egress import deliver_to_webhook
from src.services.extraction import extract_invoice_data
from src.services.idempotency import idempotency_store
from src.services.ingestion import ingest_from_sendgrid, ingest_from_upload, wipe_bytesio
from src.services.metrics import metrics
from src.services.validation import validate_invoice

logger = logging.getLogger(__name__)
router = APIRouter()


def _set_timing_headers(response: Response, duration_ms: float) -> None:
    """Attach processing headers to the outgoing response."""
    response.headers['X-Processing-Time-Ms'] = str(round(duration_ms, 2))


def _build_response(status: ProcessingStatus, invoice: Optional[InvoiceData], sender_email: Optional[str], warnings: List[str], error: Optional[str], timings: Dict[str, float]) -> InvoiceResponse:
    """Build the standard invoices API response payload."""
    return InvoiceResponse(
        status=status,
        invoice=invoice,
        processing_time_ms=timings['total_ms'],
        sender_email=sender_email,
        warnings=warnings,
        error=error,
        timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        request_id=get_request_id() or None,
        pipeline_timings=timings,
    )


async def process_single_document(file_bytes: bytes, sender_email: Optional[str], request_id: str, settings: Settings) -> InvoiceResponse:
    """Process one invoice document with per-stage telemetry."""
    timings: Dict[str, float] = {}
    total_start = time.monotonic()
    buffer: Optional[io.BytesIO] = None
    try:
        t = time.monotonic()
        buffer = io.BytesIO(file_bytes)
        timings['ingestion_ms'] = round((time.monotonic() - t) * 1000, 2)

        t = time.monotonic()
        invoice, _ = await extract_invoice_data(buffer, settings)
        timings['extraction_ms'] = round((time.monotonic() - t) * 1000, 2)

        t = time.monotonic()
        status, warnings, error = validate_invoice(invoice, settings)
        timings['validation_ms'] = round((time.monotonic() - t) * 1000, 2)

        timings['egress_enqueue_ms'] = 0.0
        response = _build_response(status, invoice, sender_email, warnings, error, timings)
        if status is not ProcessingStatus.REJECTED:
            t = time.monotonic()
            await deliver_to_webhook(response.model_dump(mode='json'), settings, request_id=request_id)
            timings['egress_enqueue_ms'] = round((time.monotonic() - t) * 1000, 2)
        timings['total_ms'] = round((time.monotonic() - total_start) * 1000, 2)
        response.pipeline_timings = timings
        response.processing_time_ms = timings['total_ms']
        logger.info('pipeline_complete', extra={'extra': {'timings': timings, 'request_id': request_id}})
        return response
    finally:
        wipe_bytesio(buffer)


@router.get('/healthz', tags=['Health'])
async def health_check(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return the service health with dependency probing."""
    checks: Dict[str, str] = {}
    overall = 'ok'
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get('https://generativelanguage.googleapis.com/')
        checks['gemini'] = 'ok' if response.status_code < 500 else 'degraded'
        if response.status_code >= 500:
            overall = 'degraded'
    except Exception:
        checks['gemini'] = 'unreachable'
        overall = 'degraded'
    if settings.erp_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.head(settings.erp_webhook_url)
            checks['erp_webhook'] = 'ok'
        except Exception:
            checks['erp_webhook'] = 'unreachable'
    else:
        checks['erp_webhook'] = 'not_configured'
    return {
        'status': overall,
        'product': 'corvail-invoices',
        'version': '1.0.0',
        'environment': settings.environment,
        'uptime_seconds': metrics.uptime_seconds(),
        'gemini_model': settings.gemini_model,
        'checks': checks,
    }


@router.get('/metrics', tags=['Health'])
async def metrics_endpoint() -> dict[str, Any]:
    """Return service metrics."""
    payload = metrics.to_dict()
    payload.update({'product': 'corvail-invoices', 'version': '1.0.0'})
    return payload


@router.post('/api/v1/webhooks/sendgrid', response_model=InvoiceResponse, tags=['Processing'])
async def sendgrid_webhook(request: Request, response: Response, settings: Settings = Depends(get_settings), _auth: None = Depends(verify_webhook_auth), _signature: None = Depends(verify_sendgrid_signature)) -> InvoiceResponse:
    """Process an invoice delivered by SendGrid."""
    started = time.perf_counter()
    sender_email: Optional[str] = None
    invoice_number: Optional[str] = None
    status_code = 200
    try:
        form = await request.form()
        sender_email, _filename, file_bytes = await ingest_from_sendgrid(form, settings)
        cache_key = idempotency_store.make_key(sender_email or '', file_bytes)
        cached = idempotency_store.get(cache_key)
        if cached is not None:
            response.headers['X-Idempotent-Replay'] = 'true'
            cached_model = InvoiceResponse.model_validate(cached)
            if cached_model.status is ProcessingStatus.REJECTED:
                metrics.requests_rejected += 1
            else:
                metrics.requests_success += 1
            return cached_model
        payload = await process_single_document(file_bytes, sender_email, get_request_id(), settings)
        invoice_number = payload.invoice.invoice_number if payload.invoice else None
        if payload.status is ProcessingStatus.REJECTED:
            metrics.requests_rejected += 1
            await fire_alerts(settings, 'VALIDATION_REJECTED', payload.error or 'Invoice rejected', sender_email, invoice_number)
        else:
            metrics.requests_success += 1
        idempotency_store.set(cache_key, payload.model_dump(mode='json'))
        return payload
    except CorvailInvoicesError as exc:
        status_code = exc.status_code
        if exc.status_code < 500:
            metrics.requests_rejected += 1
        else:
            metrics.requests_failed += 1
        await fire_alerts(settings, exc.error_code, exc.message, sender_email, invoice_number)
        raise
    except Exception:
        status_code = 500
        metrics.requests_failed += 1
        await fire_alerts(settings, 'INTERNAL_ERROR', 'Unexpected pipeline failure', sender_email, invoice_number)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.requests_total += 1
        metrics.total_processing_ms += duration_ms
        request.state.processing_time_ms = duration_ms
        _set_timing_headers(response, duration_ms)
        logger.info('request_complete', extra={'extra': {'path': request.url.path, 'method': request.method, 'status': status_code, 'duration_ms': duration_ms, 'request_id': get_request_id()}})


@router.post('/api/v1/invoices/analyze', response_model=InvoiceResponse, tags=['Processing'])
async def analyze_invoice(request: Request, response: Response, file: UploadFile = File(...), settings: Settings = Depends(get_settings), _auth: None = Depends(require_api_key)) -> InvoiceResponse:
    """Process a directly uploaded invoice PDF."""
    started = time.perf_counter()
    invoice_number: Optional[str] = None
    status_code = 200
    try:
        _filename, file_bytes = await ingest_from_upload(file, settings)
        payload = await process_single_document(file_bytes, None, get_request_id(), settings)
        invoice_number = payload.invoice.invoice_number if payload.invoice else None
        if payload.status is ProcessingStatus.REJECTED:
            metrics.requests_rejected += 1
            await fire_alerts(settings, 'VALIDATION_REJECTED', payload.error or 'Invoice rejected', None, invoice_number)
        else:
            metrics.requests_success += 1
        return payload
    except CorvailInvoicesError as exc:
        status_code = exc.status_code
        if exc.status_code < 500:
            metrics.requests_rejected += 1
        else:
            metrics.requests_failed += 1
        await fire_alerts(settings, exc.error_code, exc.message, None, invoice_number)
        raise
    except Exception:
        status_code = 500
        metrics.requests_failed += 1
        await fire_alerts(settings, 'INTERNAL_ERROR', 'Unexpected pipeline failure', None, invoice_number)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.requests_total += 1
        metrics.total_processing_ms += duration_ms
        request.state.processing_time_ms = duration_ms
        _set_timing_headers(response, duration_ms)
        logger.info('request_complete', extra={'extra': {'path': request.url.path, 'method': request.method, 'status': status_code, 'duration_ms': duration_ms, 'request_id': get_request_id()}})


@router.post('/api/v1/invoices/batch', tags=['Processing'])
async def batch_analyze(request: Request, response: Response, files: List[UploadFile] = File(...), settings: Settings = Depends(get_settings), _auth: None = Depends(require_api_key)) -> dict[str, Any]:
    """Process multiple invoice documents in one request."""
    started = time.perf_counter()
    status_code = 200
    try:
        if len(files) > 10:
            raise HTTPException(status_code=400, detail={'code': 'BATCH_TOO_LARGE', 'message': 'Maximum 10 documents per batch request'})
        results: List[dict[str, Any]] = []
        for file in files:
            try:
                _filename, file_bytes = await ingest_from_upload(file, settings)
                result = await process_single_document(file_bytes, None, get_request_id(), settings)
                results.append(result.model_dump(mode='json'))
            except Exception as exc:
                results.append({'status': 'error', 'filename': file.filename, 'error': str(exc)})
        successes = sum(1 for item in results if item.get('status') not in {'STATUS_REJECTED', 'error'})
        rejections = sum(1 for item in results if item.get('status') == 'STATUS_REJECTED')
        metrics.requests_success += successes
        metrics.requests_rejected += rejections
        if any(item.get('status') == 'error' for item in results):
            metrics.requests_failed += 1
        return {'product': 'corvail-invoices', 'batch_size': len(files), 'results': results, 'timestamp': datetime.utcnow().isoformat() + 'Z'}
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics.requests_total += 1
        metrics.total_processing_ms += duration_ms
        request.state.processing_time_ms = duration_ms
        _set_timing_headers(response, duration_ms)
        logger.info('request_complete', extra={'extra': {'path': request.url.path, 'method': request.method, 'status': status_code, 'duration_ms': duration_ms, 'request_id': get_request_id()}})
