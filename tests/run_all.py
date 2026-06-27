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
    ("Config",            "tests/test_config.py"),
    ("Models — schema",   "tests/test_models_schema.py"),
    ("Models — invoice",  "tests/test_models_invoice.py"),
    ("Models — validation","tests/test_models_validation.py"),
    ("Utils",             "tests/test_utils.py"),
    ("Phase 1 (full)",    "tests/test_phase1.py"),
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
