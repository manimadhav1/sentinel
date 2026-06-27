"""
Test services/database_service.py
Run: venv/bin/python tests/test_database_service.py
"""
import sys, json
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use a test DB so we don't pollute the real one
import config
config.DATABASE_PATH = config.RUNTIME_DIR / "test_database.db"
if config.DATABASE_PATH.exists():
    config.DATABASE_PATH.unlink()

from services.database_service import DatabaseService

print("Testing services/database_service.py...")

DatabaseService.initialise()
print("✓ Database initialised")

# ── Sample invoice dict ────────────────────────────────────────────────────────
sample_invoice = {
    "invoice_number": "INV-2026-CL001-0001",
    "employee_id":    "EMP10001",
    "employee_name":  "Carlos Smith",
    "client_id":      "CL001",
    "client_name":    "Emirates Steel",
    "contract_id":    "CON-EMP10001-CL001",
    "billing_period_start": "2026-06-01",
    "billing_period_end":   "2026-06-30",
    "invoice_date":   "2026-07-01",
    "due_date":       "2026-07-31",
    "status":         "GENERATED",
    "pdf_path":       "/output/pdf/INV-2026-CL001-0001.pdf",
    "excel_path":     "/output/excel/INV-2026-CL001-0001_ERP.xlsx",
    "billing": {
        "currency": "AED", "total_amount": 9750.0,
        "total_amount_inr": 221325.0, "gst_amount": 0.0,
        "regular_hours": 192.0, "overtime_hours": 0.0,
        "subtotal": 9750.0, "regular_amount": 9750.0,
        "overtime_amount": 0.0, "exchange_rate_to_inr": 22.7,
        "line_items": [], "billing_notes": [],
    }
}

# ── Save and retrieve ──────────────────────────────────────────────────────────
row_id = DatabaseService.save_invoice(sample_invoice)
assert row_id > 0
print(f"✓ Invoice saved (row_id={row_id})")

fetched = DatabaseService.get_invoice("INV-2026-CL001-0001")
assert fetched is not None
assert fetched["employee_name"] == "Carlos Smith"
assert fetched["total_amount"]  == 9750.0
print(f"✓ Invoice retrieved: {fetched['invoice_number']}")

# ── Status update ──────────────────────────────────────────────────────────────
DatabaseService.update_invoice_status("INV-2026-CL001-0001", "DISPATCHED")
updated = DatabaseService.get_invoice("INV-2026-CL001-0001")
assert updated["status"] == "DISPATCHED"
print("✓ Status updated → DISPATCHED")

# ── Duplicate detection ────────────────────────────────────────────────────────
dup = DatabaseService.is_duplicate("EMP10001", "CL001", "2026-06-01", "2026-06-30")
assert dup is not None
assert dup["invoice_number"] == "INV-2026-CL001-0001"
print("✓ Duplicate detected correctly")

no_dup = DatabaseService.is_duplicate("EMP10001", "CL001", "2026-07-01", "2026-07-31")
assert no_dup is None
print("✓ Non-duplicate period returns None")

# ── Sequence ───────────────────────────────────────────────────────────────────
seq = DatabaseService.next_sequence("CL001")
assert seq == 2
print(f"✓ Next sequence for CL001 = {seq}")

# ── List invoices ──────────────────────────────────────────────────────────────
all_inv = DatabaseService.list_invoices()
assert len(all_inv) == 1
assert all_inv[0]["client_id"] == "CL001"
print(f"✓ list_invoices returned {len(all_inv)} invoice(s)")

filtered = DatabaseService.list_invoices(client_id="CL001")
assert len(filtered) == 1
print("✓ Filtered by client_id works")

# ── Review queue ───────────────────────────────────────────────────────────────
qid = DatabaseService.add_to_review_queue(
    stage="document", confidence=0.61,
    errors=["Employee name matched multiple records"],
    warnings=[], ambiguous_fields=[{"field": "employee_name", "confidence": 0.61}],
    raw_data={"employee": {"name": "A. Smith"}},
    source_file="upload/timesheet.pdf",
    employee_name="A. Smith", client_name="Emirates Steel",
    priority="HIGH",
)
assert qid > 0
print(f"✓ Added to review queue (id={qid})")

queue = DatabaseService.get_review_queue("PENDING")
assert len(queue) == 1
assert queue[0]["priority"] == "HIGH"
assert queue[0]["confidence"] == 0.61
print(f"✓ Review queue has {len(queue)} pending item(s)")

DatabaseService.resolve_review_item(qid, notes="Confirmed EMP10001")
resolved = DatabaseService.get_review_queue("RESOLVED")
assert len(resolved) == 1
print("✓ Review item resolved")

# ── Audit log ──────────────────────────────────────────────────────────────────
DatabaseService.log_event("DOCUMENT_PROCESSED", invoice_number="INV-2026-CL001-0001",
                           stage="document", status="SUCCESS", confidence=0.97,
                           message="File processed OK")
DatabaseService.log_event("INVOICE_GENERATED", invoice_number="INV-2026-CL001-0001",
                           stage="invoice", status="SUCCESS", confidence=1.0)

log = DatabaseService.get_audit_log("INV-2026-CL001-0001")
assert len(log) == 2
print(f"✓ Audit log has {len(log)} entries for INV-2026-CL001-0001")

# ── Stats ──────────────────────────────────────────────────────────────────────
stats = DatabaseService.get_stats()
assert stats["total_invoices"] == 1
assert stats["total_billed_inr"] > 0
assert stats["pending_review"] == 0
assert "DISPATCHED" in stats["by_status"]
print(f"✓ Stats: {stats['total_invoices']} invoice | "
      f"₹{stats['total_billed_inr']:,.0f} billed | "
      f"{stats['pending_review']} pending review")

# Cleanup test DB
config.DATABASE_PATH.unlink(missing_ok=True)
print("✓ Test database cleaned up")

print("\nPASS — services/database_service.py")
