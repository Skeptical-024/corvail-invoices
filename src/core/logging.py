"""Structured JSON logging for Corvail APIs."""
from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Optional

request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
product_name_var: ContextVar[Optional[str]] = ContextVar('product_name', default=None)


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to JSON.

        Args:
            record: The logging record to format.

        Returns:
            The serialized JSON log line.
        """
        log_data = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(record.created)),
            'level': record.levelname,
            'product': product_name_var.get() or 'corvail',
            'request_id': request_id_var.get(),
            'logger': record.name,
            'msg': record.getMessage(),
        }
        if record.exc_info:
            log_data['exc'] = self.formatException(record.exc_info)
        extra_payload = getattr(record, 'extra', None)
        if isinstance(extra_payload, dict):
            log_data.update(extra_payload)
        return json.dumps(log_data, default=str)


def setup_logging(product: str, level: str = 'INFO') -> None:
    """Configure JSON structured logging for the application.

    Args:
        product: The product identifier written to every log line.
        level: The desired root log level.

    Returns:
        None.
    """
    product_name_var.set(product)
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger('uvicorn.access').handlers.clear()
    logging.getLogger('uvicorn.access').propagate = False
