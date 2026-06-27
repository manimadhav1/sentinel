from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Employee(BaseModel):
    employee_id: str
    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    hsn_code: Optional[str] = None   # service classification code


class Client(BaseModel):
    client_id: str
    company_name: str
    billing_address: Optional[str] = None
    country: str = "India"
    currency: str = "INR"
    gst_number: Optional[str] = None
    timezone: Optional[str] = "Asia/Kolkata"
    contact_email: Optional[str] = None


class Contract(BaseModel):
    contract_id: str
    client_id: str
    employee_id: str
    billing_rate: float                     # per hour
    currency: str = "INR"
    billing_type: str = "hourly"            # hourly | daily | fixed
    contracted_hours: Optional[float] = None
    start_date: date
    end_date: date
    overtime_allowed: bool = True
    overtime_multiplier: float = 1.5
    early_completion_policy: str = "pay_actual"   # pay_full | pay_actual
    late_penalty_per_hour: float = 0.0
    gst_applicable: bool = True
    gst_rate: float = 0.18
    payment_terms_days: int = 30

    @field_validator("billing_type")
    @classmethod
    def validate_billing_type(cls, v: str) -> str:
        allowed = {"hourly", "daily", "fixed"}
        if v not in allowed:
            raise ValueError(f"billing_type must be one of {allowed}")
        return v


class TimesheetEntry(BaseModel):
    date: date
    employee_id: str
    hours_worked: float
    task_description: Optional[str] = None
    overtime_hours: float = 0.0

    @field_validator("hours_worked")
    @classmethod
    def validate_hours(cls, v: float) -> float:
        if v < 0 or v > 24:
            raise ValueError("hours_worked must be between 0 and 24")
        return v


class ExtractedDocument(BaseModel):
    """Standard JSON shape produced by the Document Engine."""
    employee: Employee
    client: Client
    contract: Contract
    timesheet: list[TimesheetEntry]
    billing_period_start: date
    billing_period_end: date
    source_file: Optional[str] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
