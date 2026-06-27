"""
One-time script: seeds TASC Excel data into master data JSONs.
Run: venv/bin/python tests/seed_tasc_master.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from config import MASTER_DATA_DIR, CONTRACTS_DIR

SAMPLE_FILE = Path("/Users/madhavan/Downloads/For Contestants/TASC_Sample_Database_vF.xlsx")
xl = pd.ExcelFile(SAMPLE_FILE)

# ── Employees ──────────────────────────────────────────────────────────────────
emp_df = xl.parse("Employees")
employees = []
for _, r in emp_df.iterrows():
    employees.append({
        "employee_id": str(r["Emp ID"]),
        "name": str(r["Full Name"]),
        "designation": str(r["Job Title"]),
        "department": str(r["Department"]),
        "email": str(r["Email"]),
        "hsn_code": None,
    })

(MASTER_DATA_DIR / "employees.json").write_text(json.dumps(employees, indent=2))
print(f"✓ Seeded {len(employees)} employees")

# ── Clients ────────────────────────────────────────────────────────────────────
cli_df = xl.parse("Customers")
clients = []
for _, r in cli_df.iterrows():
    clients.append({
        "client_id": str(r["Client Code"]),
        "company_name": str(r["Client Name"]),
        "billing_address": str(r["City"]),
        "country": "UAE",
        "currency": "AED",
        "gst_number": None,
        "timezone": "Asia/Dubai",
        "contact_email": str(r["Contact Email"]),
    })

(MASTER_DATA_DIR / "clients.json").write_text(json.dumps(clients, indent=2))
print(f"✓ Seeded {len(clients)} clients")

# ── Contracts — one per employee-client pair from payroll ─────────────────────
pay_df = xl.parse("Payroll_June2026")
contracts = []
seen = set()
for _, r in pay_df.iterrows():
    emp_id    = str(r["Emp ID"])
    client_id = str(r["Client Code"])
    key       = (emp_id, client_id)
    if key in seen:
        continue
    seen.add(key)

    working_days = int(r["Working Days"]) if int(r["Working Days"]) > 0 else 20
    gross        = float(r["Gross"])
    hourly_rate  = round(gross / (working_days * 8), 4)

    contracts.append({
        "contract_id": f"CON-{emp_id}-{client_id}",
        "client_id": client_id,
        "employee_id": emp_id,
        "billing_rate": hourly_rate,
        "currency": str(r["Currency"]),
        "billing_type": "hourly",
        "contracted_hours": working_days * 8.0,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "overtime_allowed": True,
        "overtime_multiplier": 1.5,
        "early_completion_policy": "pay_actual",
        "late_penalty_per_hour": 0.0,
        "gst_applicable": False,
        "gst_rate": 0.0,
        "payment_terms_days": 30,
    })

# Write as individual contract files
for con in contracts:
    fname = f"contract_{con['contract_id']}.json"
    (CONTRACTS_DIR / fname).write_text(json.dumps(con, indent=2))

print(f"✓ Seeded {len(contracts)} contracts")
print("\nMaster data ready. Re-run test_tasc_sample.py to see VALID results.")
