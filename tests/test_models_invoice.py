"""Test models/invoice.py — run: venv/bin/python tests/test_models_invoice.py"""
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.invoice import LineItem, BillingResult, Invoice

print("Testing models/invoice.py...")

# LineItem
li = LineItem(description="Regular hours", hours=160.0, rate=1500.0, amount=240000.0)
assert li.amount == 240000.0
print("✓ LineItem model")

# BillingResult
billing = BillingResult(
    regular_hours=160.0, overtime_hours=8.0,
    regular_amount=240000.0, overtime_amount=18000.0,
    subtotal=258000.0, gst_amount=46440.0,
    total_amount=304440.0, currency="INR",
    total_amount_inr=304440.0,
    line_items=[li],
    billing_notes=["Overtime applied at 1.5x"],
)
assert billing.subtotal == 258000.0
assert billing.gst_amount == 46440.0
assert len(billing.billing_notes) == 1
print("✓ BillingResult model")

# Invoice
invoice = Invoice(
    invoice_number="INV-2024-CLI001-0001",
    invoice_date=date(2024, 7, 1),
    due_date=date(2024, 7, 31),
    employee_id="EMP001", employee_name="Arjun Sharma",
    client_id="CLI001", client_name="Infosys",
    contract_id="CON001",
    billing_period_start=date(2024, 6, 1),
    billing_period_end=date(2024, 6, 30),
    billing=billing,
)
assert invoice.status == "GENERATED"
assert invoice.pdf_path is None
assert invoice.excel_path is None
print("✓ Invoice model — default status=GENERATED")

# Status update
invoice.status = "DISPATCHED"
assert invoice.status == "DISPATCHED"
print("✓ Invoice status mutable")

print("PASS — models/invoice.py")
