import json
import logging
import time
from typing import Optional

import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.core.config import Settings

logger = logging.getLogger("corvail.invoices.alerts")


def _slack_color(level: str) -> str:
    return "#F97316" if level == "warning" else "#EF4444"


def _build_slack_payload(
    error_type: str,
    message: str,
    sender_email: Optional[str],
    invoice_number: Optional[str],
    level: str,
) -> dict:
    return {
        "attachments": [
            {
                "color": _slack_color(level),
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Corvail Invoices* — {error_type}",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Sender*\n{sender_email or 'unknown'}"},
                            {"type": "mrkdwn", "text": f"*Invoice*\n{invoice_number or 'unknown'}"},
                            {"type": "mrkdwn", "text": f"*Timestamp*\n{time.strftime('%Y-%m-%d %H:%M:%S')}"},
                        ],
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*Error*\n{message}"}},
                ],
            }
        ]
    }


async def send_slack_alert(
    settings: Settings,
    error_type: str,
    message: str,
    sender_email: Optional[str],
    invoice_number: Optional[str],
    level: str = "error",
) -> None:
    if not settings.slack_webhook_url:
        return

    payload = _build_slack_payload(error_type, message, sender_email, invoice_number, level)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(settings.slack_webhook_url, json=payload)
        logger.info("slack_alert status=%s", resp.status_code)
    except Exception as exc:
        logger.warning("slack_alert_failed error=%s", exc, exc_info=True)


def send_email_alert(
    settings: Settings,
    error_type: str,
    message: str,
    sender_email: Optional[str],
    invoice_number: Optional[str],
) -> None:
    if not settings.sendgrid_api_key or not settings.alert_email_from or not settings.alert_email_to:
        return

    subject = f"[Corvail Invoices] Processing Failed — {error_type}"
    body = {
        "product": "corvail-invoices",
        "error_type": error_type,
        "message": message,
        "sender_email": sender_email,
        "invoice_number": invoice_number,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    mail = Mail(
        from_email=settings.alert_email_from,
        to_emails=settings.alert_email_to,
        subject=subject,
        plain_text_content=json.dumps(body, indent=2),
    )
    try:
        client = SendGridAPIClient(settings.sendgrid_api_key)
        response = client.send(mail)
        logger.info("sendgrid_alert status=%s", response.status_code)
    except Exception as exc:
        logger.warning("sendgrid_alert_failed error=%s", exc, exc_info=True)


async def fire_alerts(
    settings: Settings,
    error_type: str,
    message: str,
    sender_email: Optional[str],
    invoice_number: Optional[str],
    level: str = "error",
) -> None:
    await send_slack_alert(settings, error_type, message, sender_email, invoice_number, level)
    send_email_alert(settings, error_type, message, sender_email, invoice_number)
