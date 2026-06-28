from __future__ import annotations
import json
import calendar
from datetime import date, datetime
from pathlib import Path

from models.schema import (
    Employee, Client, Contract, TimesheetEntry, ExtractedDocument
)
from models.validation import EngineResult, AmbiguousField
from services.gemini_service import call_gemini, verify_ambiguous_fields
from utils.file_utils import detect_file_type, is_supported
from utils.logger import get_logger
from config import (
    CONFIDENCE_AUTO_PROCEED, CONTRACTS_DIR, MASTER_DATA_DIR,
)

logger = get_logger("document_engine")

# CUST001→CL001 … CUST020→CL020 applied in Python (don't rely on Gemini prompt alone)
_CUST_MAP = {f"CUST{str(i).zfill(3)}": f"CL{str(i).zfill(3)}" for i in range(1, 21)}

# Fields that are optional / can be backfilled — never penalise confidence for these
NON_CRITICAL = {
    "employee.hsn_code", "employee.department", "employee.email",
    "client.company_name", "client.billing_address", "client.gst_number",
    "client.timezone", "client.contact_email", "client.country", "client.currency",
    "contract.billing_rate", "contract.billing_type", "contract.contracted_hours",
    "contract.start_date", "contract.end_date", "contract.contract_id",
    "contract.overtime_allowed", "contract.overtime_multiplier",
    "contract.early_completion_policy", "contract.late_penalty_per_hour",
    "contract.gst_applicable", "contract.gst_rate", "contract.payment_terms_days",
    "billing_period_start", "billing_period_end",
    "timesheet[*].task_description", "timesheet[].task_description",
    "timesheet*.task_description", "timesheet",
}


def _normalise_client_id(raw_id: str | None) -> str:
    """CUST00X → CL00X; strip whitespace; uppercase."""
    if not raw_id:
        return "UNKNOWN"
    v = str(raw_id).strip().upper()
    return _CUST_MAP.get(v, v)


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


class DocumentEngine:

    @staticmethod
    def process(file_path: str | Path) -> EngineResult:
        file_path = Path(file_path)
        result = EngineResult(stage="document", status="SUCCESS", confidence=1.0)

        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result
        if not is_supported(file_path):
            result.add_error(f"Unsupported file format: {file_path.suffix}")
            return result

        file_type = detect_file_type(file_path)
        result.metadata["file_name"] = file_path.name
        result.metadata["file_type"] = file_type

        # ── Gemini extraction ──────────────────────────────────────────────────
        try:
            raw = call_gemini(file_path, file_type)
        except Exception as e:
            result.add_error(f"Gemini extraction failed: {str(e)}")
            return result

        # ── Confidence from critical fields only ───────────────────────────────
        scores = raw.get("confidence_scores", {})
        critical_scores = [
            float(scores[k]) for k in ["employee", "client", "contract", "timesheet"]
            if k in scores
        ]
        overall_confidence = (
            sum(critical_scores) / len(critical_scores)
            if critical_scores else float(scores.get("overall", 0.5))
        )
        result.confidence = overall_confidence
        result.metadata["confidence_scores"] = scores
        result.metadata["extraction_notes"] = raw.get("extraction_notes", "")

        # ── Flag ambiguous CRITICAL fields only ────────────────────────────────
        for af in raw.get("ambiguous_fields", []):
            field_name = af.get("field", "unknown")
            if field_name in NON_CRITICAL or "task_description" in field_name:
                continue
            result.ambiguous_fields.append(AmbiguousField(
                field_name=field_name,
                extracted_value=af.get("extracted_value"),
                confidence=float(scores.get(field_name, 0.5)),
                reason=af.get("reason", ""),
                suggested_value=af.get("suggested_value"),
            ))

        # ── Backfill missing fields from master data ───────────────────────────
        raw, resolved_fields = DocumentEngine._backfill_from_master(raw)
        if resolved_fields:
            result.ambiguous_fields = [
                af for af in result.ambiguous_fields
                if not any(f in af.field_name for f in resolved_fields)
            ]
            boost = min(0.15, 0.02 * len(resolved_fields))
            result.confidence = min(1.0, result.confidence + boost)
            overall_confidence = result.confidence
            result.add_warning(
                f"Fields backfilled from master data: {', '.join(resolved_fields)}"
            )

        # ── Second-pass verification for ambiguous critical fields ─────────────
        critical_ambiguous = [
            af for af in result.ambiguous_fields
            if af.field_name not in NON_CRITICAL
            and "task_description" not in af.field_name
        ]
        if critical_ambiguous:
            verification = verify_ambiguous_fields(
                file_path=file_path,
                file_type=file_type,
                extraction=raw,
                ambiguous_fields=[
                    {
                        "field": af.field_name,
                        "extracted_value": af.extracted_value,
                        "confidence": af.confidence,
                        "reason": af.reason,
                        "suggested_value": af.suggested_value,
                    }
                    for af in critical_ambiguous
                ],
            )
            corrections = verification.get("corrections", {})
            if corrections:
                raw = DocumentEngine._apply_corrections(raw, corrections)
                result.metadata["verification_corrections"] = corrections
                result.metadata["verification_notes"] = verification.get("verification_notes", "")
                # Re-score confidence with corrections applied
                verified_fields = [
                    f for f, c in corrections.items()
                    if float(c.get("confidence", 0)) >= 0.80
                ]
                if verified_fields:
                    boost = min(0.10, 0.025 * len(verified_fields))
                    result.confidence = min(1.0, result.confidence + boost)
                    overall_confidence = result.confidence
                    # Remove now-resolved fields from ambiguous list
                    result.ambiguous_fields = [
                        af for af in result.ambiguous_fields
                        if not any(
                            vf in af.field_name
                            for vf in verified_fields
                        )
                    ]
                    result.add_warning(
                        f"Verification pass resolved {len(verified_fields)} ambiguous field(s): "
                        f"{', '.join(verified_fields)}"
                    )

        # ── Build Pydantic models ──────────────────────────────────────────────
        try:
            doc = DocumentEngine._build_document(raw)
        except Exception as e:
            result.add_error(f"Schema validation failed: {str(e)}")
            result.metadata["raw_extraction"] = raw
            return result

        # ── Apply confidence thresholds ────────────────────────────────────────
        if overall_confidence >= CONFIDENCE_AUTO_PROCEED:
            if overall_confidence < 0.90:
                result.add_warning(
                    f"Confidence {overall_confidence:.0%} — auto-proceeding with low-confidence note"
                )
        else:
            result.flag_for_review(
                f"Confidence {overall_confidence:.0%} is below 75% threshold — human review required"
            )
            if overall_confidence < 0.50:
                result.metadata["priority"] = "HIGH"

        result.data = json.loads(doc.model_dump_json())
        logger.info(
            f"Document processed: {file_path.name} | "
            f"confidence={overall_confidence:.2f} | "
            f"review={result.requires_human_review}"
        )
        return result

    # ── Apply verification corrections ────────────────────────────────────────

    @staticmethod
    def _apply_corrections(raw: dict, corrections: dict) -> dict:
        """
        Merge second-pass Gemini corrections back into the raw extraction dict.
        Supports dot-notation keys like "employee.employee_id" or "billing_period_start".
        Only applies when verification confidence exceeds the original.
        """
        raw = dict(raw)
        for field_key, correction in corrections.items():
            confirmed = correction.get("confirmed_value")
            if confirmed is None:
                continue
            parts = field_key.split(".")
            if len(parts) == 1:
                raw[field_key] = confirmed
            elif len(parts) == 2:
                section, subfield = parts
                if section in raw and isinstance(raw[section], dict):
                    raw[section] = dict(raw[section])
                    raw[section][subfield] = confirmed
                elif section not in raw:
                    raw[section] = {subfield: confirmed}
        return raw

    # ── Master-data backfill ───────────────────────────────────────────────────

    @staticmethod
    def _backfill_from_master(raw: dict) -> tuple[dict, list[str]]:
        """
        1. Normalise client_id (CUST→CL).
        2. Resolve UNKNOWN IDs via name-matching against master JSON files.
        3. Backfill all missing contract fields from the contract file.
        4. Backfill missing client fields (company_name, currency, etc.).
        5. Fix billing period when missing/wrong year.
        """
        raw = dict(raw)
        resolved: list[str] = []

        # ── Step 1: normalise client_id ────────────────────────────────────────
        raw_cli_id = (raw.get("client") or {}).get("client_id", "")
        cli_id = _normalise_client_id(raw_cli_id)
        if cli_id != raw_cli_id:
            raw.setdefault("client", {})
            raw["client"] = dict(raw.get("client") or {})
            raw["client"]["client_id"] = cli_id

        emp_id = str((raw.get("employee") or {}).get("employee_id") or "").strip().upper() or "UNKNOWN"

        # ── Step 2a: employee name → ID lookup ─────────────────────────────────
        if emp_id in ("UNKNOWN", "NULL", "NONE", "N/A", ""):
            emp_name = (raw.get("employee") or {}).get("name", "")
            if emp_name and emp_name.lower() not in ("unknown", ""):
                try:
                    employees = json.loads((Path(MASTER_DATA_DIR) / "employees.json").read_text())
                    m = next(
                        (e for e in employees if e.get("name", "").lower() == emp_name.lower()),
                        None,
                    )
                    if m:
                        emp_id = m["employee_id"]
                        raw["employee"] = dict(raw.get("employee") or {})
                        raw["employee"]["employee_id"] = emp_id
                        resolved.append("employee.employee_id")
                except Exception:
                    pass

        # ── Step 2b: client name → ID lookup ──────────────────────────────────
        if not cli_id or cli_id in ("UNKNOWN", "NULL", "NONE", "N/A", ""):
            company = (raw.get("client") or {}).get("company_name", "")
            if company and company.lower() not in ("unknown", ""):
                try:
                    clients = json.loads((Path(MASTER_DATA_DIR) / "clients.json").read_text())
                    m = next(
                        (c for c in clients
                         if c.get("company_name", "").lower() == company.lower()),
                        None,
                    ) or next(
                        (c for c in clients
                         if company.lower() in c.get("company_name", "").lower()
                         or c.get("company_name", "").lower() in company.lower()),
                        None,
                    )
                    if m:
                        cli_id = m["client_id"]
                        raw["client"] = dict(raw.get("client") or {})
                        raw["client"]["client_id"] = cli_id
                        resolved.append("client.client_id")
                except Exception:
                    pass

        # ── Step 3: backfill contract from file ────────────────────────────────
        if emp_id and cli_id and emp_id != "UNKNOWN" and cli_id != "UNKNOWN":
            contract_file = Path(CONTRACTS_DIR) / f"contract_CON-{emp_id}-{cli_id}.json"
            if contract_file.exists():
                try:
                    master = json.loads(contract_file.read_text())
                    con = dict(raw.get("contract") or {})
                    for field in [
                        "contract_id", "billing_rate", "currency", "billing_type",
                        "contracted_hours", "start_date", "end_date",
                        "overtime_allowed", "overtime_multiplier",
                        "early_completion_policy", "late_penalty_per_hour",
                        "gst_applicable", "gst_rate", "payment_terms_days",
                    ]:
                        if con.get(field) is None and master.get(field) is not None:
                            con[field] = master[field]
                            resolved.append(f"contract.{field}")
                    raw["contract"] = con
                except Exception:
                    pass

        # ── Step 4: backfill client fields (company_name, currency, etc.) ──────
        if cli_id and cli_id != "UNKNOWN":
            cli = dict(raw.get("client") or {})
            if not cli.get("company_name") or not cli.get("currency"):
                try:
                    clients = json.loads((Path(MASTER_DATA_DIR) / "clients.json").read_text())
                    mc = next((c for c in clients if c.get("client_id") == cli_id), None)
                    if mc:
                        for f in ["company_name", "currency", "country",
                                  "billing_address", "contact_email"]:
                            if not cli.get(f) and mc.get(f):
                                cli[f] = mc[f]
                                resolved.append(f"client.{f}")
                        raw["client"] = cli
                except Exception:
                    pass

        # ── Step 5: fix billing period ─────────────────────────────────────────
        today = date.today()
        bp_s  = raw.get("billing_period_start")
        bp_e  = raw.get("billing_period_end")

        def _yr(d):
            try: return int(str(d)[:4])
            except: return 0

        bp_s_date = _parse_date(bp_s)
        bp_e_date = _parse_date(bp_e)

        if bp_s_date and bp_e_date and abs(bp_s_date.year - today.year) <= 1:
            # Document has valid dates within ±1 year — trust them exactly as-is
            pass
        else:
            # Dates are missing or year is wildly wrong — try to infer from timesheet
            ts_dates = []
            for entry in (raw.get("timesheet") or []):
                d = _parse_date(entry.get("date"))
                if d and abs(d.year - today.year) <= 1:
                    ts_dates.append(d)

            if ts_dates:
                ref_first = min(ts_dates).replace(day=1)
                ref_last_month = max(ts_dates)
                last_day = calendar.monthrange(ref_last_month.year, ref_last_month.month)[1]
                ref_last = ref_last_month.replace(day=last_day)
                raw["billing_period_start"] = ref_first.strftime("%Y-%m-%d")
                raw["billing_period_end"]   = ref_last.strftime("%Y-%m-%d")
            else:
                # Fall back to prior month — invoices are submitted in arrears
                if today.month == 1:
                    prior_year, prior_month = today.year - 1, 12
                else:
                    prior_year, prior_month = today.year, today.month - 1
                first = date(prior_year, prior_month, 1)
                last  = date(prior_year, prior_month,
                             calendar.monthrange(prior_year, prior_month)[1])
                raw["billing_period_start"] = first.strftime("%Y-%m-%d")
                raw["billing_period_end"]   = last.strftime("%Y-%m-%d")
            resolved.append("billing_period")

        return raw, resolved

    # ── Document builder ───────────────────────────────────────────────────────

    @staticmethod
    def _build_document(raw: dict) -> ExtractedDocument:
        """Map raw Gemini dict → validated Pydantic ExtractedDocument."""

        emp_data = raw.get("employee") or {}
        employee = Employee(
            employee_id=emp_data.get("employee_id") or "UNKNOWN",
            name=emp_data.get("name") or "Unknown",
            designation=emp_data.get("designation"),
            department=emp_data.get("department"),
            email=emp_data.get("email"),
            hsn_code=emp_data.get("hsn_code"),
        )

        cli_data = raw.get("client") or {}
        # Apply CUST→CL mapping one final time as safety net
        raw_cli_id = cli_data.get("client_id") or raw.get("customer_code")
        resolved_cli_id = _normalise_client_id(raw_cli_id)

        client = Client(
            client_id=resolved_cli_id,
            company_name=cli_data.get("company_name") or "Unknown",
            billing_address=cli_data.get("billing_address"),
            country=cli_data.get("country") or "UAE",
            currency=cli_data.get("currency") or "AED",
            gst_number=cli_data.get("gst_number"),
            timezone=cli_data.get("timezone"),
            contact_email=cli_data.get("contact_email"),
        )

        con_data = raw.get("contract") or {}
        derived_contract_id = (
            con_data.get("contract_id")
            or f"CON-{employee.employee_id}-{client.client_id}"
        )
        contract = Contract(
            contract_id=derived_contract_id,
            client_id=client.client_id,
            employee_id=employee.employee_id,
            billing_rate=float(con_data.get("billing_rate") or 0),
            currency=con_data.get("currency") or client.currency,
            billing_type=con_data.get("billing_type") or "hourly",
            contracted_hours=con_data.get("contracted_hours"),
            start_date=_parse_date(con_data.get("start_date")) or date(2026, 1, 1),
            end_date=_parse_date(con_data.get("end_date")) or date(2026, 12, 31),
            overtime_allowed=bool(con_data.get("overtime_allowed", True)),
            overtime_multiplier=float(con_data.get("overtime_multiplier") or 1.5),
            early_completion_policy=con_data.get("early_completion_policy") or "pay_actual",
            late_penalty_per_hour=float(con_data.get("late_penalty_per_hour") or 0),
            gst_applicable=bool(con_data.get("gst_applicable", False)),
            gst_rate=float(con_data["gst_rate"]) if con_data.get("gst_rate") is not None else 0.0,
            payment_terms_days=int(con_data.get("payment_terms_days") or 30),
        )

        # Build timesheet entries
        timesheet: list[TimesheetEntry] = []
        for entry in raw.get("timesheet") or []:
            try:
                timesheet.append(TimesheetEntry(
                    date=_parse_date(entry.get("date")) or date.today(),
                    employee_id=entry.get("employee_id") or employee.employee_id,
                    hours_worked=min(float(entry.get("hours_worked") or 0), 24.0),
                    task_description=entry.get("task_description"),
                    overtime_hours=float(entry.get("overtime_hours") or 0),
                ))
            except Exception:
                continue

        # Synthesise daily entries when document only has aggregate monthly data
        if not timesheet:
            bp_start = _parse_date(raw.get("billing_period_start")) or date.today()
            bp_end   = _parse_date(raw.get("billing_period_end"))   or date.today()
            total_hours = float(con_data.get("contracted_hours") or 0)
            if total_hours > 0:
                from datetime import timedelta
                workdays = [
                    bp_start + timedelta(days=i)
                    for i in range((bp_end - bp_start).days + 1)
                    if (bp_start + timedelta(days=i)).weekday() < 5
                ]
                hpd = round(total_hours / len(workdays), 2) if workdays else 8.0
                for d in workdays:
                    timesheet.append(TimesheetEntry(
                        date=d,
                        employee_id=employee.employee_id,
                        hours_worked=min(hpd, 24.0),
                        task_description="Synthesised from monthly aggregate",
                        overtime_hours=0.0,
                    ))

        return ExtractedDocument(
            employee=employee,
            client=client,
            contract=contract,
            timesheet=timesheet,
            billing_period_start=_parse_date(raw.get("billing_period_start")) or date.today(),
            billing_period_end=_parse_date(raw.get("billing_period_end"))   or date.today(),
            source_file=raw.get("source_file"),
        )
