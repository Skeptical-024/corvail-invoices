"""Background webhook delivery queue with exponential backoff retry."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookJob:
    """A pending webhook delivery job."""

    url: str
    payload: dict
    headers: dict
    attempt: int = 0
    max_attempts: int = 3
    product: str = 'corvail'
    request_id: Optional[str] = None


class WebhookQueue:
    """Async background queue for webhook delivery."""

    def __init__(self) -> None:
        """Initialize queue state."""
        self._queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background worker."""
        self._queue = asyncio.Queue(maxsize=1000)
        self._worker_task = asyncio.create_task(self._worker())
        logger.info('webhook_queue_started')

    async def stop(self) -> None:
        """Stop the background worker."""
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info('webhook_queue_stopped')

    async def enqueue(self, job: WebhookJob) -> None:
        """Add a webhook delivery job to the queue.

        Args:
            job: The webhook job to enqueue.

        Returns:
            None.
        """
        if self._queue is None:
            logger.error('webhook_queue_not_started', extra={'extra': {'url': job.url}})
            return
        try:
            self._queue.put_nowait(job)
            logger.info('webhook_enqueued', extra={'extra': {'url': job.url, 'request_id': job.request_id}})
        except asyncio.QueueFull:
            logger.error('webhook_queue_full', extra={'extra': {'url': job.url, 'request_id': job.request_id}})

    async def _worker(self) -> None:
        """Process jobs from the queue with retry logic."""
        assert self._queue is not None
        while True:
            try:
                job = await self._queue.get()
                await self._deliver(job)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception('webhook_worker_error')

    async def _deliver(self, job: WebhookJob) -> None:
        """Attempt webhook delivery with exponential backoff.

        Args:
            job: The pending webhook job.

        Returns:
            None.
        """
        backoff = [0, 2, 8]
        for attempt in range(job.max_attempts):
            if attempt > 0:
                await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(job.url, json=job.payload, headers=job.headers)
                if response.status_code < 300:
                    logger.info('webhook_delivered', extra={'extra': {'url': job.url, 'attempt': attempt + 1, 'status': response.status_code, 'request_id': job.request_id}})
                    return
                logger.warning('webhook_non_2xx', extra={'extra': {'url': job.url, 'attempt': attempt + 1, 'status': response.status_code, 'request_id': job.request_id}})
            except Exception as exc:
                logger.warning('webhook_attempt_failed', extra={'extra': {'url': job.url, 'attempt': attempt + 1, 'error': str(exc), 'request_id': job.request_id}})
        logger.error('webhook_delivery_failed', extra={'extra': {'url': job.url, 'max_attempts': job.max_attempts, 'request_id': job.request_id}})


webhook_queue = WebhookQueue()
