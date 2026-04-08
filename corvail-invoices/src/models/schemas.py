from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ProcessingStatus(str, Enum):
    SUCCESS = "success"
    WARNING = "warning"
    REJECTED = "rejected"


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    sku: Optional[str] = None
    unit: Optional[str] = None


class MathError(BaseModel):
    field: str
    expected: float
    actual: float
    delta: float
    severity: str  # "warning" or "error"


class VendorInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tax_id: Optional[str] = None
    bank_details: Optional[str] = None


class BillToInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None


class InvoiceData(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    reference_number: Optional[str] = None
    vendor: VendorInfo
    bill_to: BillToInfo
    line_items: List[LineItem]
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
    math_errors: List[MathError]
    confidence_score: float


class InvoiceResponse(BaseModel):
    status: ProcessingStatus
    product: str = "corvail-invoices"
    version: str = "1.0.0"
    invoice: Optional[InvoiceData] = None
    processing_time_ms: float
    sender_email: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str]
    timestamp: str
