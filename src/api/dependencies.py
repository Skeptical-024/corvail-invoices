"""Dependency providers for the Corvail Invoices API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Request

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError


async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias='X-API-Key')) -> None:
    """Require a timing-safe API key match."""
    settings = get_settings()
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_secret):
        raise AuthenticationError()


async def verify_webhook_auth(x_api_key: Optional[str] = Header(default=None, alias='X-API-Key')) -> None:
    """Validate webhook auth unless inbound auth is disabled."""
    settings = get_settings()
    if settings.sendgrid_inbound_open:
        return
    await require_api_key(x_api_key)


async def verify_sendgrid_signature(request: Request) -> None:
    """Verify the SendGrid webhook signature when configured."""
    settings = get_settings()
    if settings.sendgrid_inbound_open:
        return
    webhook_key = getattr(settings, 'sendgrid_webhook_key', None)
    if not webhook_key:
        return
    signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature', '')
    timestamp = request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp', '')
    if not signature or not timestamp:
        raise HTTPException(status_code=403, detail='Missing webhook signature')
    body = await request.body()
    payload = timestamp.encode() + body
    expected = base64.b64encode(hmac.new(webhook_key.encode(), payload, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail='Invalid webhook signature')
