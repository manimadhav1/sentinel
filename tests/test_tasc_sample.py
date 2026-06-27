"""
TASC Sample Database Test
Run: venv/bin/python tests/test_tasc_sample.py

Loads the official TASC_Sample_Database_vF.xlsx and runs
3 representative payroll records through the full pipeline
(Document → Processing → Validation).

No Gemini API call — data is loaded directly from Excel.
"""
import sys
import json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument
from models.validation import EngineResult
from engines.processing_engine import ProcessingEngine
from engines.validation_engine import ValidationEngine
from utils.helpers import format_currency

SAMPLE_FILE = Path("/Users/madhavan/Downloads/For Contestants/TASC_Sample_Database_vF.xlsx")

print("=" * 60)
print("  SENTINEL — TASC Sample Database Run")
print("=" * 60)

if not SAMPLE_FILE.exists():
    print(f"ERROR: File not found at {SAMPLE_FILE}")
    sys.exit(1)

# ── Load Excel sheets ──────────────────────────────────────────────────────────
xl        = pd.ExcelFile(SAMPLE_FILE)
customers = xl.parse("Customers")
employees = xl.parse("Employees")
payroll   = xl.parse("Payroll_June2026")

print(f"\nLoaded: {len(customers)} clients, {len(employees)} employees, "
      f"{len(payroll)} payroll records")

# ── Pick 3 test records ────────────────────────────────────────────────────────
# Record 1: Standard clean record         (EMP10001 — Carlos Smith, CL001)
# Record 2: Employee with overtime        (EMP10002 — Ahmed Khan, CL001)
# Record 3: Ambiguous name test           (EMP10058 — Aisha Al Zaabi, shared name)

test_emp_ids = ["EMP10001", "EMP10002", "EMP10058"]
records = payroll[payroll["Emp ID"].isin(test_emp_ids)].reset_index(drop=True)

def build_and_run(row, label: str):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")

    # ── Map Excel row → internal schema ───────────────────────────────────────
    emp_id      = str(row["Emp ID"])
    emp_name    = str(row["Employee Name"])
    client_id   = str(row["Client Code"])
    client_name = str(row["Client Name"])
    currency    = str(row["Currency"])
    gross       = float(row["Gross"])
    ot_hours    = float(row["OT Hours"])
    ot_amount   = float(row["OT Amount"])
    working_days = int(row["Working Days"])
    deductions  = float(row["Deductions"])
    net_pay     = float(row["Net Pay"])

    # Derive daily rate from gross (gross / contracted working days in month)
    contracted_hours = working_days * 8.0
    daily_rate       = round(gross / working_days, 4) if working_days else 0
    hourly_rate      = round(daily_rate / 8, 4)

    print(f"  Employee  : {emp_name} ({emp_id})")
    print(f"  Client    : {client_name} ({client_id})")
    print(f"  Gross Pay : {currency} {gross:,.2f}")
    print(f"  OT Hours  : {ot_hours}h  |  OT Amount: {currency} {ot_amount:,.2f}")
    print(f"  Working   : {working_days} days  |  Hourly Rate ≈ {currency} {hourly_rate:.4f}")

    # ── Build models ───────────────────────────────────────────────────────────
    employee = Employee(
        employee_id=emp_id,
        name=emp_name,
        designation=employees[employees["Emp ID"] == emp_id]["Job Title"].values[0]
            if emp_id in employees["Emp ID"].values else "Unknown",
    )

    client = Client(
        client_id=client_id,
        company_name=client_name,
        country="UAE",
        currency=currency,
    )

    contract = Contract(
        contract_id=f"CON-{emp_id}-{client_id}",
        client_id=client_id,
        employee_id=emp_id,
        billing_rate=hourly_rate,
        currency=currency,
        billing_type="hourly",
        contracted_hours=contracted_hours,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        overtime_allowed=True,
        overtime_multiplier=1.5,
        early_completion_policy="pay_actual",
        gst_applicable=False,   # UAE VAT handled separately
        gst_rate=0.0,
        payment_terms_days=30,
    )

    # Build timesheet — distribute working_days evenly across June 2026
    timesheet = []
    day = 1
    added = 0
    while added < working_days and day <= 30:
        d = date(2026, 6, day)
        if d.weekday() < 5:  # Mon–Fri
            hours = 8.0
            if added == 0 and ot_hours > 0:
                hours += min(ot_hours, 4.0)   # add OT to first day for simplicity
            timesheet.append(TimesheetEntry(
                date=d,
                employee_id=emp_id,
                hours_worked=min(hours, 24.0),
                overtime_hours=min(ot_hours, 4.0) if added == 0 else 0.0,
            ))
            added += 1
        day += 1

    doc = ExtractedDocument(
        employee=employee,
        client=client,
        contract=contract,
        timesheet=timesheet,
        billing_period_start=date(2026, 6, 1),
        billing_period_end=date(2026, 6, 30),
        source_file=str(SAMPLE_FILE.name),
    )

    # ── Wrap in EngineResult (simulating Document Engine output) ───────────────
    doc_result = EngineResult(
        stage="document", status="SUCCESS", confidence=0.97,
        metadata={"source": "TASC Excel", "extraction": "direct_load"}
    )
    doc_result.data = json.loads(doc.model_dump_json())

    # ── Processing Engine ──────────────────────────────────────────────────────
    proc_result = ProcessingEngine.process(doc_result)

    if proc_result.status == "FAILED":
        print(f"\n  ✗ Processing FAILED: {proc_result.errors}")
        return

    b = proc_result.data
    print(f"\n  [PROCESSING RESULT]")
    print(f"  Regular Hours : {b['regular_hours']}h  @ {currency} {b['regular_amount']:,.2f}")
    print(f"  Overtime Hours: {b['overtime_hours']}h  @ {currency} {b['overtime_amount']:,.2f}")
    print(f"  Subtotal      : {currency} {b['subtotal']:,.2f}")
    print(f"  GST           : {currency} {b['gst_amount']:,.2f}")
    print(f"  TOTAL         : {currency} {b['total_amount']:,.2f}")
    print(f"  Total (INR)   : ₹{b['total_amount_inr']:,.2f}")
    for note in b["billing_notes"]:
        print(f"  Note: {note}")

    # ── Validation Engine ──────────────────────────────────────────────────────
    val_result = ValidationEngine.process(doc_result, proc_result, existing_invoices=[])
    v = val_result.data

    print(f"\n  [VALIDATION RESULT]")
    print(f"  Overall  : {v['overall']}")
    print(f"  Checks   : {v['total_checks']} total | "
          f"{v['passed']} passed | "
          f"{v['failed']} failed | "
          f"{v['warnings']} warnings")

    if val_result.errors:
        for e in val_result.errors:
            print(f"  ✗ ERROR  : {e}")
    if val_result.warnings:
        for w in val_result.warnings:
            print(f"  ⚠ WARN   : {w}")

    status_icon = "✓" if v["overall"] == "VALID" else ("⚠" if v["overall"] == "WARN" else "✗")
    print(f"\n  {status_icon} Pipeline result: {v['overall']} "
          f"(confidence={val_result.confidence:.2f})")


# ── Run all 3 records ──────────────────────────────────────────────────────────
labels = [
    "Record 1 — Carlos Smith (EMP10001) — Standard clean record",
    "Record 2 — Ahmed Khan (EMP10002) — Employee with overtime",
    "Record 3 — Aisha Al Zaabi (EMP10058) — Ambiguous name (shared across clients)",
]

for i, (_, row) in enumerate(records.iterrows()):
    build_and_run(row, labels[i])

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SUMMARY")
print(f"{'='*60}")
print(f"  Total employees in file : {len(employees)}")
print(f"  Total payroll records   : {len(payroll)}")
print(f"  Test records processed  : {len(records)}")
print(f"  Engines run             : Document (mocked) → Processing → Validation")
print(f"  Invoice Engine          : Phase 5 (not yet built)")
print(f"{'='*60}\n")
