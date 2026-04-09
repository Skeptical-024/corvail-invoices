from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from src.api.routes import router
from src.core.exceptions import CorvailInvoicesError, app_error_handler, unhandled_error_handler
from src.core.config import get_settings
from src.middleware.rate_limiter import RateLimiterMiddleware
from src.middleware.request_id import RequestIdMiddleware, get_request_id
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.services.egress import shutdown_http_client, startup_http_client

settings = get_settings()


class RequestIdFilter(logging.Filter):
    """Inject the current request ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach request_id to every log record."""
        record.request_id = get_request_id() or '-'
        return True


def _configure_logging() -> None:
    """Configure application logging with request IDs."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s request_id=%(request_id)s %(message)s'))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown resources."""
    _configure_logging()
    await startup_http_client()
    logging.getLogger(__name__).info('[corvail-invoices] startup | model=%s | environment=%s', settings.gemini_model, settings.environment)
    yield
    await shutdown_http_client()
    logging.getLogger(__name__).info('[corvail-invoices] shutdown')


app = FastAPI(
    title='Corvail Invoices API',
    description='AI-powered invoice processing. Zero data retention. Production-grade.',
    version='1.0.0',
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_tags=[
        {'name': 'Processing', 'description': 'Document processing endpoints'},
        {'name': 'Health', 'description': 'Health and metrics endpoints'},
    ],
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['GET', 'POST'], allow_headers=['*'])
app.include_router(router)
app.add_exception_handler(CorvailInvoicesError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
