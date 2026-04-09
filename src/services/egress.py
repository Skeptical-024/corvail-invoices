from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.core.config import Settings
from src.core.exceptions import EgressError
from src.middleware.request_id import get_request_id
from src.models import InvoiceResponse

logger = logging.getLogger(__name__)
_client: Optional[httpx.AsyncClient] = None


async def startup_http_client() -> None:
    """Create the shared outbound HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15.0, limits=httpx.Limits(max_connections=10))


async def shutdown_http_client() -> None:
    """Close the shared outbound HTTP client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_http_client() -> httpx.AsyncClient:
    """Return the shared outbound HTTP client."""
    if _client is None:
        raise RuntimeError('HTTP client not initialised')
    return _client


async def deliver_to_erp(payload: InvoiceResponse, settings: Settings) -> None:
    """POST successful invoice payloads to the configured webhook."""
    if not settings.erp_webhook_url:
        return
    client = get_http_client()
    response = await client.post(settings.erp_webhook_url, json=payload.model_dump(mode='json'), headers={'X-Source': 'corvail-invoices-api', 'X-Request-ID': get_request_id()})
    if response.is_error:
        raise EgressError(message='ERP delivery failed')
    logger.info('[corvail-invoices] egress_ok | request_id=%s', get_request_id())
