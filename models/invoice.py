from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    hours: Optional[float] = None
    rate: float
    amount: float


class BillingResult(BaseModel):
    """Output of the Processing Engine."""
    regular_hours: float
    overtime_hours: float
    regular_amount: float
    overtime_amount: float
    subtotal: float
    gst_amount: float
    total_amount: float
    currency: str
    exchange_rate_to_inr: float = 1.0
    total_amount_inr: float
    line_items: list[LineItem]
    billing_notes: list[str] = Field(default_factory=list)


class Invoice(BaseModel):
    invoice_number: str
    invoice_date: date
    due_date: date
    employee_id: str
    employee_name: str
    client_id: str
    client_name: str
    contract_id: str
    billing_period_start: date
    billing_period_end: date
    billing: BillingResult
    pdf_path: Optional[str] = None
    excel_path: Optional[str] = None
    status: str = "GENERATED"          # GENERATED | DISPATCHED | PAID | FLAGGED
    created_at: datetime = Field(default_factory=datetime.utcnow)
