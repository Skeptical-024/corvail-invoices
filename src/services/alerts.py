from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.core.config import Settings
from src.middleware.request_id import get_request_id

logger = logging.getLogger(__name__)


async def send_slack_alert(settings: Settings, error_type: str, message: str, sender_email: Optional[str], invoice_number: Optional[str]) -> None:
    """Send a Slack alert when configured."""
    if not settings.slack_webhook_url:
        return
    payload = {
        'text': f'Corvail Invoices failure\nrequest_id={get_request_id()}\nerror_type={error_type}\nmessage={message}\nsender={sender_email or "unknown"}\ninvoice={invoice_number or "unknown"}\ntime={datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}'
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(settings.slack_webhook_url, json=payload)
    except Exception:
        logger.exception('[corvail-invoices] alert_slack_failed | request_id=%s', get_request_id())


def send_email_alert(settings: Settings, error_type: str, message: str, sender_email: Optional[str], invoice_number: Optional[str]) -> None:
    """Send a SendGrid alert email when configured."""
    if not all([settings.sendgrid_api_key, settings.alert_email_from, settings.alert_email_to]):
        return
    try:
        client = SendGridAPIClient(settings.sendgrid_api_key)
        mail = Mail(
            from_email=settings.alert_email_from,
            to_emails=settings.alert_email_to,
            subject='[Corvail Invoices] Processing failure',
            plain_text_content=f'request_id={get_request_id()}\nerror_type={error_type}\nmessage={message}\nsender={sender_email or "unknown"}\ninvoice={invoice_number or "unknown"}',
        )
        client.send(mail)
    except Exception:
        logger.exception('[corvail-invoices] alert_email_failed | request_id=%s', get_request_id())


async def fire_alerts(settings: Settings, error_type: str, message: str, sender_email: Optional[str], invoice_number: Optional[str]) -> None:
    """Dispatch configured alerts for invoice failures."""
    await send_slack_alert(settings, error_type, message, sender_email, invoice_number)
    send_email_alert(settings, error_type, message, sender_email, invoice_number)
