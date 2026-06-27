"""Test config.py — run: venv/bin/python tests/test_config.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config

print("Testing config.py...")
assert config.BASE_DIR.exists(), "BASE_DIR missing"
assert config.UPLOADS_DIR.exists(), "UPLOADS_DIR not created"
assert config.PDF_OUTPUT_DIR.exists(), "PDF_OUTPUT_DIR not created"
assert config.GST_RATE == 0.18, "GST_RATE wrong"
assert config.OVERTIME_MULTIPLIER == 1.5, "OVERTIME_MULTIPLIER wrong"
assert config.GEMINI_MODEL == "gemini-2.5-flash", "GEMINI_MODEL wrong"
assert "INR" in config.SUPPORTED_CURRENCIES, "INR missing"
assert config.CONFIDENCE_AUTO_PROCEED > config.CONFIDENCE_WARN_PROCEED, "Threshold order wrong"
assert config.CONFIDENCE_WARN_PROCEED > config.CONFIDENCE_HUMAN_REVIEW, "Threshold order wrong"
print("✓ All paths exist")
print("✓ All constants correct")
print("✓ Confidence thresholds ordered correctly")
print("PASS — config.py")
