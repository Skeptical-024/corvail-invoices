"""Request ID middleware for Corvail APIs."""
from __future__ import annotations

import contextvars
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import request_id_var

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')


def get_request_id() -> str:
    """Return the current request ID.

    Returns:
        The active request ID, or an empty string when absent.
    """
    return _request_id.get('')


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request ID to each inbound request."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Create and propagate a request ID.

        Args:
            request: The inbound request.
            call_next: The downstream ASGI handler.

        Returns:
            The downstream response with the request ID header set.
        """
        request_id = str(uuid.uuid4())
        token = _request_id.set(request_id)
        logging_token = request_id_var.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
            request_id_var.reset(logging_token)
        response.headers['X-Request-ID'] = request_id
        return response
