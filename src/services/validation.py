from __future__ import annotations

import datetime as dt
from typing import List, Optional, Tuple

from src.core import ValidationError
from src.models import InvoiceData, MathError, ProcessingStatus


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    """Parse common invoice date formats."""
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _approx_equal(expected: float, actual: float, tolerance: float = 0.01) -> bool:
    """Return whether two invoice values are materially equal."""
    if expected == 0:
        return abs(actual) <= tolerance
    return abs(expected - actual) / max(abs(expected), 1e-9) <= tolerance


def validate_invoice(invoice: InvoiceData) -> Tuple[ProcessingStatus, List[str]]:
    """Validate invoice fields and populate math discrepancies."""
    warnings: List[str] = []
    if not invoice.invoice_number:
        raise ValidationError(message='Missing invoice_number')
    if invoice.total_amount is None:
        raise ValidationError(message='Missing total_amount')
    if not invoice.vendor or not invoice.vendor.name:
        raise ValidationError(message='Missing vendor.name')
    if invoice.confidence_score < 0.5:
        raise ValidationError(message='Low confidence extraction')
    if 0.5 <= invoice.confidence_score < 0.7:
        warnings.append('Low confidence — manual review recommended')
    math_errors: List[MathError] = []
    line_total_sum = 0.0
    line_total_count = 0
    for idx, item in enumerate(invoice.line_items or []):
        if item.quantity is not None and item.unit_price is not None:
            expected = float(item.quantity) * float(item.unit_price)
            actual = float(item.total) if item.total is not None else expected
            if item.total is None or not _approx_equal(expected, actual):
                math_errors.append(MathError(field=f'line_items[{idx}].total', expected=expected, actual=actual, delta=abs(expected - actual), severity='warning'))
        if item.total is not None:
            line_total_sum += float(item.total)
            line_total_count += 1
    if invoice.subtotal is not None and line_total_count > 0 and not _approx_equal(line_total_sum, float(invoice.subtotal)):
        math_errors.append(MathError(field='subtotal', expected=line_total_sum, actual=float(invoice.subtotal), delta=abs(line_total_sum - float(invoice.subtotal)), severity='warning'))
    if invoice.total_amount is not None and invoice.subtotal is not None:
        expected = float(invoice.subtotal) + float(invoice.tax_amount or 0.0) + float(invoice.shipping_amount or 0.0)
        actual = float(invoice.total_amount)
        if not _approx_equal(expected, actual):
            math_errors.append(MathError(field='total_amount', expected=expected, actual=actual, delta=abs(expected - actual), severity='warning'))
    invoice.math_errors = math_errors
    total_amount = float(invoice.total_amount or 0.0)
    for err in math_errors:
        if total_amount and err.delta > 0.10 * total_amount:
            warnings.append('Significant math discrepancy detected')
            break
    due_date = _parse_date(invoice.due_date)
    if due_date and due_date < dt.date.today():
        warnings.append('Invoice is overdue')
    if invoice.balance_due is not None and invoice.amount_paid is not None and float(invoice.balance_due) > 0 and float(invoice.amount_paid) > 0:
        warnings.append('Partial payment recorded')
    return (ProcessingStatus.WARNING if warnings else ProcessingStatus.SUCCESS, warnings)
