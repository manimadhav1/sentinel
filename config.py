import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
DATA_DIR        = BASE_DIR / "data"
RUNTIME_DIR     = BASE_DIR / "runtime"
OUTPUT_DIR      = BASE_DIR / "output"

UPLOADS_DIR     = RUNTIME_DIR / "uploads"
PROCESSED_DIR   = RUNTIME_DIR / "processed"
INVOICES_DIR    = RUNTIME_DIR / "invoices"
DATABASE_PATH   = RUNTIME_DIR / "database.db"

CONTRACTS_DIR   = DATA_DIR / "contracts"
MASTER_DATA_DIR = DATA_DIR / "master_data"

PDF_OUTPUT_DIR   = OUTPUT_DIR / "pdf"
EXCEL_OUTPUT_DIR = OUTPUT_DIR / "excel"

# ── Gemini ─────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.5-flash"

# ── Confidence thresholds ──────────────────────────────────────────────────────
CONFIDENCE_AUTO_PROCEED    = 0.95   # green — fully automatic
CONFIDENCE_WARN_PROCEED    = 0.80   # yellow — proceed with warnings attached
CONFIDENCE_HUMAN_REVIEW    = 0.60   # orange — route to human review queue
# anything below CONFIDENCE_HUMAN_REVIEW → high-priority human review

# ── Business rules ─────────────────────────────────────────────────────────────
GST_RATE               = 0.18   # 18%
OVERTIME_MULTIPLIER    = 1.5
STANDARD_DAILY_HOURS   = 8
STANDARD_WEEKLY_HOURS  = 40

# ── Currency ───────────────────────────────────────────────────────────────────
SUPPORTED_CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"]

CURRENCY_SYMBOLS = {
    "INR": "₹", "USD": "$", "EUR": "€",
    "GBP": "£", "AED": "د.إ", "SGD": "S$",
}

# Exchange rates to INR (approximate demo values)
EXCHANGE_RATES_TO_INR = {
    "INR": 1.0, "USD": 83.5, "EUR": 90.2,
    "GBP": 105.3, "AED": 22.7, "SGD": 61.8,
}

# ── Invoice numbering ──────────────────────────────────────────────────────────
INVOICE_PREFIX = "INV"

# ── Supported upload formats ───────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".webp"]

# ── Ensure runtime dirs exist on import ───────────────────────────────────────
for _d in [UPLOADS_DIR, PROCESSED_DIR, INVOICES_DIR,
           PDF_OUTPUT_DIR, EXCEL_OUTPUT_DIR, CONTRACTS_DIR, MASTER_DATA_DIR]:
    _d.mkdir(parents=True, exist_ok=True)
