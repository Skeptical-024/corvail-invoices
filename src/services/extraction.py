from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

from google import genai
from google.genai import types as genai_types

from src.core import ExtractionError
from src.core.config import Settings
from src.middleware.request_id import get_request_id
from src.models import InvoiceData
from src.services.metrics import metrics

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = 'You are a precise invoice data extraction system. Return only valid JSON for the supplied invoice PDF.'
_client: Optional[genai.Client] = None


def _get_client(settings: Settings) -> genai.Client:
    """Return the shared Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def _call_gemini(pdf_bytes: bytes, settings: Settings) -> Any:
    """Call Gemini with the configured invoice extraction prompt."""
    client = _get_client(settings)
    return await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[genai_types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf')],
        config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, response_mime_type='application/json', temperature=0.0),
    )


async def extract_invoice_data(buf: BytesIO, settings: Settings) -> Tuple[InvoiceData, float]:
    """Extract structured invoice data with retries, timeout, and logging."""
    pdf_bytes = buf.getvalue()
    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        started = time.perf_counter()
        metrics.gemini_calls_total += 1
        try:
            response = await asyncio.wait_for(_call_gemini(pdf_bytes, settings), timeout=30.0)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            usage = getattr(response, 'usage_metadata', None)
            input_tokens = getattr(usage, 'prompt_token_count', 0)
            output_tokens = getattr(usage, 'candidates_token_count', 0)
            logger.info('[corvail-invoices] gemini_call | attempt=%s | model=%s | duration_ms=%s | input_tokens=%s | output_tokens=%s | success=%s | request_id=%s', attempt, settings.gemini_model, duration_ms, input_tokens, output_tokens, True, get_request_id())
            metrics.gemini_total_ms += duration_ms
            data: Dict[str, Any] = json.loads(response.text or '{}')
            return InvoiceData.model_validate(data), duration_ms
        except asyncio.TimeoutError:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            metrics.gemini_calls_failed += 1
            metrics.gemini_total_ms += duration_ms
            logger.error('[corvail-invoices] gemini_timeout | attempt=%s | model=%s | duration_ms=%s | request_id=%s', attempt, settings.gemini_model, duration_ms, get_request_id())
            last_error = ExtractionError(message='Document processing timed out — please try again', error_code='GEMINI_TIMEOUT')
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            metrics.gemini_calls_failed += 1
            metrics.gemini_total_ms += duration_ms
            logger.warning('[corvail-invoices] gemini_call | attempt=%s | model=%s | duration_ms=%s | input_tokens=%s | output_tokens=%s | success=%s | request_id=%s', attempt, settings.gemini_model, duration_ms, 0, 0, False, get_request_id())
            last_error = exc
        if attempt < 3:
            wait_seconds = random.uniform(1.0, 2.0) if attempt == 1 else random.uniform(2.0, 4.0)
            logger.info('[corvail-invoices] gemini_retry | attempt=%s | wait_seconds=%.2f | request_id=%s', attempt + 1, wait_seconds, get_request_id())
            await asyncio.sleep(wait_seconds)
    if isinstance(last_error, ExtractionError):
        raise last_error
    raise ExtractionError(message='Gemini extraction failed after retries')
