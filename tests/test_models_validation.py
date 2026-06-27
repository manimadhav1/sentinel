"""Test models/validation.py — run: venv/bin/python tests/test_models_validation.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.validation import EngineResult, ValidationReport, AmbiguousField

print("Testing models/validation.py...")

# EngineResult — success
r = EngineResult(stage="document", status="SUCCESS", confidence=0.97, data={"key": "val"})
assert r.is_ok() is True
assert r.next_action == "PROCEED"
print("✓ EngineResult SUCCESS")

# Add warning — should not block
r.add_warning("Timezone inferred")
assert r.is_ok() is True
assert len(r.warnings) == 1
print("✓ add_warning keeps is_ok=True")

# Add error — should block
r2 = EngineResult(stage="processing", status="SUCCESS", confidence=0.99)
r2.add_error("Contract expired")
assert r2.status == "FAILED"
assert r2.next_action == "ABORT"
assert r2.is_ok() is False
print("✓ add_error sets FAILED + ABORT")

# Flag for review
r3 = EngineResult(stage="document", status="SUCCESS", confidence=0.65)
r3.flag_for_review("Multiple employee matches")
assert r3.requires_human_review is True
assert r3.status == "AMBIGUOUS"
assert r3.next_action == "HUMAN_REVIEW"
print("✓ flag_for_review sets AMBIGUOUS + HUMAN_REVIEW")

# AmbiguousField
af = AmbiguousField(
    field_name="employee_name",
    extracted_value="A. Sharma",
    confidence=0.61,
    reason="Matched EMP001 and EMP004",
    suggested_value="EMP001",
)
assert af.confidence == 0.61
print("✓ AmbiguousField model")

# ValidationReport
report = ValidationReport()
report.add_check("EMPLOYEE_EXISTS", True, "Employee found")
report.add_check("CONTRACT_ACTIVE", True, "Contract valid")
assert report.overall == "VALID"
print("✓ ValidationReport — all pass → VALID")

report.add_check("DUPLICATE_INVOICE", False, "Duplicate found", severity="WARNING")
assert report.overall == "WARN"
print("✓ ValidationReport — WARNING → WARN")

report.add_check("GST_MATCH", False, "GST mismatch", severity="ERROR")
assert report.overall == "INVALID"
print("✓ ValidationReport — ERROR → INVALID")

assert len(report.checks) == 4
print("✓ All 4 checks recorded")

print("PASS — models/validation.py")
