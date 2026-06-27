"""
Test engines/validation_engine.py
Run: venv/bin/python tests/test_validation_engine.py
"""
import sys
import json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.validation_engine import ValidationEngine
from engines.processing_engine import ProcessingEngine
from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument
from models.validation import EngineResult

print("Testing engines/validation_engine.py...")

# ── Factory helpers ────────────────────────────────────────────────────────────
def make_results(
    hours_per_day: list = None,
    contracted: float = 160.0,
    overtime_allowed: bool = True,
    policy: str = "pay_actual",
    currency: str = "INR",
    gst: bool = True,
    gst_rate: float = 0.18,
    billing_rate: float = 1500.0,
    employee_id: str = "EMP001",
    employee_name: str = "Arjun Sharma",
    client_id: str = "CLI001",
    client_name: str = "Infosys Ltd",
    contract_id: str = "CON001",
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2026, 12, 31),
    bp_start: date = date(2024, 6, 1),
    bp_end: date = date(2024, 6, 30),
    timesheet_dates: list = None,
):
    if hours_per_day is None:
        hours_per_day = [8] * 20

    emp = Employee(employee_id=employee_id, name=employee_name, designation="SWE")
    cli = Client(client_id=client_id, company_name=client_name,
                 country="India", currency=currency)
    con = Contract(
        contract_id=contract_id, client_id=client_id, employee_id=employee_id,
        billing_rate=billing_rate, currency=currency, contracted_hours=contracted,
        start_date=start_date, end_date=end_date,
        overtime_allowed=overtime_allowed, early_completion_policy=policy,
        gst_applicable=gst, gst_rate=gst_rate,
    )

    if timesheet_dates:
        timesheet = [
            TimesheetEntry(date=d, employee_id=employee_id, hours_worked=8.0)
            for d in timesheet_dates
        ]
    else:
        timesheet = [
            TimesheetEntry(date=date(2024, 6, i+1), employee_id=employee_id,
                          hours_worked=h)
            for i, h in enumerate(hours_per_day)
        ]

    doc = ExtractedDocument(
        employee=emp, client=cli, contract=con, timesheet=timesheet,
        billing_period_start=bp_start, billing_period_end=bp_end,
    )
    doc_result = EngineResult(stage="document", status="SUCCESS", confidence=0.97)
    doc_result.data = json.loads(doc.model_dump_json())
    proc_result = ProcessingEngine.process(doc_result)
    return doc_result, proc_result


# ── 1. Full happy path — all 14 checks pass ───────────────────────────────────
dr, pr = make_results()
result = ValidationEngine.process(dr, pr, existing_invoices=[])
assert result.status == "SUCCESS", f"Expected SUCCESS got {result.status}: {result.errors}"
assert result.data["overall"] == "VALID"
assert result.data["failed"] == 0
assert result.data["total_checks"] == 14
print(f"✓ Happy path — all {result.data['total_checks']} checks pass")

# ── 2. Missing mandatory field — employee_id UNKNOWN ─────────────────────────
dr2, pr2 = make_results(employee_id="UNKNOWN")
result2 = ValidationEngine.process(dr2, pr2)
assert result2.status == "FAILED"
assert any("mandatory" in e.lower() or "Missing" in e for e in result2.errors)
print("✓ Rule 1 — missing mandatory field detected")

# ── 3. Employee not in master data ────────────────────────────────────────────
dr3, pr3 = make_results(employee_id="EMP999", employee_name="Ghost Person")
result3 = ValidationEngine.process(dr3, pr3)
assert result3.status == "FAILED"
assert any("not found in master data" in e for e in result3.errors)
print("✓ Rule 2 — unknown employee rejected")

# ── 4. Client not in master data ──────────────────────────────────────────────
dr4, pr4 = make_results(client_id="CLI999", client_name="Ghost Corp")
result4 = ValidationEngine.process(dr4, pr4)
assert result4.status == "FAILED"
assert any("not found in master data" in e for e in result4.errors)
print("✓ Rule 3 — unknown client rejected")

# ── 5. Expired contract ───────────────────────────────────────────────────────
dr5, pr5 = make_results(start_date=date(2020, 1, 1), end_date=date(2021, 12, 31))
result5 = ValidationEngine.process(dr5, pr5)
assert result5.status == "FAILED"
assert any("expired" in e.lower() for e in result5.errors)
print("✓ Rule 4 — expired contract rejected")

# ── 6. Future contract ────────────────────────────────────────────────────────
dr6, pr6 = make_results(start_date=date(2030, 1, 1), end_date=date(2031, 12, 31),
                        bp_start=date(2030, 6, 1), bp_end=date(2030, 6, 30))
result6 = ValidationEngine.process(dr6, pr6)
assert result6.status == "FAILED"
assert any("not started" in e.lower() for e in result6.errors)
print("✓ Rule 4 — future contract rejected")

# ── 7. Billing period outside contract dates ──────────────────────────────────
dr7, pr7 = make_results(
    bp_start=date(2023, 1, 1),
    bp_end=date(2023, 1, 31),
)
result7 = ValidationEngine.process(dr7, pr7)
assert result7.status == "FAILED"
assert any("outside" in e.lower() for e in result7.errors)
print("✓ Rule 6 — billing period outside contract dates rejected")

# ── 8. Zero hours in timesheet entry ─────────────────────────────────────────
from models.schema import TimesheetEntry as TS
emp = Employee(employee_id="EMP001", name="Arjun Sharma", designation="SWE")
cli = Client(client_id="CLI001", company_name="Infosys Ltd", country="India", currency="INR")
con = Contract(
    contract_id="CON001", client_id="CLI001", employee_id="EMP001",
    billing_rate=1500.0, currency="INR", contracted_hours=160.0,
    start_date=date(2024,1,1), end_date=date(2026,12,31),
    gst_applicable=True, gst_rate=0.18,
)
bad_timesheet_doc = ExtractedDocument(
    employee=emp, client=cli, contract=con,
    timesheet=[TS(date=date(2024,6,1), employee_id="EMP001", hours_worked=0.0)],
    billing_period_start=date(2024,6,1), billing_period_end=date(2024,6,30),
)
dr8 = EngineResult(stage="document", status="SUCCESS", confidence=0.97)
dr8.data = json.loads(bad_timesheet_doc.model_dump_json())
pr8 = ProcessingEngine.process(dr8)
result8 = ValidationEngine.process(dr8, pr8)
assert result8.status == "FAILED"
assert any("Invalid hours" in e for e in result8.errors)
print("✓ Rule 7 — zero hours timesheet entry rejected")

# ── 9. Currency mismatch ──────────────────────────────────────────────────────
dr9, pr9 = make_results(currency="INR")
# Tamper billing currency
proc_data_copy = dict(pr9.data)
proc_data_copy["currency"] = "USD"
pr9_bad = EngineResult(stage="processing", status="SUCCESS", confidence=1.0)
pr9_bad.data = proc_data_copy
result9 = ValidationEngine.process(dr9, pr9_bad)
assert result9.status == "FAILED"
assert any("Currency mismatch" in e for e in result9.errors)
print("✓ Rule 9 — currency mismatch detected")

# ── 10. Duplicate invoice detection ──────────────────────────────────────────
dr10, pr10 = make_results()
existing = [{
    "invoice_number": "INV-2024-CLI001-0001",
    "employee_id": "EMP001",
    "client_id": "CLI001",
    "billing_period_start": "2024-06-01",
    "billing_period_end": "2024-06-30",
}]
result10 = ValidationEngine.process(dr10, pr10, existing_invoices=existing)
assert result10.status == "FAILED"
assert any("Duplicate" in e for e in result10.errors)
print("✓ Rule 12 — duplicate invoice detected")

# ── 11. Timesheet date outside billing period (warning) ───────────────────────
dr11, pr11 = make_results(
    timesheet_dates=[date(2024, 5, 15), date(2024, 6, 5)]  # May date is out of June period
)
result11 = ValidationEngine.process(dr11, pr11)
assert any("outside billing period" in w for w in result11.warnings)
print("✓ Rule 13 — out-of-range timesheet date raises warning")

# ── 12. Contract linkage mismatch ─────────────────────────────────────────────
# Build manually: client says CLI002 but contract says CLI001
emp12 = Employee(employee_id="EMP001", name="Arjun Sharma", designation="SWE")
cli12 = Client(client_id="CLI002", company_name="Accenture UK", country="UK", currency="INR")
con12 = Contract(contract_id="CON001", client_id="CLI001", employee_id="EMP001",
    billing_rate=1500, currency="INR", contracted_hours=160,
    start_date=date(2024,1,1), end_date=date(2026,12,31))
doc12 = ExtractedDocument(employee=emp12, client=cli12, contract=con12,
    timesheet=[TimesheetEntry(date=date(2024,6,1), employee_id="EMP001", hours_worked=8)],
    billing_period_start=date(2024,6,1), billing_period_end=date(2024,6,30))
dr12 = EngineResult(stage="document", status="SUCCESS", confidence=0.97)
dr12.data = json.loads(doc12.model_dump_json())
pr12 = ProcessingEngine.process(dr12)
result12 = ValidationEngine.process(dr12, pr12)
assert result12.status == "FAILED"
assert any("linkage" in e.lower() for e in result12.errors)
print("✓ Rule 14 — employee–client–contract linkage mismatch detected")

# ── 13. Confidence score degrades on failures ─────────────────────────────────
dr13, pr13 = make_results(employee_id="EMP999", employee_name="Ghost Person")
result13 = ValidationEngine.process(dr13, pr13)
assert result13.confidence < 1.0
print(f"✓ Confidence degrades on failure — score={result13.confidence}")

# ── 14. Failed upstream blocked ───────────────────────────────────────────────
bad_upstream = EngineResult(stage="document", status="FAILED")
bad_upstream.add_error("File corrupted")
bad_proc = EngineResult(stage="processing", status="FAILED")
bad_proc.add_error("No data")
result14 = ValidationEngine.process(bad_upstream, bad_proc)
assert result14.status == "FAILED"
print("✓ Failed upstream → validation blocked cleanly")

print(f"\nPASS — engines/validation_engine.py  (14 rules, all tested)")
