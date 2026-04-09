"""Security headers middleware for Corvail APIs."""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.middleware.request_id import get_request_id


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply security and version headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Attach response headers after downstream processing.

        Args:
            request: The inbound request.
            call_next: The downstream ASGI handler.

        Returns:
            The response with security headers attached.
        """
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Request-ID'] = get_request_id()
        response.headers['X-API-Version'] = '1.0.0'
        return response
