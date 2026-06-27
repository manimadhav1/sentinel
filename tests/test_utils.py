"""Test utils/ — run: venv/bin/python tests/test_utils.py"""
import sys
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import (
    convert_to_inr, format_currency, generate_invoice_number,
    calculate_due_date, round_hours, safe_divide
)
from utils.file_utils import detect_file_type, is_supported, save_upload, safe_delete
from utils.logger import get_logger

print("Testing utils/...")

# helpers
assert convert_to_inr(1, "USD") == 83.5,  "USD conversion wrong"
assert convert_to_inr(1, "INR") == 1.0,   "INR conversion wrong"
assert convert_to_inr(1, "GBP") == 105.3, "GBP conversion wrong"
print("✓ convert_to_inr")

assert format_currency(1000, "INR") == "₹1,000.00"
assert format_currency(1000, "USD") == "$1,000.00"
print("✓ format_currency")

inv_num = generate_invoice_number("CLI001", 42)
assert inv_num.startswith("INV-")
assert "CLI001" in inv_num
assert "0042" in inv_num
print(f"✓ generate_invoice_number → {inv_num}")

due = calculate_due_date(date(2024, 7, 1), 30)
assert due == date(2024, 7, 31)
print("✓ calculate_due_date")

assert round_hours(8.567) == 8.57
print("✓ round_hours")

assert safe_divide(10, 2) == 5.0
assert safe_divide(10, 0) == 0.0   # no ZeroDivisionError
print("✓ safe_divide (including divide-by-zero)")

# file_utils
assert detect_file_type("report.pdf")  == "pdf"
assert detect_file_type("sheet.xlsx") == "excel"
assert detect_file_type("sheet.xls")  == "excel"
assert detect_file_type("data.csv")   == "csv"
assert detect_file_type("scan.png")   == "image"
assert detect_file_type("scan.jpg")   == "image"
assert detect_file_type("scan.jpeg")  == "image"
assert detect_file_type("unknown.xyz") == "unknown"
print("✓ detect_file_type — all formats")

assert is_supported("doc.pdf")    is True
assert is_supported("doc.xlsx")   is True
assert is_supported("img.png")    is True
assert is_supported("doc.docx")   is False
assert is_supported("doc.txt")    is False
print("✓ is_supported")

# save_upload and safe_delete
test_bytes = b"dummy file content"
saved_path = save_upload(test_bytes, "test_upload.pdf")
assert saved_path.exists(), "Saved file not found"
assert saved_path.suffix == ".pdf"
print(f"✓ save_upload → {saved_path.name}")
safe_delete(saved_path)
assert not saved_path.exists(), "File not deleted"
print("✓ safe_delete")

# logger
logger = get_logger("test_utils")
logger.info("Utils test logger working")
logger.warning("This is a warning")
print("✓ logger — INFO and WARNING logged")

print("PASS — utils/")
