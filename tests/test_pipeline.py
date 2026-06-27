"""
End-to-End Pipeline Test using TASC sample data.
Run: venv/bin/python tests/test_pipeline.py

Simulates the full pipeline:
Document Engine (mocked) → Processing → Validation → Invoice → Database
"""
import sys, json
from pathlib import Path
from datetime import date
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
# Use isolated test DB
config.DATABASE_PATH = config.RUNTIME_DIR / "test_pipeline.db"
if config.DATABASE_PATH.exists():
    config.DATABASE_PATH.unlink()

from pipeline import SentinelPipeline
from services.database_service import DatabaseService
from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument

print("=" * 60)
print("  SENTINEL — End-to-End Pipeline Test")
print("=" * 60)

# ── Mock Gemini response (TASC Record: Carlos Smith) ──────────────────────────
MOCK_EXTRACTION = {
    "employee": {
        "employee_id": "EMP10001", "name": "Carlos Smith",
        "designation": "Software Engineer", "department": "IT",
        "email": "carlos.smith@test.com", "hsn_code": None,
    },
    "client": {
        "client_id": "CL001", "company_name": "Emirates Steel Industries LLC",
        "billing_address": "Abu Dhabi", "country": "UAE",
        "currency": "AED", "gst_number": None,
        "timezone": "Asia/Dubai", "contact_email": "billing@test.com",
    },
    "contract": {
        "contract_id": "CON-EMP10001-CL001",
        "billing_rate": 50.7812, "currency": "AED",
        "billing_type": "hourly", "contracted_hours": 192.0,
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "overtime_allowed": True, "overtime_multiplier": 1.5,
        "early_completion_policy": "pay_actual",
        "late_penalty_per_hour": 0.0,
        "gst_applicable": False, "gst_rate": 0.0,
        "payment_terms_days": 30,
    },
    "timesheet": [
        {"date": f"2026-06-{str(d).zfill(2)}", "employee_id": "EMP10001",
         "hours_worked": 8.0, "task_description": "Engineering work",
         "overtime_hours": 0.0}
        for d in range(1, 25) if date(2026, 6, d).weekday() < 5
    ],
    "billing_period_start": "2026-06-01",
    "billing_period_end":   "2026-06-30",
    "confidence_scores": {
        "employee": 0.99, "client": 0.98, "contract": 0.97,
        "timesheet": 0.99, "overall": 0.98,
    },
    "ambiguous_fields": [],
    "extraction_notes": "Clean structured Excel input.",
}

# Create dummy upload file
dummy_file = config.UPLOADS_DIR / "test_carlos_june2026.xlsx"
dummy_file.write_bytes(b"PK dummy xlsx content")

pipeline = SentinelPipeline()

# ── Test 1: Full happy path ────────────────────────────────────────────────────
print("\nTest 1: Full happy path — Carlos Smith June 2026")
with patch("engines.document_engine.call_gemini", return_value=MOCK_EXTRACTION):
    result = pipeline.run(dummy_file)

assert result.success,           f"Pipeline failed: {result.summary()}"
assert result.invoice_number,    "No invoice number"
assert result.pdf_path,          "No PDF path"
assert result.excel_path,        "No Excel path"
assert not result.routed_to_review

print(f"  ✓ Status         : {result.final_status}")
print(f"  ✓ Invoice        : {result.invoice_number}")
print(f"  ✓ PDF            : {Path(result.pdf_path).name}")
print(f"  ✓ ERP Excel      : {Path(result.excel_path).name}")
print(f"  ✓ Confidence     : {result.document.confidence:.2f}")

# ── Test 2: Invoice persisted in DB ───────────────────────────────────────────
print("\nTest 2: Invoice persisted in database")
inv_db = DatabaseService.get_invoice(result.invoice_number)
assert inv_db is not None
assert inv_db["employee_id"] == "EMP10001"
assert inv_db["client_id"]   == "CL001"
assert inv_db["status"]       == "GENERATED"
print(f"  ✓ Found in DB    : {inv_db['invoice_number']}")
print(f"  ✓ Total (AED)    : {inv_db['total_amount']:,.2f}")
print(f"  ✓ Total (INR)    : ₹{inv_db['total_amount_inr']:,.2f}")

# ── Test 3: Duplicate invoice blocked ─────────────────────────────────────────
print("\nTest 3: Duplicate invoice blocked")
with patch("engines.document_engine.call_gemini", return_value=MOCK_EXTRACTION):
    result_dup = pipeline.run(dummy_file)

assert result_dup.routed_to_review or result_dup.final_status in ("FAILED", "REVIEW_REQUIRED"), \
    f"Duplicate should be blocked, got: {result_dup.final_status}"
print(f"  ✓ Duplicate blocked → {result_dup.final_status}")

# ── Test 4: Low confidence → review queue ────────────────────────────────────
print("\nTest 4: Low confidence document → human review queue")
low_conf = {
    **MOCK_EXTRACTION,
    "confidence_scores": {
        "employee": 0.55, "client": 0.60, "contract": 0.58,
        "timesheet": 0.65, "overall": 0.59
    },
    "ambiguous_fields": [
        {"field": "employee_id", "reason": "Handwriting unclear",
         "extracted_value": "EMP1000?", "suggested_value": "EMP10001"}
    ],
}
dummy_file2 = config.UPLOADS_DIR / "test_low_conf.pdf"
dummy_file2.write_bytes(b"%PDF dummy")

with patch("engines.document_engine.call_gemini", return_value=low_conf):
    result_low = pipeline.run(dummy_file2)

assert result_low.routed_to_review
assert result_low.review_queue_id is not None
print(f"  ✓ Routed to review queue (id={result_low.review_queue_id})")
print(f"  ✓ Confidence     : {result_low.document.confidence:.2f}")

# ── Test 5: Bad file → pipeline fails gracefully ──────────────────────────────
print("\nTest 5: Unsupported file format fails gracefully")
bad_file = config.UPLOADS_DIR / "bad.docx"
bad_file.write_bytes(b"dummy")
result_bad = pipeline.run(bad_file)
assert result_bad.final_status == "FAILED"
assert not result_bad.success
print(f"  ✓ Bad file → {result_bad.final_status} (no crash)")

# ── Test 6: Audit log populated ───────────────────────────────────────────────
print("\nTest 6: Audit log populated")
log = DatabaseService.get_audit_log(result.invoice_number)
assert len(log) >= 1
event_types = [e["event_type"] for e in log]
assert "INVOICE_GENERATED" in event_types
print(f"  ✓ Audit entries  : {len(log)}")
print(f"  ✓ Events         : {event_types}")

# ── Test 7: Review queue contains low-conf item ───────────────────────────────
print("\nTest 7: Review queue state")
queue = DatabaseService.get_review_queue("PENDING")
assert len(queue) >= 1
print(f"  ✓ Pending reviews: {len(queue)}")
print(f"  ✓ Top item conf  : {queue[0]['confidence']:.2f}")
print(f"  ✓ Top item stage : {queue[0]['stage']}")

# ── Test 8: Dashboard stats ────────────────────────────────────────────────────
print("\nTest 8: Dashboard stats")
stats = DatabaseService.get_stats()
assert stats["total_invoices"] >= 1
assert stats["total_billed_inr"] > 0
assert stats["pending_review"] >= 1
print(f"  ✓ Total invoices : {stats['total_invoices']}")
print(f"  ✓ Total billed   : ₹{stats['total_billed_inr']:,.2f}")
print(f"  ✓ Pending review : {stats['pending_review']}")
print(f"  ✓ By status      : {stats['by_status']}")

# Cleanup
dummy_file.unlink(missing_ok=True)
dummy_file2.unlink(missing_ok=True)
bad_file.unlink(missing_ok=True)
config.DATABASE_PATH.unlink(missing_ok=True)

print("\n" + "=" * 60)
print("  PASS — End-to-End Pipeline Test (8 scenarios)")
print("=" * 60)
