"""
Test services/gemini_service.py
Run: venv/bin/python tests/test_gemini_service.py

Tests JSON parsing, image encoding, and tabular reading
without making a live Gemini API call.
"""
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.gemini_service import _extract_json, _encode_image, _read_tabular

print("Testing services/gemini_service.py...")

# ── 1. JSON extraction from clean response ────────────────────────────────────
sample = {
    "employee": {"name": "Arjun Sharma", "employee_id": "EMP001", "designation": "SWE",
                 "department": None, "email": None, "hsn_code": None},
    "client": {"company_name": "Infosys", "client_id": "CLI001", "country": "India",
               "currency": "INR", "gst_number": None, "timezone": None,
               "billing_address": None, "contact_email": None},
    "contract": {"contract_id": "CON001", "billing_rate": 1500, "currency": "INR",
                 "billing_type": "hourly", "contracted_hours": 160,
                 "overtime_allowed": True, "overtime_multiplier": 1.5,
                 "early_completion_policy": "pay_actual", "late_penalty_per_hour": 0,
                 "gst_applicable": True, "gst_rate": 0.18, "payment_terms_days": 30},
    "timesheet": [
        {"date": "2024-06-03", "employee_id": "EMP001",
         "hours_worked": 9.0, "task_description": "Backend dev", "overtime_hours": 1.0}
    ],
    "billing_period_start": "2024-06-01",
    "billing_period_end": "2024-06-30",
    "confidence_scores": {"employee": 0.98, "client": 0.97, "contract": 0.95,
                          "timesheet": 0.99, "overall": 0.97},
    "ambiguous_fields": [],
    "extraction_notes": "Clean typed PDF."
}

clean_json_str = json.dumps(sample)
result = _extract_json(clean_json_str)
assert result["employee"]["name"] == "Arjun Sharma"
assert result["confidence_scores"]["overall"] == 0.97
print("✓ _extract_json — clean JSON string")

# ── 2. JSON wrapped in markdown fences ────────────────────────────────────────
fenced = f"```json\n{clean_json_str}\n```"
result2 = _extract_json(fenced)
assert result2["client"]["company_name"] == "Infosys"
print("✓ _extract_json — strips ```json fences")

fenced2 = f"```\n{clean_json_str}\n```"
result3 = _extract_json(fenced2)
assert result3["contract"]["billing_rate"] == 1500
print("✓ _extract_json — strips ``` fences")

# ── 3. Image encoding ─────────────────────────────────────────────────────────
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    # minimal 1x1 PNG bytes
    f.write(bytes([
        0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,
        0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
        0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,
        0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,
        0xDE,0x00,0x00,0x00,0x0C,0x49,0x44,0x41,
        0x54,0x08,0xD7,0x63,0xF8,0xCF,0xC0,0x00,
        0x00,0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,
        0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,
        0x44,0xAE,0x42,0x60,0x82
    ]))
    tmp_png = Path(f.name)

mime, data = _encode_image(tmp_png)
assert mime == "image/png"
assert len(data) > 0
print(f"✓ _encode_image — mime={mime}  base64_len={len(data)}")
tmp_png.unlink()

# ── 4. Excel reading ──────────────────────────────────────────────────────────
try:
    import pandas as pd
    import openpyxl

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_xlsx = Path(f.name)

    df = pd.DataFrame({
        "Date": ["2024-06-03", "2024-06-04"],
        "Employee": ["Arjun Sharma", "Arjun Sharma"],
        "Hours": [8.0, 9.5],
        "Task": ["Backend", "Testing"],
    })
    df.to_excel(tmp_xlsx, index=False)

    text = _read_tabular(tmp_xlsx, "excel")
    assert "Arjun Sharma" in text
    assert "Hours" in text
    print(f"✓ _read_tabular excel — {len(text)} chars extracted")
    tmp_xlsx.unlink()
except ImportError:
    print("  (skipped Excel test — pandas/openpyxl not installed yet)")

# ── 5. Prompt length sanity ───────────────────────────────────────────────────
from services.gemini_service import EXTRACTION_PROMPT
assert len(EXTRACTION_PROMPT) > 500, "Prompt seems too short"
print(f"✓ EXTRACTION_PROMPT length = {len(EXTRACTION_PROMPT)} chars")

print("\nPASS — services/gemini_service.py")
print("NOTE: Live Gemini API call not tested here (requires API key + real file)")
print("      Full live test runs in test_document_engine.py with a sample file.")
