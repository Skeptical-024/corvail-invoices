"""In-memory idempotency store for preventing duplicate document processing."""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional, Tuple


class IdempotencyStore:
    """Simple TTL-based in-memory idempotency store."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        """Initialize the idempotency store.

        Args:
            ttl_seconds: Maximum lifetime of a cached response.
        """
        self._store: Dict[str, Tuple[float, dict]] = {}
        self.ttl = ttl_seconds

    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [key for key, (ts, _) in self._store.items() if now - ts > self.ttl]
        for key in expired:
            del self._store[key]

    def get(self, key: str) -> Optional[dict]:
        """Return a cached result if the key is still fresh.

        Args:
            key: The idempotency key.

        Returns:
            The cached result when present, otherwise None.
        """
        if key in self._store:
            ts, result = self._store[key]
            if time.time() - ts <= self.ttl:
                return result
            del self._store[key]
        return None

    def set(self, key: str, result: dict) -> None:
        """Cache a result for this key.

        Args:
            key: The idempotency key.
            result: The serialized response payload.

        Returns:
            None.
        """
        self._cleanup()
        self._store[key] = (time.time(), result)

    def make_key(self, sender_email: str, file_bytes: bytes) -> str:
        """Generate an idempotency key from sender and file content.

        Args:
            sender_email: The normalized sender email address.
            file_bytes: The uploaded PDF bytes.

        Returns:
            The deterministic idempotency key.
        """
        content = f'{sender_email}:{hashlib.sha256(file_bytes).hexdigest()}'
        return hashlib.sha256(content.encode()).hexdigest()


idempotency_store = IdempotencyStore(ttl_seconds=3600)
