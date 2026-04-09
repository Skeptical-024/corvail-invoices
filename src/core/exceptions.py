from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from src.middleware.request_id import get_request_id


class CorvailInvoicesError(Exception):
    """Base exception for the Corvail Invoices API."""

    status_code: int = 500
    error_code: str = 'INTERNAL_ERROR'
    message: str = 'Unexpected internal error'

    def __init__(self, message: str | None = None, error_code: str | None = None, status_code: int | None = None) -> None:
        """Store API-safe error metadata."""
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.status_code = status_code or self.status_code
        super().__init__(self.message)


class IngestionError(CorvailInvoicesError):
    status_code = 400
    error_code = 'INGESTION_ERROR'
    message = 'Unable to ingest request payload'


class ExtractionError(CorvailInvoicesError):
    status_code = 502
    error_code = 'EXTRACTION_ERROR'
    message = 'Document extraction failed'


class ValidationError(CorvailInvoicesError):
    status_code = 422
    error_code = 'VALIDATION_ERROR'
    message = 'Document validation failed'


class EgressError(CorvailInvoicesError):
    status_code = 502
    error_code = 'EGRESS_ERROR'
    message = 'Failed to deliver payload'


class AuthenticationError(CorvailInvoicesError):
    status_code = 401
    error_code = 'AUTHENTICATION_ERROR'
    message = 'Invalid or missing API key'


def error_payload(code: str, message: str, product: str) -> dict[str, Any]:
    """Build the standard error response envelope."""
    return {
        'error': {
            'code': code,
            'message': message,
            'product': product,
            'request_id': get_request_id(),
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
    }


async def app_error_handler(request: Request, exc: CorvailInvoicesError) -> JSONResponse:
    """Return the standard error response for handled errors."""
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.error_code, exc.message, 'corvail-invoices'))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the standard error response for unhandled errors."""
    import logging
    import traceback

    logging.getLogger(__name__).error('[corvail-invoices] unhandled_exception | path=%s | request_id=%s\n%s', request.url.path, get_request_id(), traceback.format_exc())
    return JSONResponse(status_code=500, content=error_payload('INTERNAL_ERROR', 'Unexpected internal error', 'corvail-invoices'))
