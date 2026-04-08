import datetime as dt
import logging
from typing import Optional, List, Tuple

from src.core import ValidationError
from src.models import InvoiceData, MathError, ProcessingStatus

logger = logging.getLogger("corvail.invoices.validation")


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _approx_equal(expected: float, actual: float, tolerance: float = 0.01) -> bool:
    if expected == 0:
        return abs(actual) <= tolerance
    return abs(expected - actual) / max(abs(expected), 1e-9) <= tolerance


def validate_invoice(invoice: InvoiceData) -> Tuple[ProcessingStatus, List[str]]:
    warnings: List[str] = []

    if not invoice.invoice_number:
        raise ValidationError("Missing invoice_number")
    if invoice.total_amount is None:
        raise ValidationError("Missing total_amount")
    if not invoice.vendor or not invoice.vendor.name:
        raise ValidationError("Missing vendor.name")
    if invoice.confidence_score < 0.5:
        raise ValidationError("Low confidence extraction")
    if 0.5 <= invoice.confidence_score < 0.7:
        warnings.append("Low confidence — manual review recommended")

    math_errors: List[MathError] = []
    line_total_sum = 0.0
    line_total_count = 0

    for idx, item in enumerate(invoice.line_items or []):
        if item.quantity is not None and item.unit_price is not None:
            expected = float(item.quantity) * float(item.unit_price)
            actual = float(item.total) if item.total is not None else expected
            if item.total is None or not _approx_equal(expected, actual):
                delta = abs(expected - actual)
                math_errors.append(
                    MathError(
                        field=f"line_items[{idx}].total",
                        expected=expected,
                        actual=actual,
                        delta=delta,
                        severity="warning",
                    )
                )
        if item.total is not None:
            line_total_sum += float(item.total)
            line_total_count += 1

    if invoice.subtotal is not None and line_total_count > 0:
        expected = line_total_sum
        actual = float(invoice.subtotal)
        if not _approx_equal(expected, actual):
            delta = abs(expected - actual)
            math_errors.append(
                MathError(
                    field="subtotal",
                    expected=expected,
                    actual=actual,
                    delta=delta,
                    severity="warning",
                )
            )

    if invoice.total_amount is not None and invoice.subtotal is not None:
        tax = float(invoice.tax_amount or 0.0)
        shipping = float(invoice.shipping_amount or 0.0)
        expected = float(invoice.subtotal) + tax + shipping
        actual = float(invoice.total_amount)
        if not _approx_equal(expected, actual):
            delta = abs(expected - actual)
            math_errors.append(
                MathError(
                    field="total_amount",
                    expected=expected,
                    actual=actual,
                    delta=delta,
                    severity="warning",
                )
            )

    invoice.math_errors = math_errors

    total_amount = float(invoice.total_amount or 0.0)
    for err in math_errors:
        if total_amount and err.delta > 0.10 * total_amount:
            warnings.append("Significant math discrepancy detected")
            break

    due_date = _parse_date(invoice.due_date)
    if due_date and due_date < dt.date.today():
        warnings.append("Invoice is overdue")

    if invoice.balance_due is not None and invoice.amount_paid is not None:
        if float(invoice.balance_due) > 0 and float(invoice.amount_paid) > 0:
            warnings.append("Partial payment recorded")

    status = ProcessingStatus.SUCCESS
    if warnings:
        status = ProcessingStatus.WARNING

    logger.info("validation_status=%s warnings=%s math_errors=%s", status, len(warnings), len(math_errors))
    return status, warnings
