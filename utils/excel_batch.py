"""
Excel batch parser — reads a multi-row timesheet and builds one synthetic
EngineResult per employee row.  No Gemini call needed for structured Excel.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from models.validation import EngineResult, AmbiguousField

# ── Master data cache ──────────────────────────────────────────────────────────
_BASE = Path(__file__).parent.parent / "data"

def _load_employees() -> dict:
    p = _BASE / "master_data" / "employees.json"
    if p.exists():
        return {e["employee_id"]: e for e in json.loads(p.read_text())}
    return {}

def _load_clients() -> dict:
    p = _BASE / "master_data" / "clients.json"
    if p.exists():
        return {c["client_id"]: c for c in json.loads(p.read_text())}
    return {}

def _load_contract(emp_id: str, cli_id: str) -> dict | None:
    p = _BASE / "contracts" / f"contract_CON-{emp_id}-{cli_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None

_CUST_MAP = {f"CUST{i:03d}": f"CL{i:03d}" for i in range(1, 20)}
_CUST_MAP.update({f"CUST{i:03d}": f"CL{i:03d}" for i in range(20, 50)})

def _norm_client(raw: str) -> str:
    v = str(raw).strip().upper()
    return _CUST_MAP.get(v, v)

# ── Column synonym map ─────────────────────────────────────────────────────────
# Maps canonical name → list of acceptable column header variants (lowercase)
_COL = {
    "employee_id":    ["employee_id", "emp_id", "staff_no", "emp no", "employee id",
                       "empid", "worker_id", "resource_id", "staffid"],
    "employee_name":  ["employee_name", "name", "employee name", "staff_name",
                       "worker_name", "emp_name", "resource_name", "full_name"],
    "client_id":      ["client_id", "customer_code", "client_code", "cust_code",
                       "account_code", "client id", "customer id", "cust id",
                       "customer_id", "clientcode"],
    "client_name":    ["client_name", "company_name", "customer_name", "client name",
                       "company", "organization", "organisation"],
    "period_start":   ["period_start", "billing_start", "start_date", "from_date",
                       "period from", "period_from", "date_from", "billing period start"],
    "period_end":     ["period_end", "billing_end", "end_date", "to_date",
                       "period to", "period_to", "date_to", "billing period end"],
    "hours_worked":   ["hours_worked", "hours", "total_hours", "days_worked",
                       "working_days", "days", "billable_hours", "hrs_worked",
                       "regular_hours", "work_days"],
    "overtime_hours": ["overtime_hours", "ot_hours", "overtime", "extra_hours",
                       "ot hrs", "ovt_hours"],
    "billing_rate":   ["billing_rate", "hourly_rate", "rate", "rate_per_hour",
                       "hourly rate", "aed_rate", "rate_aed", "salary", "basic_salary",
                       "monthly_salary", "pay_rate"],
    "currency":       ["currency", "cur", "curr", "billing_currency"],
    "designation":    ["designation", "job_title", "title", "role", "position"],
}

def _find_col(df_cols: list[str], canonical: str) -> str | None:
    """Return the actual DataFrame column name matching a canonical field."""
    lower_map = {c.lower().strip(): c for c in df_cols}
    for alias in _COL.get(canonical, []):
        if alias in lower_map:
            return lower_map[alias]
    return None

def _get(row, col_name: str | None, default=None):
    if col_name is None:
        return default
    val = row.get(col_name)
    if pd.isna(val) if hasattr(val, '__class__') and val.__class__.__name__ in ('float','NAType') else False:
        return default
    return val if val is not None else default

def _parse_date(val, fallback: date) -> date:
    if val is None:
        return fallback
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except Exception:
        pass
    try:
        return datetime.strptime(str(val).strip(), "%d/%m/%Y").date()
    except Exception:
        pass
    try:
        return datetime.strptime(str(val).strip(), "%d-%m-%Y").date()
    except Exception:
        pass
    return fallback

def _to_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "").strip())
    except Exception:
        return default


# ── Main entry point ───────────────────────────────────────────────────────────

def is_multi_row_excel(file_path: str | Path) -> bool:
    """Return True if the file is an Excel with ≥2 data rows."""
    fp = Path(file_path)
    if fp.suffix.lower() not in (".xlsx", ".xls"):
        return False
    try:
        df = pd.read_excel(fp, nrows=5)
        return len(df) >= 2
    except Exception:
        return False


def parse_batch(file_path: str | Path) -> list[EngineResult]:
    """
    Parse a multi-row Excel and return one EngineResult per employee row.
    Each result is equivalent to what DocumentEngine would return for that row,
    but built from Python directly (no Gemini call).
    """
    fp = Path(file_path)
    df = pd.read_excel(fp)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")

    cols = list(df.columns)

    # Map canonical → actual column
    mapped = {k: _find_col(cols, k) for k in _COL}

    employees = _load_employees()
    clients   = _load_clients()

    # Default period = current month
    today = date.today()
    default_start = date(today.year, today.month, 1)
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    default_end = date(today.year, today.month, last_day)

    results = []

    for idx, row in df.iterrows():
        row = row.to_dict()
        warnings: list[str] = []
        ambiguous: list[AmbiguousField] = []

        # ── Employee ────────────────────────────────────────────────────────────
        raw_emp_id   = str(_get(row, mapped["employee_id"], "UNKNOWN")).strip().upper()
        raw_emp_name = str(_get(row, mapped["employee_name"], "")).strip()
        designation  = str(_get(row, mapped["designation"], "")).strip()

        emp_id = raw_emp_id if raw_emp_id not in ("", "NAN", "NONE") else "UNKNOWN"

        # Name lookup from master if name missing
        emp_master = employees.get(emp_id, {})
        emp_name = raw_emp_name or emp_master.get("name", "UNKNOWN")
        if not designation:
            designation = emp_master.get("designation", "")

        # ── Client ─────────────────────────────────────────────────────────────
        raw_cli_id   = str(_get(row, mapped["client_id"], "UNKNOWN")).strip()
        raw_cli_name = str(_get(row, mapped["client_name"], "")).strip()

        cli_id = _norm_client(raw_cli_id) if raw_cli_id not in ("", "NAN", "NONE") else "UNKNOWN"
        cli_master = clients.get(cli_id, {})
        cli_name   = raw_cli_name or cli_master.get("company_name", "UNKNOWN")
        currency   = str(_get(row, mapped["currency"], cli_master.get("currency", "AED"))).strip().upper()
        if not currency or currency in ("NAN", "NONE"):
            currency = "AED"

        # ── Contract ────────────────────────────────────────────────────────────
        contract = _load_contract(emp_id, cli_id)
        contract_id = f"CON-{emp_id}-{cli_id}"

        raw_rate = _get(row, mapped["billing_rate"])
        billing_rate = _to_float(raw_rate) if raw_rate is not None else 0.0

        if billing_rate <= 0 and contract:
            billing_rate = contract.get("billing_rate", 0.0)
        if billing_rate <= 0:
            warnings.append(f"Row {idx+2}: billing rate missing — cannot calculate invoice")

        contract_start = date(today.year, 1, 1)
        contract_end   = date(today.year, 12, 31)
        if contract:
            try:
                contract_start = datetime.strptime(contract["start_date"], "%Y-%m-%d").date()
                contract_end   = datetime.strptime(contract["end_date"], "%Y-%m-%d").date()
            except Exception:
                pass

        # ── Billing period ──────────────────────────────────────────────────────
        period_start = _parse_date(_get(row, mapped["period_start"]), default_start)
        period_end   = _parse_date(_get(row, mapped["period_end"]), default_end)

        # ── Hours ───────────────────────────────────────────────────────────────
        raw_hours = _get(row, mapped["hours_worked"])
        total_hours = _to_float(raw_hours) if raw_hours is not None else 0.0

        # If "days worked" column detected, value is already in days
        days_col = mapped.get("hours_worked")
        is_days_col = days_col and any(x in (days_col or "").lower() for x in ("day", "days"))
        if is_days_col:
            # Convert to hours and remember how many working days
            working_days = int(total_hours)
            total_hours  = total_hours * 8.0
        else:
            # Derive working days from total hours (8h/day)
            working_days = max(1, int(round(total_hours / 8)))

        ot_hours = _to_float(_get(row, mapped["overtime_hours"], 0.0))

        # Fallback: derive hours from period if missing
        if total_hours <= 0:
            working_days = 22
            total_hours  = 22 * 8.0
            warnings.append(f"Row {idx+2}: hours_worked not found — estimated {total_hours:.0f}h from period")

        # ── Build daily timesheet entries (max 24h/day per model constraint) ────
        # Spread total hours evenly across working days in the billing period
        import calendar as _cal

        # Collect weekdays in the period
        weekdays: list[date] = []
        cur = period_start
        while cur <= period_end:
            if cur.weekday() < 5:  # Mon–Fri
                weekdays.append(cur)
            cur = date.fromordinal(cur.toordinal() + 1)

        if not weekdays:
            weekdays = [period_end]

        # Use actual weekday count or capped at working_days
        n_days = min(working_days, len(weekdays))
        if n_days == 0:
            n_days = len(weekdays)

        daily_hours = round(total_hours / n_days, 2)
        daily_hours = min(daily_hours, 8.0)  # cap at 8h regular per day

        # Distribute OT: put it on the last working day (or spread if large)
        ot_per_day = 0.0
        ot_last    = 0.0
        if ot_hours > 0:
            if ot_hours / n_days <= 4.0:
                ot_last = round(ot_hours, 2)
            else:
                ot_per_day = round(ot_hours / n_days, 2)

        timesheet = []
        for i, work_date in enumerate(weekdays[:n_days]):
            is_last = (i == n_days - 1)
            ot = ot_last if (is_last and ot_last > 0) else ot_per_day
            timesheet.append({
                "date": work_date.isoformat(),
                "employee_id": emp_id,
                "hours_worked": daily_hours,
                "overtime_hours": ot,
                "task_description": "Client services",
            })

        # ── Confidence scoring ──────────────────────────────────────────────────
        # Structured Excel = high base confidence; deduct for unknowns
        base_conf = 0.95
        if emp_id == "UNKNOWN":
            base_conf -= 0.15
            ambiguous.append(AmbiguousField(
                field_name="employee.employee_id",
                extracted_value=raw_emp_id,
                confidence=0.3,
                reason="Employee ID not found in master records",
            ))
        if cli_id == "UNKNOWN":
            base_conf -= 0.15
            ambiguous.append(AmbiguousField(
                field_name="client.client_id",
                extracted_value=raw_cli_id,
                confidence=0.3,
                reason="Client ID not found in master records",
            ))
        if billing_rate <= 0:
            base_conf -= 0.20
        if not contract:
            base_conf -= 0.05
            warnings.append(f"Contract {contract_id} not on file — will use extracted rate")

        confidence = max(0.30, round(base_conf, 2))

        # ── Build EngineResult ─────────────────────────────────────────────────
        result = EngineResult(
            stage="document",
            status="SUCCESS" if confidence >= 0.50 else "AMBIGUOUS",
            confidence=confidence,
            data={
                "employee": {
                    "employee_id": emp_id,
                    "name": emp_name,
                    "designation": designation,
                    "department": emp_master.get("department", ""),
                    "email": emp_master.get("email", ""),
                    "hsn_code": None,
                },
                "client": {
                    "client_id": cli_id,
                    "company_name": cli_name,
                    "billing_address": cli_master.get("billing_address", ""),
                    "country": cli_master.get("country", "UAE"),
                    "currency": currency,
                    "gst_number": cli_master.get("gst_number"),
                    "timezone": cli_master.get("timezone", "Asia/Dubai"),
                    "contact_email": cli_master.get("contact_email", ""),
                },
                "contract": {
                    "contract_id": contract_id,
                    "client_id": cli_id,
                    "employee_id": emp_id,
                    "billing_rate": billing_rate,
                    "currency": currency,
                    "billing_type": (contract or {}).get("billing_type", "hourly"),
                    "contracted_hours": (contract or {}).get("contracted_hours"),
                    "start_date": contract_start.isoformat(),
                    "end_date": contract_end.isoformat(),
                    "overtime_allowed": (contract or {}).get("overtime_allowed", True),
                    "overtime_multiplier": (contract or {}).get("overtime_multiplier", 1.5),
                    "early_completion_policy": "pay_actual",
                    "late_penalty_per_hour": 0.0,
                    "gst_applicable": (contract or {}).get("gst_applicable", False),
                    "gst_rate": (contract or {}).get("gst_rate", 0.0),
                    "payment_terms_days": (contract or {}).get("payment_terms_days", 30),
                },
                "timesheet": timesheet,
                "billing_period_start": period_start.isoformat(),
                "billing_period_end": period_end.isoformat(),
                "source_file": str(fp),
            },
            warnings=warnings,
            ambiguous_fields=ambiguous,
            metadata={
                "source": "excel_batch",
                "row_index": int(idx) + 2,
                "source_file": str(fp),
                "confidence_scores": {
                    "employee": 0.95 if emp_id != "UNKNOWN" else 0.40,
                    "client":   0.95 if cli_id != "UNKNOWN" else 0.40,
                    "contract": 0.90 if contract else 0.70,
                    "timesheet": 0.90 if total_hours > 0 else 0.50,
                },
            },
        )
        results.append(result)

    return results
