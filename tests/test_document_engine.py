"""
Test engines/document_engine.py
Run: venv/bin/python tests/test_document_engine.py

Uses a mock Gemini response — no API key required.
"""
import sys
import json
from pathlib import Path
from datetime import date
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engines.document_engine import DocumentEngine

print("Testing engines/document_engine.py...")

# ── Shared mock Gemini response ────────────────────────────────────────────────
MOCK_RESPONSE = {
    "employee": {
        "employee_id": "EMP001", "name": "Arjun Sharma",
        "designation": "Senior SWE", "department": "Engineering",
        "email": "arjun@outsource.com", "hsn_code": "998314"
    },
    "client": {
        "client_id": "CLI001", "company_name": "Infosys Ltd",
        "billing_address": "Bangalore", "country": "India",
        "currency": "INR", "gst_number": "29AABCI1682H1ZK",
        "timezone": "Asia/Kolkata", "contact_email": "billing@infosys.com"
    },
    "contract": {
        "contract_id": "CON001", "billing_rate": 1500, "currency": "INR",
        "billing_type": "hourly", "contracted_hours": 160,
        "start_date": "2024-01-01", "end_date": "2026-12-31",
        "overtime_allowed": True, "overtime_multiplier": 1.5,
        "early_completion_policy": "pay_actual", "late_penalty_per_hour": 0,
        "gst_applicable": True, "gst_rate": 0.18, "payment_terms_days": 30
    },
    "timesheet": [
        {"date": "2024-06-03", "employee_id": "EMP001",
         "hours_worked": 9.0, "task_description": "Backend dev", "overtime_hours": 1.0},
        {"date": "2024-06-04", "employee_id": "EMP001",
         "hours_worked": 8.0, "task_description": "Code review", "overtime_hours": 0.0},
    ],
    "billing_period_start": "2024-06-01",
    "billing_period_end": "2024-06-30",
    "confidence_scores": {
        "employee": 0.98, "client": 0.97, "contract": 0.96,
        "timesheet": 0.99, "overall": 0.97
    },
    "ambiguous_fields": [],
    "extraction_notes": "Clean typed document."
}

# ── 1. Happy path — high confidence ───────────────────────────────────────────
# Create a minimal dummy PDF so file-type detection passes
sample_file = Path("runtime/uploads/test_sample.pdf")
sample_file.write_bytes(b"%PDF-1.4 dummy content for testing")

with patch("engines.document_engine.call_gemini", return_value=MOCK_RESPONSE):
    result = DocumentEngine.process(sample_file)

assert result.status == "SUCCESS", f"Expected SUCCESS got {result.status}"
assert result.confidence == 0.97
assert result.requires_human_review is False
assert result.next_action == "PROCEED"
assert result.data is not None

doc = result.data
assert doc["employee"]["name"] == "Arjun Sharma"
assert doc["client"]["company_name"] == "Infosys Ltd"
assert doc["contract"]["billing_rate"] == 1500.0
assert len(doc["timesheet"]) == 2
assert doc["timesheet"][0]["hours_worked"] == 9.0
print("✓ Happy path — high confidence, auto-proceed")

# ── 2. Low confidence → human review ──────────────────────────────────────────
low_conf_response = {**MOCK_RESPONSE,
    "confidence_scores": {
        "employee": 0.65, "client": 0.70, "contract": 0.60,
        "timesheet": 0.72, "overall": 0.65
    },
    "ambiguous_fields": [
        {"field": "employee_id", "reason": "Handwriting unclear",
         "extracted_value": "EMP00?", "suggested_value": "EMP001"}
    ]
}

with patch("engines.document_engine.call_gemini", return_value=low_conf_response):
    result2 = DocumentEngine.process(sample_file)

assert result2.requires_human_review is True
assert result2.status == "AMBIGUOUS"
assert result2.next_action == "HUMAN_REVIEW"
assert len(result2.ambiguous_fields) == 1
assert result2.ambiguous_fields[0].field_name == "employee_id"
print("✓ Low confidence → human review flagged correctly")

# ── 3. Very low confidence → high priority ────────────────────────────────────
very_low = {**MOCK_RESPONSE,
    "confidence_scores": {**MOCK_RESPONSE["confidence_scores"], "overall": 0.45}
}

with patch("engines.document_engine.call_gemini", return_value=very_low):
    result3 = DocumentEngine.process(sample_file)

assert result3.requires_human_review is True
assert result3.metadata.get("priority") == "HIGH"
print("✓ Very low confidence → HIGH priority review")

# ── 4. File not found ─────────────────────────────────────────────────────────
result4 = DocumentEngine.process("nonexistent_file.pdf")
assert result4.status == "FAILED"
assert result4.next_action == "ABORT"
assert len(result4.errors) > 0
print("✓ File not found → FAILED gracefully")

# ── 5. Unsupported file format ────────────────────────────────────────────────
# create a dummy .docx file
dummy = Path("runtime/uploads/test.docx")
dummy.write_bytes(b"dummy")
result5 = DocumentEngine.process(dummy)
assert result5.status == "FAILED"
assert "Unsupported" in result5.errors[0]
dummy.unlink()
print("✓ Unsupported format → FAILED gracefully")

# ── 6. Gemini failure → handled gracefully ────────────────────────────────────
with patch("engines.document_engine.call_gemini", side_effect=Exception("API timeout")):
    result6 = DocumentEngine.process(sample_file)

assert result6.status == "FAILED"
assert "Gemini extraction failed" in result6.errors[0]
print("✓ Gemini failure → FAILED gracefully, no crash")

# ── 7. Partial data — missing fields default gracefully ───────────────────────
partial = {
    "employee": {"name": "Unknown Person"},
    "client": {"company_name": "Some Client"},
    "contract": {"billing_rate": 500},
    "timesheet": [],
    "billing_period_start": "2024-06-01",
    "billing_period_end": "2024-06-30",
    "confidence_scores": {"overall": 0.82},
    "ambiguous_fields": [],
}

with patch("engines.document_engine.call_gemini", return_value=partial):
    result7 = DocumentEngine.process(sample_file)

assert result7.status in ("SUCCESS", "AMBIGUOUS")
assert result7.data["employee"]["employee_id"] == "UNKNOWN"
print("✓ Partial data — missing fields default gracefully")

sample_file.unlink(missing_ok=True)
print("\nPASS — engines/document_engine.py")
