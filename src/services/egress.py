from typing import Optional
import logging
import time

import httpx

from src.core.config import Settings
from src.models import InvoiceResponse

logger = logging.getLogger("corvail.invoices.egress")


async def deliver_to_erp(payload: InvoiceResponse, settings: Settings) -> None:
    if not settings.erp_webhook_url:
        logger.warning("ERP webhook URL not configured; skipping delivery")
        return

    headers = {
        "Content-Type": "application/json",
        "X-Source": "corvail-invoices-api",
        "X-Invoice-Number": payload.invoice.invoice_number if payload.invoice else "",
        "X-Vendor": payload.invoice.vendor.name if payload.invoice and payload.invoice.vendor else "",
        "X-Total": str(payload.invoice.total_amount) if payload.invoice else "",
        "X-Currency": payload.invoice.currency if payload.invoice else "",
    }

    timeout = httpx.Timeout(15.0)
    for attempt in range(1, 3):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    settings.erp_webhook_url,
                    json=payload.model_dump(),
                    headers=headers,
                )
            duration = (time.monotonic() - start) * 1000
            logger.info(
                "erp_delivery status=%s duration_ms=%.2f",
                response.status_code,
                duration,
            )
            return
        except httpx.TimeoutException as exc:
            duration = (time.monotonic() - start) * 1000
            logger.warning("erp_timeout attempt=%s duration_ms=%.2f error=%s", attempt, duration, exc)
            if attempt == 2:
                return
        except Exception as exc:
            logger.error("erp_delivery_failed error=%s", exc, exc_info=True)
            return
