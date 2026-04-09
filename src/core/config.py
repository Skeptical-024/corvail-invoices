from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load runtime settings from environment variables."""

    gemini_api_key: str
    gemini_model: str = 'gemini-2.5-flash'
    api_secret: str
    erp_webhook_url: Optional[str] = None
    max_upload_bytes: int = 20 * 1024 * 1024
    sendgrid_inbound_open: bool = False
    slack_webhook_url: Optional[str] = None
    sendgrid_api_key: Optional[str] = None
    alert_email_from: Optional[str] = None
    alert_email_to: Optional[str] = None
    environment: str = 'production'
    log_level: str = 'INFO'

    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
