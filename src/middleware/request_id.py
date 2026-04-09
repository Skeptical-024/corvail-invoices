from __future__ import annotations

import contextvars
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')


def get_request_id() -> str:
    """Return the request ID for the current context."""
    return _request_id.get('')


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request ID to the request context and response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Create a request ID for each inbound request."""
        request_id = str(uuid.uuid4())
        token = _request_id.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers['X-Request-ID'] = request_id
        return response
