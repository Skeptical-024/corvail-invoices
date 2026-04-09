from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Header

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError


async def verify_webhook_auth(x_api_key: Optional[str] = Header(default=None, alias='X-API-Key')) -> None:
    """Validate webhook auth unless inbound auth is disabled."""
    settings = get_settings()
    if settings.sendgrid_inbound_open:
        return
    await require_api_key(x_api_key)


async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias='X-API-Key')) -> None:
    """Require a timing-safe API key match."""
    settings = get_settings()
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_secret):
        raise AuthenticationError()
