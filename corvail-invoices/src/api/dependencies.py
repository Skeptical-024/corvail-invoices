from typing import Optional
import secrets

from fastapi import Depends, Header

from src.core import AuthenticationError
from src.core.config import Settings, get_settings


def verify_webhook_auth(
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    if settings.sendgrid_inbound_open:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_secret):
        raise AuthenticationError("Invalid API key")
