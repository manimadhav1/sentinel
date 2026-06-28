from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path

from models.schema import ExtractedDocument, Contract, Employee, Client
from models.invoice import BillingResult
from models.validation import EngineResult, ValidationReport, ValidationCheck
from utils.logger import get_logger
from config import MASTER_DATA_DIR, CONTRACTS_DIR

logger = get_logger("validation_engine")


class ValidationEngine:

    @staticmethod
    def process(
        doc_result: EngineResult,
        proc_result: EngineResult,
        existing_invoices: list[dict] | None = None,
    ) -> EngineResult:
        """
        Runs all validation rules against the extracted document and billing result.
        Returns EngineResult with a ValidationReport in result.data.

        existing_invoices: list of stored invoice dicts for duplicate detection.
                           Pass [] if database not yet available.
        """
        result = EngineResult(stage="validation", status="SUCCESS", confidence=1.0)
        report = ValidationReport()

        # ── Guard: upstream must have data ────────────────────────────────────
        if not doc_result.data:
            result.add_error("No document data available for validation")
            return result
        if not proc_result.data:
            result.add_error("No billing data available for validation")
            return result

        try:
            doc = ExtractedDocument(**doc_result.data)
            billing = BillingResult(**proc_result.data)
        except Exception as e:
            result.add_error(f"Failed to deserialise data for validation: {e}")
            return result

        if existing_invoices is None:
            existing_invoices = []

        # ── Run all checks ─────────────────────────────────────────────────────
        master_employees = _load_master_employees()
        master_clients   = _load_master_clients()
        master_contracts = _load_master_contracts()

        ValidationEngine._check_mandatory_fields(doc, report)
        ValidationEngine._check_employee_exists(doc, master_employees, report)
        ValidationEngine._check_client_exists(doc, master_clients, report)
        ValidationEngine._check_contract_active(doc, report)
        ValidationEngine._check_contract_matches_master(doc, master_contracts, report)
        ValidationEngine._check_billing_period_in_contract(doc, report)
        ValidationEngine._check_hours_validity(doc, report)
        ValidationEngine._check_gst_consistency(doc, billing, report)
        ValidationEngine._check_currency_match(doc, billing, report)
        ValidationEngine._check_billing_rate_integrity(doc, billing, report)
        ValidationEngine._check_overtime_compliance(doc, billing, report)
        ValidationEngine._check_duplicate_invoice(doc, existing_invoices, report)
        ValidationEngine._check_timesheet_date_range(doc, report)
        ValidationEngine._check_employee_client_contract_linkage(doc, report)

        # ── Derive overall engine result from report ───────────────────────────
        result.data = {
            "report": [c.model_dump() for c in report.checks],
            "overall": report.overall,
            "total_checks": len(report.checks),
            "passed": sum(1 for c in report.checks if c.passed),
            "failed": sum(1 for c in report.checks if not c.passed and c.severity == "ERROR"),
            "warnings": sum(1 for c in report.checks if not c.passed and c.severity == "WARNING"),
        }

        if report.overall == "INVALID":
            failed = [c for c in report.checks if not c.passed and c.severity == "ERROR"]
            for c in failed:
                result.add_error(c.message)
            result.status = "FAILED"
            result.next_action = "HUMAN_REVIEW"
            result.requires_human_review = True
            result.confidence = _compute_confidence(report)
        elif report.overall == "WARN":
            for c in report.checks:
                if not c.passed and c.severity == "WARNING":
                    result.add_warning(c.message)
            result.confidence = _compute_confidence(report)
        else:
            result.confidence = 1.0

        logger.info(
            f"Validation complete | overall={report.overall} | "
            f"checks={len(report.checks)} | "
            f"passed={result.data['passed']} | "
            f"failed={result.data['failed']} | "
            f"warnings={result.data['warnings']}"
        )
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # INDIVIDUAL RULE CHECKS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _check_mandatory_fields(doc: ExtractedDocument, report: ValidationReport) -> None:
        """Rule 1 — Hard blockers: must have employee identity, billing rate, and timesheet."""
        errors = []
        warnings = []

        # Hard errors — cannot calculate or identify the invoice without these
        if not doc.employee.name or doc.employee.name.strip().lower() in ("unknown", ""):
            errors.append("employee name is missing — cannot identify who to bill")
        if not doc.employee.employee_id or doc.employee.employee_id == "UNKNOWN":
            # If name is known, it's a soft warning (backfill may have missed it)
            if doc.employee.name and doc.employee.name.strip().lower() not in ("unknown", ""):
                warnings.append(
                    f"employee ID not found for '{doc.employee.name}' — "
                    f"reviewer should confirm the employee ID"
                )
            else:
                errors.append("employee ID is missing — cannot identify which employee to invoice")
        if doc.contract.billing_rate <= 0:
            errors.append("billing rate is 0 or missing — cannot calculate invoice amount")
        if not doc.timesheet:
            errors.append("timesheet is empty — no hours to bill")

        # Soft warnings — useful but can proceed if company_name is known
        if not doc.client.client_id or doc.client.client_id == "UNKNOWN":
            if not doc.client.company_name or doc.client.company_name.strip().lower() in ("unknown", ""):
                errors.append("client identity missing — no client ID or company name found")
            else:
                warnings.append(f"client.client_id unknown (company: {doc.client.company_name})")

        if errors:
            report.add_check(
                "MANDATORY_FIELDS", passed=False,
                message=f"Missing required fields: {', '.join(errors)}",
                severity="ERROR",
            )
        elif warnings:
            report.add_check(
                "MANDATORY_FIELDS", passed=False,
                message=f"Incomplete fields: {', '.join(warnings)}",
                severity="WARNING",
            )
        else:
            report.add_check("MANDATORY_FIELDS", passed=True,
                             message="All mandatory fields present")

    @staticmethod
    def _check_employee_exists(
        doc: ExtractedDocument,
        master: list[dict],
        report: ValidationReport,
    ) -> None:
        """Rule 2 — Employee must exist in master data."""
        if not master:
            report.add_check("EMPLOYEE_EXISTS", passed=True,
                             message="Master data unavailable — skipped", severity="WARNING")
            return

        match = any(
            e.get("employee_id") == doc.employee.employee_id or
            e.get("name", "").lower() == doc.employee.name.lower()
            for e in master
        )
        if match:
            report.add_check("EMPLOYEE_EXISTS", passed=True,
                             message=f"Employee '{doc.employee.name}' verified in master data")
        else:
            report.add_check(
                "EMPLOYEE_EXISTS", passed=False,
                message=f"Employee '{doc.employee.name}' (ID: {doc.employee.employee_id}) "
                        f"not found in master data — verify manually",
                severity="WARNING",
            )

    @staticmethod
    def _check_client_exists(
        doc: ExtractedDocument,
        master: list[dict],
        report: ValidationReport,
    ) -> None:
        """Rule 3 — Client must exist in master data."""
        if not master:
            report.add_check("CLIENT_EXISTS", passed=True,
                             message="Master data unavailable — skipped", severity="WARNING")
            return

        match = any(
            c.get("client_id") == doc.client.client_id or
            c.get("company_name", "").lower() == doc.client.company_name.lower()
            for c in master
        )
        if match:
            report.add_check("CLIENT_EXISTS", passed=True,
                             message=f"Client '{doc.client.company_name}' verified in master data")
        else:
            report.add_check(
                "CLIENT_EXISTS", passed=False,
                message=f"Client '{doc.client.company_name}' (ID: {doc.client.client_id}) "
                        f"not found in master data — verify manually",
                severity="WARNING",
            )

    @staticmethod
    def _check_contract_active(doc: ExtractedDocument, report: ValidationReport) -> None:
        """Rule 4 — Contract must be currently active (not expired, not future)."""
        today = date.today()
        start = doc.contract.start_date
        end   = doc.contract.end_date

        if start > end:
            report.add_check(
                "CONTRACT_ACTIVE", passed=False,
                message=f"Contract start date {start} is after end date {end}",
                severity="ERROR",
            )
        elif today < start:
            report.add_check(
                "CONTRACT_ACTIVE", passed=False,
                message=f"Contract has not started yet (starts {start})",
                severity="ERROR",
            )
        elif today > end:
            report.add_check(
                "CONTRACT_ACTIVE", passed=False,
                message=f"Contract expired on {end}",
                severity="ERROR",
            )
        else:
            report.add_check("CONTRACT_ACTIVE", passed=True,
                             message=f"Contract active: {start} → {end}")

    @staticmethod
    def _check_contract_matches_master(
        doc: ExtractedDocument,
        master_contracts: list[dict],
        report: ValidationReport,
    ) -> None:
        """Rule 5 — Contract terms must match master contract on file."""
        if not master_contracts:
            report.add_check("CONTRACT_MASTER_MATCH", passed=True,
                             message="No master contracts loaded — skipped", severity="WARNING")
            return

        master = next(
            (c for c in master_contracts if c.get("contract_id") == doc.contract.contract_id),
            None
        )
        if not master:
            report.add_check(
                "CONTRACT_MASTER_MATCH", passed=False,
                message=f"Contract ID '{doc.contract.contract_id}' not found in master contracts",
                severity="WARNING",
            )
            return

        mismatches = []
        if abs(float(master.get("billing_rate", 0)) - doc.contract.billing_rate) > 0.01:
            mismatches.append(
                f"billing_rate: master={master.get('billing_rate')} "
                f"doc={doc.contract.billing_rate}"
            )
        if master.get("currency") != doc.contract.currency:
            mismatches.append(
                f"currency: master={master.get('currency')} doc={doc.contract.currency}"
            )
        if abs(float(master.get("gst_rate", 0)) - doc.contract.gst_rate) > 0.001:
            mismatches.append(
                f"gst_rate: master={master.get('gst_rate')} doc={doc.contract.gst_rate}"
            )

        if mismatches:
            report.add_check(
                "CONTRACT_MASTER_MATCH", passed=False,
                message=f"Contract terms differ from master: {'; '.join(mismatches)}",
                severity="WARNING",
            )
        else:
            report.add_check("CONTRACT_MASTER_MATCH", passed=True,
                             message="Contract terms match master data")

    @staticmethod
    def _check_billing_period_in_contract(
        doc: ExtractedDocument, report: ValidationReport
    ) -> None:
        """Rule 6 — Billing period must fall within contract validity dates."""
        bp_start = doc.billing_period_start
        bp_end   = doc.billing_period_end
        c_start  = doc.contract.start_date
        c_end    = doc.contract.end_date

        if bp_start < c_start or bp_end > c_end:
            report.add_check(
                "BILLING_PERIOD_IN_CONTRACT", passed=False,
                message=(
                    f"Billing period {bp_start} → {bp_end} falls outside "
                    f"contract validity {c_start} → {c_end}"
                ),
                severity="ERROR",
            )
        elif bp_start > bp_end:
            report.add_check(
                "BILLING_PERIOD_IN_CONTRACT", passed=False,
                message=f"Billing period start {bp_start} is after end {bp_end}",
                severity="ERROR",
            )
        else:
            report.add_check(
                "BILLING_PERIOD_IN_CONTRACT", passed=True,
                message=f"Billing period {bp_start} → {bp_end} within contract dates",
            )

    @staticmethod
    def _check_hours_validity(doc: ExtractedDocument, report: ValidationReport) -> None:
        """Rule 7 — Timesheet hours must be valid (>0, ≤24/day, reasonable total)."""
        issues = []
        total = 0.0

        for entry in doc.timesheet:
            if entry.hours_worked <= 0:
                issues.append(f"{entry.date}: hours_worked={entry.hours_worked} (must be > 0)")
            if entry.hours_worked > 24:
                issues.append(f"{entry.date}: hours_worked={entry.hours_worked} exceeds 24h/day")
            if entry.overtime_hours < 0:
                issues.append(f"{entry.date}: overtime_hours cannot be negative")
            if entry.overtime_hours > 0 and entry.overtime_hours > entry.hours_worked:
                issues.append(
                    f"{entry.date}: overtime_hours ({entry.overtime_hours}) "
                    f"exceeds hours_worked ({entry.hours_worked})"
                )
            total += entry.hours_worked

        # Sanity: more than 744h in a month (31 days × 24h) is impossible
        if total > 744:
            issues.append(f"Total hours {total} exceeds physical maximum for a month")

        if issues:
            report.add_check(
                "HOURS_VALIDITY", passed=False,
                message=f"Invalid hours detected: {'; '.join(issues)}",
                severity="ERROR",
            )
        else:
            report.add_check(
                "HOURS_VALIDITY", passed=True,
                message=f"All timesheet hours valid (total={total}h)",
            )

    @staticmethod
    def _check_gst_consistency(
        doc: ExtractedDocument,
        billing: BillingResult,
        report: ValidationReport,
    ) -> None:
        """Rule 8 — GST amount must match contract GST rate applied to subtotal."""
        if not doc.contract.gst_applicable:
            if billing.gst_amount != 0:
                report.add_check(
                    "GST_CONSISTENCY", passed=False,
                    message=f"GST not applicable per contract but billing shows {billing.gst_amount}",
                    severity="ERROR",
                )
            else:
                report.add_check("GST_CONSISTENCY", passed=True,
                                 message="GST correctly set to 0 (not applicable)")
            return

        expected_gst = round(billing.subtotal * doc.contract.gst_rate, 2)
        diff = abs(expected_gst - billing.gst_amount)

        if diff > 1.0:  # tolerance: ₹1 rounding allowance
            report.add_check(
                "GST_CONSISTENCY", passed=False,
                message=(
                    f"GST mismatch: expected {expected_gst} "
                    f"({int(doc.contract.gst_rate*100)}% of {billing.subtotal}) "
                    f"but got {billing.gst_amount}"
                ),
                severity="ERROR",
            )
        else:
            report.add_check(
                "GST_CONSISTENCY", passed=True,
                message=f"GST {billing.gst_amount} matches rate {int(doc.contract.gst_rate*100)}%",
            )

    @staticmethod
    def _check_currency_match(
        doc: ExtractedDocument,
        billing: BillingResult,
        report: ValidationReport,
    ) -> None:
        """Rule 9 — Billing currency must match contract currency."""
        if doc.contract.currency != billing.currency:
            report.add_check(
                "CURRENCY_MATCH", passed=False,
                message=(
                    f"Currency mismatch: contract specifies '{doc.contract.currency}' "
                    f"but billing uses '{billing.currency}'"
                ),
                severity="ERROR",
            )
        else:
            report.add_check(
                "CURRENCY_MATCH", passed=True,
                message=f"Currency '{billing.currency}' matches contract",
            )

    @staticmethod
    def _check_billing_rate_integrity(
        doc: ExtractedDocument,
        billing: BillingResult,
        report: ValidationReport,
    ) -> None:
        """Rule 10 — Effective billing rate must match contract rate."""
        if billing.regular_hours <= 0:
            report.add_check("BILLING_RATE_INTEGRITY", passed=True,
                             message="No regular hours to validate rate against")
            return

        effective_rate = round(billing.regular_amount / billing.regular_hours, 2)
        expected_rate  = doc.contract.billing_rate
        diff = abs(effective_rate - expected_rate)

        if diff > 0.5:  # tolerance for rounding
            report.add_check(
                "BILLING_RATE_INTEGRITY", passed=False,
                message=(
                    f"Effective billing rate {effective_rate} does not match "
                    f"contract rate {expected_rate}"
                ),
                severity="ERROR",
            )
        else:
            report.add_check(
                "BILLING_RATE_INTEGRITY", passed=True,
                message=f"Billing rate {effective_rate} matches contract rate {expected_rate}",
            )

    @staticmethod
    def _check_overtime_compliance(
        doc: ExtractedDocument,
        billing: BillingResult,
        report: ValidationReport,
    ) -> None:
        """Rule 11 — Overtime must only appear if contract allows it."""
        if billing.overtime_hours > 0 and not doc.contract.overtime_allowed:
            report.add_check(
                "OVERTIME_COMPLIANCE", passed=False,
                message=(
                    f"Overtime of {billing.overtime_hours}h billed but "
                    f"contract does not permit overtime"
                ),
                severity="ERROR",
            )
        elif billing.overtime_hours > 0 and doc.contract.overtime_allowed:
            report.add_check(
                "OVERTIME_COMPLIANCE", passed=True,
                message=f"Overtime {billing.overtime_hours}h permitted by contract",
            )
        else:
            report.add_check("OVERTIME_COMPLIANCE", passed=True,
                             message="No overtime — compliant")

    @staticmethod
    def _check_duplicate_invoice(
        doc: ExtractedDocument,
        existing_invoices: list[dict],
        report: ValidationReport,
    ) -> None:
        """Rule 12 — No duplicate invoice for same employee+client+period."""
        duplicate = next(
            (
                inv for inv in existing_invoices
                if (
                    inv.get("employee_id") == doc.employee.employee_id and
                    inv.get("client_id")   == doc.client.client_id and
                    inv.get("billing_period_start") == str(doc.billing_period_start) and
                    inv.get("billing_period_end")   == str(doc.billing_period_end)
                )
            ),
            None,
        )
        if duplicate:
            report.add_check(
                "DUPLICATE_INVOICE", passed=False,
                message=(
                    f"Duplicate invoice detected: {duplicate.get('invoice_number')} "
                    f"already exists for {doc.employee.name} / {doc.client.company_name} "
                    f"period {doc.billing_period_start} → {doc.billing_period_end}"
                ),
                severity="ERROR",
            )
        else:
            report.add_check("DUPLICATE_INVOICE", passed=True,
                             message="No duplicate invoice found")

    @staticmethod
    def _check_timesheet_date_range(
        doc: ExtractedDocument, report: ValidationReport
    ) -> None:
        """Rule 13 — All timesheet entries must fall within the billing period."""
        out_of_range = [
            str(e.date) for e in doc.timesheet
            if not (doc.billing_period_start <= e.date <= doc.billing_period_end)
        ]
        if out_of_range:
            report.add_check(
                "TIMESHEET_DATE_RANGE", passed=False,
                message=f"Timesheet entries outside billing period: {', '.join(out_of_range)}",
                severity="WARNING",
            )
        else:
            report.add_check(
                "TIMESHEET_DATE_RANGE", passed=True,
                message="All timesheet dates within billing period",
            )

    @staticmethod
    def _check_employee_client_contract_linkage(
        doc: ExtractedDocument, report: ValidationReport
    ) -> None:
        """Rule 14 — Contract must link the correct employee to the correct client."""
        # If client_id is UNKNOWN the contract was auto-derived — skip linkage check
        if doc.client.client_id == "UNKNOWN":
            report.add_check(
                "LINKAGE_INTEGRITY", passed=True,
                message="Client ID unresolved — linkage check skipped (auto-derived contract)",
                severity="WARNING",
            )
            return

        mismatches = []
        if doc.contract.employee_id != doc.employee.employee_id:
            mismatches.append(
                f"contract.employee_id={doc.contract.employee_id} "
                f"≠ employee.employee_id={doc.employee.employee_id}"
            )
        if doc.contract.client_id != doc.client.client_id:
            mismatches.append(
                f"contract.client_id={doc.contract.client_id} "
                f"≠ client.client_id={doc.client.client_id}"
            )

        if mismatches:
            report.add_check(
                "LINKAGE_INTEGRITY", passed=False,
                message=f"Contract linkage mismatch: {'; '.join(mismatches)}",
                severity="WARNING",
            )
        else:
            report.add_check(
                "LINKAGE_INTEGRITY", passed=True,
                message="Employee–Client–Contract linkage verified",
            )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_master_employees() -> list[dict]:
    p = MASTER_DATA_DIR / "employees.json"
    if not p.exists():
        return []
    import json
    return json.loads(p.read_text())


def _load_master_clients() -> list[dict]:
    p = MASTER_DATA_DIR / "clients.json"
    if not p.exists():
        return []
    import json
    return json.loads(p.read_text())


def _load_master_contracts() -> list[dict]:
    contracts = []
    if not CONTRACTS_DIR.exists():
        return contracts
    import json
    for f in CONTRACTS_DIR.glob("*.json"):
        try:
            contracts.append(json.loads(f.read_text()))
        except Exception:
            pass
    return contracts


def _compute_confidence(report: ValidationReport) -> float:
    """Confidence = ratio of passed checks, weighted by severity."""
    if not report.checks:
        return 1.0
    total_weight = 0.0
    passed_weight = 0.0
    for c in report.checks:
        weight = 2.0 if c.severity == "ERROR" else 1.0
        total_weight += weight
        if c.passed:
            passed_weight += weight
    return round(passed_weight / total_weight, 3)
