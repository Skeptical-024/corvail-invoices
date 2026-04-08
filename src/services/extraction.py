import base64
import json
import logging
import time
from typing import Optional, Tuple

from google import genai

from src.core import ExtractionError
from src.core.config import Settings
from src.models import InvoiceData

logger = logging.getLogger("corvail.invoices.extraction")

SYSTEM_PROMPT = (
    "You are a precise invoice data extraction system. Extract every field from "
    "this supplier invoice PDF and return ONLY valid JSON matching the schema provided. "
    "Be conservative — return null for any field you cannot find with confidence. "
    "For line_items, extract every single line item on the invoice including description, "
    "quantity, unit_price, and total. For math_errors, identify any discrepancy where line "
    "item totals do not sum to subtotal, or where subtotal + tax + shipping does not equal "
    "total_amount. Rate your confidence_score from 0.0 to 1.0 based on document quality "
    "and extraction completeness."
)


def _pdf_to_base64(pdf_bytes: bytes) -> str:
    return base64.b64encode(pdf_bytes).decode("utf-8")


def _wipe_bytes(data: bytearray) -> None:
    for i in range(len(data)):
        data[i] = 0


def extract_invoice_data(buf, settings: Settings) -> Tuple[InvoiceData, float]:
    client = genai.Client(api_key=settings.gemini_api_key)
    pdf_bytes = buf.getvalue()
    pdf_copy = bytearray(pdf_bytes)
    payload = _pdf_to_base64(pdf_bytes)
    _wipe_bytes(pdf_copy)

    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        start = time.monotonic()
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "application/pdf", "data": payload}}
                        ],
                    }
                ],
                system_instruction=SYSTEM_PROMPT,
                generation_config={"response_mime_type": "application/json"},
            )
            duration = (time.monotonic() - start) * 1000
            usage = getattr(response, "usage_metadata", None)
            tokens = getattr(usage, "total_token_count", None) if usage else None
            logger.info(
                "gemini_attempt=%s duration_ms=%.2f tokens=%s",
                attempt,
                duration,
                tokens,
            )
            if not response.text:
                raise ExtractionError("Gemini returned empty response")
            data = json.loads(response.text)
            invoice = InvoiceData.model_validate(data)
            return invoice, duration
        except Exception as exc:
            duration = (time.monotonic() - start) * 1000
            logger.warning(
                "gemini_failure attempt=%s duration_ms=%.2f error=%s",
                attempt,
                duration,
                exc,
            )
            last_error = exc
            time.sleep(2 ** (attempt - 1))

    raise ExtractionError(f"Gemini extraction failed after retries: {last_error}")
