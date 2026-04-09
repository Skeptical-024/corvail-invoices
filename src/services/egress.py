"""Webhook delivery helpers for the Corvail Invoices API."""
from __future__ import annotations

import logging
from typing import Optional

from src.core.config import Settings
from src.services.webhook_queue import WebhookJob, webhook_queue

logger = logging.getLogger(__name__)


async def deliver_to_webhook(payload: dict, settings: Settings, request_id: Optional[str] = None) -> None:
    """Enqueue a processed invoice payload for downstream delivery."""
    if not settings.erp_webhook_url:
        logger.warning('webhook_not_configured')
        return
    invoice = payload.get('invoice') or {}
    vendor = invoice.get('vendor') or {}
    headers = {
        'X-Source': 'corvail-invoices-api',
        'X-Invoice-Number': invoice.get('invoice_number') or '',
        'X-Vendor': vendor.get('name') or '',
        'X-Line-Items': str(len(invoice.get('line_items') or [])),
    }
    await webhook_queue.enqueue(WebhookJob(url=settings.erp_webhook_url, payload=payload, headers=headers, product='corvail-invoices', request_id=request_id))
