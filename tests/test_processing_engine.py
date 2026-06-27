"""
Test engines/processing_engine.py
Run: venv/bin/python tests/test_processing_engine.py
"""
import sys
import json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.processing_engine import ProcessingEngine
from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument
from models.validation import EngineResult

print("Testing engines/processing_engine.py...")

# ── Helpers ────────────────────────────────────────────────────────────────────
def make_doc(hours_per_day: list, contracted: float,
             overtime_allowed=True, policy="pay_actual",
             currency="INR", gst=True, penalty=0.0) -> EngineResult:
    emp = Employee(employee_id="EMP001", name="Arjun Sharma", designation="SWE")
    cli = Client(client_id="CLI001", company_name="Infosys", country="India", currency=currency)
    con = Contract(
        contract_id="CON001", client_id="CLI001", employee_id="EMP001",
        billing_rate=1500.0, currency=currency,
        contracted_hours=contracted,
        start_date=date(2024, 1, 1), end_date=date(2026, 12, 31),
        overtime_allowed=overtime_allowed,
        early_completion_policy=policy,
        late_penalty_per_hour=penalty,
        gst_applicable=gst, gst_rate=0.18,
    )
    timesheet = [
        TimesheetEntry(date=date(2024, 6, i+1), employee_id="EMP001", hours_worked=h)
        for i, h in enumerate(hours_per_day)
    ]
    doc = ExtractedDocument(
        employee=emp, client=cli, contract=con, timesheet=timesheet,
        billing_period_start=date(2024, 6, 1), billing_period_end=date(2024, 6, 30),
    )
    upstream = EngineResult(stage="document", status="SUCCESS", confidence=0.97)
    upstream.data = json.loads(doc.model_dump_json())
    return upstream


# ── 1. Standard billing — exact hours ─────────────────────────────────────────
r = ProcessingEngine.process(make_doc([8]*20, contracted=160.0))
b = r.data
assert r.status == "SUCCESS"
assert b["regular_hours"] == 160.0
assert b["overtime_hours"] == 0.0
assert b["regular_amount"] == 160 * 1500
assert b["gst_amount"] == round(240000 * 0.18, 2)
assert b["total_amount"] == round(240000 * 1.18, 2)
print("✓ Standard billing — exact contracted hours")

# ── 2. Early completion — pay_actual ──────────────────────────────────────────
r2 = ProcessingEngine.process(make_doc([8]*15, contracted=160.0, policy="pay_actual"))
b2 = r2.data
assert b2["regular_hours"] == 120.0
assert b2["regular_amount"] == 120 * 1500
print("✓ Early completion — pay_actual (bills 120h not 160h)")

# ── 3. Early completion — pay_full ────────────────────────────────────────────
r3 = ProcessingEngine.process(make_doc([8]*15, contracted=160.0, policy="pay_full"))
b3 = r3.data
assert b3["regular_hours"] == 160.0
assert b3["regular_amount"] == 160 * 1500
print("✓ Early completion — pay_full (bills full 160h)")

# ── 4. Overtime allowed ────────────────────────────────────────────────────────
r4 = ProcessingEngine.process(make_doc([8]*20 + [8]*2, contracted=160.0, overtime_allowed=True))
b4 = r4.data
assert b4["regular_hours"] == 160.0
assert b4["overtime_hours"] == 16.0
assert b4["overtime_amount"] == round(16 * 1500 * 1.5, 2)
print("✓ Overtime allowed — 16h OT at 1.5x")

# ── 5. Overtime NOT allowed ────────────────────────────────────────────────────
r5 = ProcessingEngine.process(make_doc([8]*22, contracted=160.0, overtime_allowed=False))
b5 = r5.data
assert b5["regular_hours"] == 160.0
assert b5["overtime_hours"] == 0.0
assert b5["overtime_amount"] == 0.0
assert len(r5.warnings) > 0
print("✓ Overtime not allowed — excess hours unbilled, warning raised")

# ── 6. GST not applicable ─────────────────────────────────────────────────────
r6 = ProcessingEngine.process(make_doc([8]*20, contracted=160.0, gst=False))
b6 = r6.data
assert b6["gst_amount"] == 0.0
assert b6["total_amount"] == b6["subtotal"]
print("✓ GST not applicable — zero GST")

# ── 7. Foreign currency (GBP) ─────────────────────────────────────────────────
r7 = ProcessingEngine.process(make_doc([8]*20, contracted=160.0, currency="GBP", gst=False))
b7 = r7.data
assert b7["currency"] == "GBP"
assert b7["exchange_rate_to_inr"] == 105.3
assert b7["total_amount_inr"] == round(b7["total_amount"] * 105.3, 2)
print(f"✓ Foreign currency GBP — total_inr={b7['total_amount_inr']}")

# ── 8. Failed upstream → processing skipped ───────────────────────────────────
failed_upstream = EngineResult(stage="document", status="FAILED", confidence=0.0)
failed_upstream.add_error("File not found")
r8 = ProcessingEngine.process(failed_upstream)
assert r8.status == "FAILED"
print("✓ Failed upstream → processing aborted cleanly")

# ── 9. Late penalty ───────────────────────────────────────────────────────────
r9 = ProcessingEngine.process(make_doc([8]*22, contracted=160.0, overtime_allowed=True, penalty=500.0))
b9 = r9.data
assert b9["overtime_hours"] == 16.0
penalty_note = any("penalty" in n.lower() for n in b9["billing_notes"])
assert penalty_note
print("✓ Late penalty applied and noted in billing_notes")

# ── 10. Line items present ────────────────────────────────────────────────────
r10 = ProcessingEngine.process(make_doc([8]*22, contracted=160.0, overtime_allowed=True))
b10 = r10.data
assert len(b10["line_items"]) >= 2
print(f"✓ Line items generated — {len(b10['line_items'])} items")

print("\nPASS — engines/processing_engine.py")
