"""Pydantic schemas for the Corvail Invoices API."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    """Enumerate invoice processing states."""

    SUCCESS = 'STATUS_SUCCESS'
    WARNING = 'STATUS_WARNING'
    REJECTED = 'STATUS_REJECTED'


class LineItem(BaseModel):
    """Represent an extracted invoice line item."""

    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    sku: Optional[str] = None
    unit: Optional[str] = None


class MathError(BaseModel):
    """Represent a deterministic invoice math discrepancy."""

    field: str
    expected: float
    actual: float
    delta: float
    severity: str


class VendorInfo(BaseModel):
    """Represent supplier identity fields."""

    name: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tax_id: Optional[str] = None
    bank_details: Optional[str] = None


class BillToInfo(BaseModel):
    """Represent bill-to identity fields."""

    name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None


class InvoiceData(BaseModel):
    """Represent the structured invoice payload."""

    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    reference_number: Optional[str] = None
    vendor: VendorInfo = Field(default_factory=VendorInfo)
    bill_to: BillToInfo = Field(default_factory=BillToInfo)
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    discount_amount: Optional[float] = None
    discount_percent: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate: Optional[float] = None
    shipping_amount: Optional[float] = None
    total_amount: Optional[float] = None
    amount_paid: Optional[float] = None
    balance_due: Optional[float] = None
    currency: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    math_errors: List[MathError] = Field(default_factory=list)
    confidence_score: float = 0.0


class InvoiceResponse(BaseModel):
    """Represent the invoices API response envelope."""

    status: ProcessingStatus
    product: str = 'corvail-invoices'
    version: str = '1.0.0'
    invoice: Optional[InvoiceData] = None
    processing_time_ms: float = 0.0
    sender_email: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    timestamp: str = ''
    request_id: Optional[str] = None
    pipeline_timings: Optional[Dict[str, float]] = None
