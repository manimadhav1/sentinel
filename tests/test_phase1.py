"""
Phase 1 Test — Foundation
Run: python tests/test_phase1.py
"""
import sys
import json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print('─'*50)

def ok(msg):  print(f"  ✓  {msg}")
def fail(msg): print(f"  ✗  {msg}"); sys.exit(1)

# ── 1. Config ──────────────────────────────────────────────────────────────────
section("1. Config")
import config
ok(f"BASE_DIR       = {config.BASE_DIR}")
ok(f"UPLOADS_DIR    = {config.UPLOADS_DIR}  exists={config.UPLOADS_DIR.exists()}")
ok(f"GST_RATE       = {config.GST_RATE}")
ok(f"GEMINI_MODEL   = {config.GEMINI_MODEL}")
ok(f"Confidence thresholds: auto={config.CONFIDENCE_AUTO_PROCEED} warn={config.CONFIDENCE_WARN_PROCEED} review={config.CONFIDENCE_HUMAN_REVIEW}")

# ── 2. Models — schema ────────────────────────────────────────────────────────
section("2. Models — schema.py")
from models.schema import Employee, Client, Contract, TimesheetEntry, ExtractedDocument

emp = Employee(employee_id="EMP001", name="Arjun Sharma", designation="Senior SWE")
ok(f"Employee        = {emp.name} ({emp.employee_id})")

cli = Client(client_id="CLI001", company_name="Infosys", country="India", currency="INR")
ok(f"Client          = {cli.company_name} ({cli.currency})")

con = Contract(
    contract_id="CON001", client_id="CLI001", employee_id="EMP001",
    billing_rate=1500.0, currency="INR", contracted_hours=160.0,
    start_date=date(2024, 1, 1), end_date=date(2026, 12, 31),
)
ok(f"Contract        = {con.contract_id}  rate={con.billing_rate}/hr  gst={con.gst_rate}")

entry = TimesheetEntry(date=date(2024, 6, 3), employee_id="EMP001", hours_worked=9.0, overtime_hours=1.0)
ok(f"TimesheetEntry  = {entry.date}  {entry.hours_worked}h  OT={entry.overtime_hours}h")

doc = ExtractedDocument(
    employee=emp, client=cli, contract=con,
    timesheet=[entry],
    billing_period_start=date(2024, 6, 1),
    billing_period_end=date(2024, 6, 30),
)
ok(f"ExtractedDocument built  entries={len(doc.timesheet)}")

# validator test
try:
    bad = TimesheetEntry(date=date(2024, 6, 3), employee_id="X", hours_worked=25.0)
    fail("Should have raised validation error for hours_worked > 24")
except Exception:
    ok("Pydantic validator correctly rejected hours_worked=25")

# ── 3. Models — invoice ────────────────────────────────────────────────────────
section("3. Models — invoice.py")
from models.invoice import LineItem, BillingResult, Invoice

li = LineItem(description="Regular hours", hours=160.0, rate=1500.0, amount=240000.0)
ok(f"LineItem        = {li.description}  {li.amount}")

billing = BillingResult(
    regular_hours=160.0, overtime_hours=8.0,
    regular_amount=240000.0, overtime_amount=18000.0,
    subtotal=258000.0, gst_amount=46440.0,
    total_amount=304440.0, currency="INR",
    total_amount_inr=304440.0,
    line_items=[li],
)
ok(f"BillingResult   = subtotal={billing.subtotal}  gst={billing.gst_amount}  total={billing.total_amount}")

invoice = Invoice(
    invoice_number="INV-2024-CLI001-0001",
    invoice_date=date(2024, 7, 1), due_date=date(2024, 7, 31),
    employee_id="EMP001", employee_name="Arjun Sharma",
    client_id="CLI001", client_name="Infosys",
    contract_id="CON001",
    billing_period_start=date(2024, 6, 1), billing_period_end=date(2024, 6, 30),
    billing=billing,
)
ok(f"Invoice         = {invoice.invoice_number}  status={invoice.status}")

# ── 4. Models — validation ────────────────────────────────────────────────────
section("4. Models — validation.py")
from models.validation import EngineResult, ValidationReport, AmbiguousField

result = EngineResult(stage="document", status="SUCCESS", confidence=0.97, data={"test": True})
ok(f"EngineResult    = status={result.status}  confidence={result.confidence}  ok={result.is_ok()}")

result.add_warning("Timezone inferred from country")
ok(f"After warning   = warnings={result.warnings}")

ambiguous = EngineResult(stage="document", status="SUCCESS", confidence=0.65)
ambiguous.flag_for_review("Employee name matched multiple records")
ok(f"Flagged result  = status={ambiguous.status}  review={ambiguous.requires_human_review}  next={ambiguous.next_action}")

report = ValidationReport()
report.add_check("GST_RATE_MATCH", True, "GST rate matches contract")
report.add_check("DUPLICATE_INVOICE", True, "No duplicate found")
report.add_check("CURRENCY_MATCH", False, "Currency mismatch: contract=INR doc=USD", severity="ERROR")
ok(f"ValidationReport= overall={report.overall}  checks={len(report.checks)}")

# ── 5. Utils ───────────────────────────────────────────────────────────────────
section("5. Utils")
from utils.helpers import convert_to_inr, format_currency, generate_invoice_number, calculate_due_date
from utils.file_utils import detect_file_type, is_supported
from utils.logger import get_logger

ok(f"100 USD → INR   = {convert_to_inr(100, 'USD')}")
ok(f"format_currency = {format_currency(304440.0, 'INR')}")
ok(f"invoice_number  = {generate_invoice_number('CLI001', 1)}")
ok(f"due_date        = {calculate_due_date(date(2024, 7, 1), 30)}")
ok(f"file type pdf   = {detect_file_type('invoice.pdf')}")
ok(f"file type xlsx  = {detect_file_type('sheet.xlsx')}")
ok(f"is_supported    = {is_supported('scan.jpg')}")

logger = get_logger("test_phase1")
logger.info("Logger working correctly")
ok("Logger initialised, wrote to runtime/sentinel.log")

# ── 6. Seed data ───────────────────────────────────────────────────────────────
section("6. Seed Data")
emp_path = config.MASTER_DATA_DIR / "employees.json"
cli_path = config.MASTER_DATA_DIR / "clients.json"
con1_path = config.CONTRACTS_DIR / "contract_001.json"
con2_path = config.CONTRACTS_DIR / "contract_002.json"

for p in [emp_path, cli_path, con1_path, con2_path]:
    if not p.exists(): fail(f"Missing seed file: {p}")
    data = json.loads(p.read_text())
    ok(f"{p.name:30s} loaded  ({type(data).__name__})")

# ── Done ───────────────────────────────────────────────────────────────────────
print(f"\n{'═'*50}")
print("  PHASE 1 COMPLETE — All checks passed")
print(f"{'═'*50}\n")
