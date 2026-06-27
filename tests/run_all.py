"""
Run all tests in order.
Usage: venv/bin/python tests/run_all.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable

tests = [
    ("Phase 1 — Config",              "tests/test_config.py"),
    ("Phase 1 — Models: schema",      "tests/test_models_schema.py"),
    ("Phase 1 — Models: invoice",     "tests/test_models_invoice.py"),
    ("Phase 1 — Models: validation",  "tests/test_models_validation.py"),
    ("Phase 1 — Utils",               "tests/test_utils.py"),
    ("Phase 1 — Full",                "tests/test_phase1.py"),
    ("Phase 2a — Gemini Service",     "tests/test_gemini_service.py"),
    ("Phase 2b — Document Engine",    "tests/test_document_engine.py"),
    ("Phase 3  — Processing Engine",  "tests/test_processing_engine.py"),
    ("Phase 4  — Validation Engine",  "tests/test_validation_engine.py"),
    ("Phase 5  — Invoice Engine",     "tests/test_invoice_engine.py"),
]

results = []
for name, path in tests:
    print(f"\n{'─'*50}")
    print(f"  Running: {name}")
    print('─'*50)
    result = subprocess.run([PYTHON, ROOT / path], cwd=ROOT)
    results.append((name, result.returncode == 0))

print(f"\n{'═'*50}")
print("  RESULTS")
print('═'*50)
all_passed = True
for name, passed in results:
    status = "PASS ✓" if passed else "FAIL ✗"
    print(f"  {status}  {name}")
    if not passed:
        all_passed = False

print('═'*50)
if all_passed:
    print("  All tests passed.")
else:
    print("  Some tests failed — check output above.")
    sys.exit(1)
