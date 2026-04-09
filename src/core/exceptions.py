"""Exception types and error handlers for the Corvail Invoices API."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.middleware.request_id import get_request_id

logger = logging.getLogger(__name__)
PRODUCT_NAME = 'corvail-invoices'


class CorvailInvoicesError(Exception):
    """Base exception for the Corvail Invoices API."""

    status_code: int = 500
    error_code: str = 'INTERNAL_ERROR'
    message: str = 'Unexpected internal error'

    def __init__(self, message: str | None = None, error_code: str | None = None, status_code: int | None = None) -> None:
        """Store API-safe error metadata.

        Args:
            message: A client-safe error message.
            error_code: A stable machine-readable error code.
            status_code: The HTTP status code to return.
        """
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


class UnsupportedFileTypeError(CorvailInvoicesError):
    status_code = 415
    error_code = 'INVALID_FILE_TYPE'
    message = 'Invalid file type — PDF required'


class FileTooLargeError(CorvailInvoicesError):
    status_code = 413
    error_code = 'FILE_TOO_LARGE'
    message = 'Uploaded file exceeds size limit'


def error_payload(code: str, message: str, product: str = PRODUCT_NAME) -> dict[str, Any]:
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
    """Render handled application exceptions."""
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.error_code, exc.message))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Render FastAPI HTTP exceptions with the standard envelope."""
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get('code', 'HTTP_ERROR')
        message = detail.get('message', 'Request failed')
    else:
        code = 'HTTP_ERROR'
        message = str(detail)
    return JSONResponse(status_code=exc.status_code, content=error_payload(code, message))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render unhandled exceptions with the standard envelope."""
    logger.error('unhandled_exception', extra={'extra': {'path': request.url.path, 'exc': traceback.format_exc()}})
    return JSONResponse(status_code=500, content=error_payload('INTERNAL_ERROR', 'Unexpected internal error'))
