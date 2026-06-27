"""Test models/schema.py — run: venv/bin/python tests/test_models_schema.py"""
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument

print("Testing models/schema.py...")

# Employee
emp = Employee(employee_id="EMP001", name="Arjun Sharma", designation="Senior SWE")
assert emp.employee_id == "EMP001"
assert emp.name == "Arjun Sharma"
print("✓ Employee model")

# Client
cli = Client(client_id="CLI001", company_name="Infosys", country="India", currency="INR")
assert cli.currency == "INR"
print("✓ Client model")

# Contract
con = Contract(
    contract_id="CON001", client_id="CLI001", employee_id="EMP001",
    billing_rate=1500.0, currency="INR", contracted_hours=160.0,
    start_date=date(2024, 1, 1), end_date=date(2026, 12, 31),
)
assert con.gst_applicable is True
assert con.gst_rate == 0.18
print("✓ Contract model")

# Invalid billing_type
try:
    Contract(
        contract_id="X", client_id="C", employee_id="E",
        billing_rate=100, start_date=date(2024,1,1), end_date=date(2025,1,1),
        billing_type="monthly"
    )
    print("✗ Should have rejected billing_type=monthly")
    sys.exit(1)
except Exception:
    print("✓ Contract rejects invalid billing_type")

# TimesheetEntry
entry = TimesheetEntry(date=date(2024, 6, 3), employee_id="EMP001", hours_worked=8.5)
assert entry.overtime_hours == 0.0
print("✓ TimesheetEntry model")

# Invalid hours
try:
    TimesheetEntry(date=date(2024,6,3), employee_id="E", hours_worked=25.0)
    print("✗ Should have rejected hours_worked=25")
    sys.exit(1)
except Exception:
    print("✓ TimesheetEntry rejects hours_worked > 24")

# ExtractedDocument
doc = ExtractedDocument(
    employee=emp, client=cli, contract=con,
    timesheet=[entry],
    billing_period_start=date(2024, 6, 1),
    billing_period_end=date(2024, 6, 30),
)
assert len(doc.timesheet) == 1
print("✓ ExtractedDocument model")

print("PASS — models/schema.py")
