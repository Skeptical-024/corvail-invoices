from __future__ import annotations

import logging
import time
from collections import deque
from typing import Awaitable, Callable, Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.middleware.request_id import get_request_id
from src.services.metrics import metrics

logger = logging.getLogger(__name__)
_RATE_LIMIT = 60
_WINDOW_SECONDS = 60
_ip_buckets: Dict[str, Deque[float]] = {}


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Enforce a sliding-window rate limit per client IP."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Limit requests to 60 per minute per IP."""
        client_ip = request.client.host if request.client else 'unknown'
        now = time.time()
        bucket = _ip_buckets.setdefault(client_ip, deque())
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT:
            metrics.rate_limit_hits += 1
            logger.warning('[corvail-invoices] rate_limit_hit | ip=%s | endpoint=%s | request_id=%s', client_ip, request.url.path, get_request_id())
            return JSONResponse(
                status_code=429,
                content={
                    'error': {
                        'code': 'RATE_LIMIT_EXCEEDED',
                        'message': 'Too many requests. Please retry after 60 seconds.',
                        'product': 'corvail-invoices',
                        'request_id': get_request_id(),
                        'timestamp': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat().replace('+00:00', 'Z'),
                    }
                },
                headers={
                    'Retry-After': '60',
                    'X-RateLimit-Limit': '60',
                    'X-RateLimit-Remaining': '0',
                },
            )
        bucket.append(now)
        response = await call_next(request)
        remaining = max(_RATE_LIMIT - len(bucket), 0)
        response.headers['X-RateLimit-Limit'] = '60'
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        return response
