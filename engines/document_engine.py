from __future__ import annotations
import json
from datetime import date
from pathlib import Path

from models.schema import (
    Employee, Client, Contract, TimesheetEntry, ExtractedDocument
)
from models.validation import EngineResult, AmbiguousField
from services.gemini_service import call_gemini
from utils.file_utils import detect_file_type, is_supported
from utils.logger import get_logger
from config import (
    CONFIDENCE_AUTO_PROCEED, CONFIDENCE_WARN_PROCEED, CONFIDENCE_HUMAN_REVIEW,
    CONTRACTS_DIR,
)

logger = get_logger("document_engine")


class DocumentEngine:

    @staticmethod
    def process(file_path: str | Path) -> EngineResult:
        """
        Entry point. Takes any supported file, returns EngineResult.
        On success, result.data contains a serialised ExtractedDocument.
        """
        file_path = Path(file_path)
        result = EngineResult(stage="document", status="SUCCESS", confidence=1.0)

        # ── 1. File checks ─────────────────────────────────────────────────────
        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        if not is_supported(file_path):
            result.add_error(f"Unsupported file format: {file_path.suffix}")
            return result

        file_type = detect_file_type(file_path)
        result.metadata["file_name"] = file_path.name
        result.metadata["file_type"] = file_type

        # ── 2. Gemini extraction ───────────────────────────────────────────────
        try:
            raw = call_gemini(file_path, file_type)
        except Exception as e:
            result.add_error(f"Gemini extraction failed: {str(e)}")
            return result

        # ── 3. Confidence scoring ──────────────────────────────────────────────
        scores = raw.get("confidence_scores", {})
        # Re-derive overall from critical fields only (employee, client, contract, timesheet)
        # Gemini often penalises for optional fields — we compute our own overall
        critical_scores = [
            float(scores[k]) for k in ["employee", "client", "contract", "timesheet"]
            if k in scores
        ]
        if critical_scores:
            overall_confidence = sum(critical_scores) / len(critical_scores)
        else:
            overall_confidence = float(scores.get("overall", 0.5))
        result.confidence = overall_confidence
        result.metadata["confidence_scores"] = scores
        result.metadata["extraction_notes"] = raw.get("extraction_notes", "")

        # ── 4. Flag ambiguous fields ───────────────────────────────────────────
        # Fields that are optional, have safe defaults, or will be backfilled from master
        NON_CRITICAL = {
            "employee.hsn_code", "employee.department", "employee.email",
            "client.billing_address", "client.gst_number", "client.timezone",
            "client.contact_email", "client.country",
            "contract.billing_rate", "contract.billing_type", "contract.contracted_hours",
            "contract.start_date", "contract.end_date",
            "contract.overtime_allowed", "contract.overtime_multiplier",
            "contract.early_completion_policy", "contract.late_penalty_per_hour",
            "contract.gst_applicable", "contract.gst_rate", "contract.payment_terms_days",
            "timesheet[*].task_description", "timesheet[].task_description",
            "timesheet*.task_description",
            "timesheet",  # aggregate-only docs get synthesised entries
        }

        for af in raw.get("ambiguous_fields", []):
            field_name = af.get("field", "unknown")
            # Skip non-critical fields entirely — they have safe defaults
            if field_name in NON_CRITICAL:
                continue
            # Also skip timesheet task_description variants
            if "task_description" in field_name:
                continue
            result.ambiguous_fields.append(AmbiguousField(
                field_name=field_name,
                extracted_value=af.get("extracted_value"),
                confidence=float(scores.get(field_name, 0.5)),
                reason=af.get("reason", ""),
                suggested_value=af.get("suggested_value"),
            ))

        # ── 4b. Backfill missing contract fields from master data ──────────────
        raw, resolved_fields = DocumentEngine._backfill_from_master(raw)
        if resolved_fields:
            # Remove ambiguous fields that are now resolved
            result.ambiguous_fields = [
                af for af in result.ambiguous_fields
                if not any(f in af.field_name for f in resolved_fields)
            ]
            # Boost confidence if we resolved ambiguities
            boost = min(0.15, 0.02 * len(resolved_fields))
            result.confidence = min(1.0, result.confidence + boost)
            overall_confidence = result.confidence
            result.add_warning(
                f"Contract fields backfilled from master data: {', '.join(resolved_fields)}"
            )
            logger.info(f"Backfilled {len(resolved_fields)} contract fields from master")

        # ── 5. Build Pydantic models ───────────────────────────────────────────
        try:
            doc = DocumentEngine._build_document(raw)
        except Exception as e:
            result.add_error(f"Schema validation failed: {str(e)}")
            result.metadata["raw_extraction"] = raw
            return result

        # ── 6. Apply confidence thresholds ────────────────────────────────────
        # ≥ 75% → auto-proceed and generate invoice (may add a warning note)
        # < 75% → route to human review queue
        if overall_confidence >= CONFIDENCE_AUTO_PROCEED:
            if overall_confidence < 0.90:
                result.add_warning(
                    f"Confidence {overall_confidence:.0%} — invoice auto-generated with low-confidence note"
                )
            # else fully automatic, no warning needed
        else:
            result.flag_for_review(
                f"Confidence {overall_confidence:.0%} is below 75% threshold — human review required"
            )
            if overall_confidence < 0.50:
                result.metadata["priority"] = "HIGH"
            result.metadata["priority"] = "HIGH"

        result.data = json.loads(doc.model_dump_json())
        logger.info(
            f"Document processed: {file_path.name} | "
            f"confidence={overall_confidence} | "
            f"review={result.requires_human_review}"
        )
        return result

    @staticmethod
    def _backfill_from_master(raw: dict) -> tuple[dict, list[str]]:
        """
        Look up master contract by employee_id + client_id.
        Fill in any None/missing contract fields so the document can proceed
        without human review for fields that are already on record.
        Returns (updated_raw, list_of_resolved_field_names).
        """
        emp_id    = (raw.get("employee") or {}).get("employee_id", "")
        cli_id    = (raw.get("client")   or {}).get("client_id",   "")

        if not emp_id or not cli_id or emp_id == "UNKNOWN" or cli_id == "UNKNOWN":
            return raw, []

        contract_file = Path(CONTRACTS_DIR) / f"contract_CON-{emp_id}-{cli_id}.json"
        if not contract_file.exists():
            return raw, []

        try:
            master = json.loads(contract_file.read_text())
        except Exception:
            return raw, []

        con = raw.get("contract") or {}
        resolved: list[str] = []

        fields_to_backfill = [
            "contract_id", "billing_rate", "currency", "billing_type",
            "contracted_hours", "start_date", "end_date",
            "overtime_allowed", "overtime_multiplier", "early_completion_policy",
            "late_penalty_per_hour", "gst_applicable", "gst_rate", "payment_terms_days",
        ]

        updated_con = dict(con)
        for field in fields_to_backfill:
            if updated_con.get(field) is None and master.get(field) is not None:
                updated_con[field] = master[field]
                resolved.append(f"contract.{field}")

        # Also backfill contract_id into the contract block
        if not updated_con.get("contract_id") and master.get("contract_id"):
            updated_con["contract_id"] = master["contract_id"]

        raw = dict(raw)
        raw["contract"] = updated_con
        return raw, resolved

    @staticmethod
    def _build_document(raw: dict) -> ExtractedDocument:
        """Map raw Gemini dict → validated Pydantic ExtractedDocument."""

        emp_data = raw.get("employee", {})
        employee = Employee(
            employee_id=emp_data.get("employee_id") or "UNKNOWN",
            name=emp_data.get("name") or "Unknown",
            designation=emp_data.get("designation"),
            department=emp_data.get("department"),
            email=emp_data.get("email"),
            hsn_code=emp_data.get("hsn_code"),
        )

        cli_data = raw.get("client", {})
        client = Client(
            client_id=cli_data.get("client_id") or "UNKNOWN",
            company_name=cli_data.get("company_name") or "Unknown",
            billing_address=cli_data.get("billing_address"),
            country=cli_data.get("country") or "India",
            currency=cli_data.get("currency") or "INR",
            gst_number=cli_data.get("gst_number"),
            timezone=cli_data.get("timezone"),
            contact_email=cli_data.get("contact_email"),
        )

        con_data = raw.get("contract", {})
        # Auto-derive contract_id from employee+client when document doesn't have one
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
            start_date=_parse_date(con_data.get("start_date")) or date(2024, 1, 1),
            end_date=_parse_date(con_data.get("end_date")) or date(2026, 12, 31),
            overtime_allowed=bool(con_data.get("overtime_allowed", True)),
            overtime_multiplier=float(con_data.get("overtime_multiplier") or 1.5),
            early_completion_policy=con_data.get("early_completion_policy") or "pay_actual",
            late_penalty_per_hour=float(con_data.get("late_penalty_per_hour") or 0),
            gst_applicable=bool(con_data.get("gst_applicable", True)),
            gst_rate=float(con_data["gst_rate"]) if con_data.get("gst_rate") is not None else 0.18,
            payment_terms_days=int(con_data.get("payment_terms_days") or 30),
        )

        timesheet = []
        for entry in raw.get("timesheet", []):
            timesheet.append(TimesheetEntry(
                date=_parse_date(entry.get("date")) or date.today(),
                employee_id=entry.get("employee_id") or employee.employee_id,
                hours_worked=min(float(entry.get("hours_worked") or 0), 24.0),
                task_description=entry.get("task_description"),
                overtime_hours=float(entry.get("overtime_hours") or 0),
            ))

        # Synthesise daily entries when document only has aggregate monthly data
        if not timesheet:
            bp_start = _parse_date(raw.get("billing_period_start")) or date.today()
            bp_end   = _parse_date(raw.get("billing_period_end"))   or date.today()
            total_hours = float((raw.get("contract") or {}).get("contracted_hours") or 0)
            if total_hours > 0:
                from datetime import timedelta
                workdays = [
                    bp_start + timedelta(days=i)
                    for i in range((bp_end - bp_start).days + 1)
                    if (bp_start + timedelta(days=i)).weekday() < 5
                ]
                hours_per_day = round(total_hours / len(workdays), 2) if workdays else 8.0
                for d in workdays:
                    timesheet.append(TimesheetEntry(
                        date=d,
                        employee_id=employee.employee_id,
                        hours_worked=min(hours_per_day, 24.0),
                        task_description="Synthesised from monthly aggregate",
                        overtime_hours=0.0,
                    ))

        return ExtractedDocument(
            employee=employee,
            client=client,
            contract=contract,
            timesheet=timesheet,
            billing_period_start=_parse_date(raw.get("billing_period_start")) or date.today(),
            billing_period_end=_parse_date(raw.get("billing_period_end")) or date.today(),
            source_file=raw.get("source_file"),
        )


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None
