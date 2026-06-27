"""
Seed TASC Excel employees into master data.
Maps TASC payroll IDs (EMP001, CUST001) → Sentinel master IDs.
Run once: venv/bin/python tests/seed_tasc_excel_employees.py
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR      = Path("data")
MASTER_DIR    = DATA_DIR / "master_data"
CONTRACTS_DIR = DATA_DIR / "contracts"

# ── TASC Excel rows ────────────────────────────────────────────────────────────
TASC_ROWS = [
    {"employee_id": "EMP001", "name": "Rahul Mehta",       "customer_code": "CUST001", "days_worked": 24, "basic_salary": 8500},
    {"employee_id": "EMP002", "name": "Nadia Al Zaabi",    "customer_code": "CUST005", "days_worked": 19, "basic_salary": 7200},
    {"employee_id": "EMP003", "name": "James Okonkwo",     "customer_code": "CUST002", "days_worked": 22, "basic_salary": 11000},
    {"employee_id": "EMP005", "name": "Omar Al Hashimi",   "customer_code": "CUST003", "days_worked": 26, "basic_salary": 14000},
    {"employee_id": "EMP006", "name": "Sunita Verma",      "customer_code": "CUST003", "days_worked": 30, "basic_salary": 9500},
    {"employee_id": "EMP008", "name": "Aisha Bint Khalid", "customer_code": "CUST004", "days_worked": 20, "basic_salary": 12500},
    {"employee_id": "EMP010", "name": "Meera Pillai",      "customer_code": "CUST005", "days_worked": 21, "basic_salary": 9200},
    {"employee_id": "EMP011", "name": "Hassan Al Muhairi", "customer_code": "CUST006", "days_worked": 25, "basic_salary": 10500},
    {"employee_id": "EMP013", "name": "Vikram Singh",      "customer_code": "CUST007", "days_worked": 23, "basic_salary": 13000},
    {"employee_id": "EMP099", "name": "Ghost Employee",    "customer_code": "CUST001", "days_worked": 18, "basic_salary": 5000},
]

# Map CUST00X → CL00X (direct number match)
CUST_TO_CL = {f"CUST00{i}": f"CL00{i}" for i in range(1, 10)}

# ── Load existing master data ──────────────────────────────────────────────────
emp_file    = MASTER_DIR / "employees.json"
employees   = json.loads(emp_file.read_text())
existing_ids = {e["employee_id"] for e in employees}

added_emps      = 0
added_contracts = 0

for row in TASC_ROWS:
    eid      = row["employee_id"]
    cust     = row["customer_code"]
    cl_id    = CUST_TO_CL.get(cust, "CL001")
    salary   = row["basic_salary"]
    days     = row["days_worked"]
    hours    = days * 8
    rate     = round(salary / hours, 4)  # hourly billing rate from basic salary

    # ── Add employee to master ─────────────────────────────────────────────────
    if eid not in existing_ids:
        employees.append({
            "employee_id":  eid,
            "name":         row["name"],
            "designation":  "Consultant",
            "department":   "Operations",
            "email":        f"{eid.lower()}@tasc.ae",
            "hsn_code":     None,
        })
        existing_ids.add(eid)
        added_emps += 1
        print(f"  + Employee: {eid} — {row['name']}")

    # ── Create contract file ───────────────────────────────────────────────────
    contract_id   = f"CON-{eid}-{cl_id}"
    contract_file = CONTRACTS_DIR / f"contract_{contract_id}.json"

    if not contract_file.exists():
        contract = {
            "contract_id":              contract_id,
            "client_id":                cl_id,
            "employee_id":              eid,
            "billing_rate":             rate,
            "currency":                 "AED",
            "billing_type":             "hourly",
            "contracted_hours":         float(hours),
            "start_date":               "2026-01-01",
            "end_date":                 "2026-12-31",
            "overtime_allowed":         True,
            "overtime_multiplier":      1.5,
            "early_completion_policy":  "pay_actual",
            "late_penalty_per_hour":    0.0,
            "gst_applicable":           False,
            "gst_rate":                 0.0,
            "payment_terms_days":       30,
        }
        contract_file.write_text(json.dumps(contract, indent=2))
        added_contracts += 1
        print(f"  + Contract: {contract_id}  rate={rate} AED/h  hours={hours}")

# Save updated employees
emp_file.write_text(json.dumps(employees, indent=2))

print(f"\n✓ Seeded {added_emps} employees, {added_contracts} contracts")
print(f"  Total employees in master: {len(employees)}")
