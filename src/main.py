"""FastAPI application entrypoint for Corvail Invoices."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from src.api.routes import router
from src.core.config import Settings, get_settings
from src.core.exceptions import CorvailInvoicesError, app_error_handler, http_exception_handler, unhandled_error_handler
from src.core.logging import setup_logging
from src.middleware.rate_limiter import RateLimiterMiddleware
from src.middleware.request_id import RequestIdMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.services.webhook_queue import webhook_queue

settings = get_settings()
logger = logging.getLogger(__name__)


async def validate_environment(settings: Settings) -> None:
    """Validate critical environment variables on startup."""
    errors = []
    warnings = []
    if not settings.gemini_api_key:
        errors.append('GEMINI_API_KEY is required')
    if not settings.api_secret:
        errors.append('API_SECRET is required')
    if len(settings.api_secret or '') < 32:
        warnings.append('API_SECRET is short — recommend 32+ character random string')
    if not settings.erp_webhook_url:
        warnings.append('ERP_WEBHOOK_URL not set — processed documents will not be forwarded')
    if not settings.slack_webhook_url:
        warnings.append('SLACK_WEBHOOK_URL not set — Slack alerts disabled')
    for warning in warnings:
        logger.warning('config_warning', extra={'extra': {'warning': warning}})
    if errors:
        for error in errors:
            logger.error('config_error', extra={'extra': {'error': error}})
        raise RuntimeError(f'Startup failed due to missing required config: {errors}')


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown resources."""
    setup_logging(product='corvail-invoices', level=settings.log_level)
    await validate_environment(settings)
    await webhook_queue.start()
    logger.info('[Corvail Invoices] API online. Model: %s. Environment: %s.', settings.gemini_model, settings.environment)
    yield
    await webhook_queue.stop()
    logger.info('shutdown_complete')


app = FastAPI(
    title='Corvail Invoices API',
    description="""
## Corvail Invoices

AI-powered supplier invoice extraction and validation.

### Authentication
All processing endpoints require an `X-API-Key` header.

### Zero Retention
Documents are processed in memory. Nothing is written to disk or stored after the response is returned.

### Webhook Delivery
Processed documents are delivered to your configured `ERP_WEBHOOK_URL` asynchronously with retry logic.

### Rate Limiting
60 requests per minute per IP address. Exceeded requests return HTTP 429.
    """,
    version='1.0.0',
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_tags=[
        {'name': 'Processing', 'description': 'Document processing endpoints'},
        {'name': 'Health', 'description': 'Health check and metrics endpoints'},
    ],
    contact={'name': 'Corvail Support', 'email': 'hello@corvail.one', 'url': 'https://corvail.one'},
    license_info={'name': 'Proprietary', 'url': 'https://corvail.one/terms.html'},
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['*'])
app.include_router(router)
app.add_exception_handler(CorvailInvoicesError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
