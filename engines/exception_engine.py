from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from enum import Enum

from models.validation import EngineResult
from utils.logger import get_logger
from utils.client_protocols import (
    get_protocol, get_ot_cap, po_required, get_po_regex,
    get_sla_hours, get_working_day_range, get_document_requirements,
)

logger = get_logger("exception_engine")


class ExceptionType(str, Enum):
    DUPLICATE                 = "DUPLICATE"
    MISSING_MANDATORY         = "MISSING_MANDATORY"
    CONTRACT_INVALID          = "CONTRACT_INVALID"
    RATE_MISMATCH             = "RATE_MISMATCH"
    CURRENCY_MISMATCH         = "CURRENCY_MISMATCH"
    OT_CAP_EXCEEDED           = "OT_CAP_EXCEEDED"
    PO_MISSING                = "PO_MISSING"
    BILLING_PERIOD_ANOMALY    = "BILLING_PERIOD_ANOMALY"
    AMOUNT_ANOMALY            = "AMOUNT_ANOMALY"
    LOW_EXTRACTION_CONFIDENCE = "LOW_EXTRACTION_CONFIDENCE"
    UNRESOLVED_AMBIGUOUS      = "UNRESOLVED_AMBIGUOUS"
    VALIDATION_WARNING        = "VALIDATION_WARNING"
    CLEAR                     = "CLEAR"


class RoutingDecision(str, Enum):
    AUTO_PROCEED      = "AUTO_PROCEED"     # clear to generate invoice
    AUTO_CORRECTED    = "AUTO_CORRECTED"   # auto-fix applied, clear to proceed
    DUPLICATE_RETURN  = "DUPLICATE_RETURN" # return existing invoice
    HUMAN_REVIEW      = "HUMAN_REVIEW"     # needs human intervention
    HARD_REJECT       = "HARD_REJECT"      # cannot process at all


@dataclass
class ExceptionItem:
    exception_type: ExceptionType
    severity: str                       # CRITICAL | HIGH | MEDIUM | LOW
    message: str
    rule: str = ""
    auto_correctable: bool = False
    correction_applied: str | None = None


@dataclass
class ExceptionResult:
    routing: RoutingDecision
    exceptions: list[ExceptionItem] = field(default_factory=list)
    pipeline_confidence: float = 1.0
    review_priority: str = "NORMAL"     # HIGH | NORMAL | LOW
    review_reason: str = ""
    corrections: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "routing": self.routing.value,
            "pipeline_confidence": self.pipeline_confidence,
            "review_priority": self.review_priority,
            "review_reason": self.review_reason,
            "corrections": self.corrections,
            "exceptions": [
                {
                    "type": e.exception_type.value,
                    "severity": e.severity,
                    "message": e.message,
                    "rule": e.rule,
                    "correction_applied": e.correction_applied,
                }
                for e in self.exceptions
            ],
            **self.metadata,
        }


# How each validation rule failure maps to an exception type and base severity
_RULE_MAP: dict[str, tuple[ExceptionType, str]] = {
    "MANDATORY_FIELDS":           (ExceptionType.MISSING_MANDATORY,      "CRITICAL"),
    "HOURS_VALIDITY":             (ExceptionType.MISSING_MANDATORY,      "CRITICAL"),
    "DUPLICATE_INVOICE":          (ExceptionType.DUPLICATE,              "CRITICAL"),
    "CONTRACT_ACTIVE":            (ExceptionType.CONTRACT_INVALID,       "CRITICAL"),
    "EMPLOYEE_EXISTS":            (ExceptionType.MISSING_MANDATORY,      "HIGH"),
    "CLIENT_EXISTS":              (ExceptionType.MISSING_MANDATORY,      "HIGH"),
    "BILLING_PERIOD_IN_CONTRACT": (ExceptionType.BILLING_PERIOD_ANOMALY, "HIGH"),
    "OVERTIME_COMPLIANCE":        (ExceptionType.OT_CAP_EXCEEDED,        "HIGH"),
    "BILLING_RATE_INTEGRITY":     (ExceptionType.RATE_MISMATCH,          "HIGH"),
    "CONTRACT_MASTER_MATCH":      (ExceptionType.RATE_MISMATCH,          "MEDIUM"),
    "CURRENCY_MATCH":             (ExceptionType.CURRENCY_MISMATCH,      "MEDIUM"),
    "GST_CONSISTENCY":            (ExceptionType.RATE_MISMATCH,          "MEDIUM"),
    "LINKAGE_INTEGRITY":          (ExceptionType.CONTRACT_INVALID,       "MEDIUM"),
    "TIMESHEET_DATE_RANGE":       (ExceptionType.BILLING_PERIOD_ANOMALY, "LOW"),
}


class ExceptionEngine:
    """
    Single routing authority for the pipeline.
    Replaces ad-hoc human_review flags scattered across stages.
    Classifies all exceptions, attempts auto-corrections, then decides
    one of: AUTO_PROCEED | AUTO_CORRECTED | DUPLICATE_RETURN | HUMAN_REVIEW | HARD_REJECT
    """

    @staticmethod
    def process(
        doc_result: EngineResult,
        proc_result: EngineResult | None = None,
        val_result: EngineResult | None = None,
    ) -> ExceptionResult:
        proc_result = proc_result or EngineResult(stage="processing", status="PENDING")
        val_result  = val_result  or EngineResult(stage="validation",  status="PENDING")

        doc_data  = doc_result.data  or {}
        proc_data = proc_result.data or {}
        val_data  = val_result.data  or {}

        client_id = (doc_data.get("client") or {}).get("client_id", "UNKNOWN")
        exceptions: list[ExceptionItem] = []
        corrections: dict = {}

        # ── 1. Hard engine failures ────────────────────────────────────────────
        if doc_result.status == "FAILED":
            for err in doc_result.errors:
                exceptions.append(ExceptionItem(
                    ExceptionType.MISSING_MANDATORY, "CRITICAL",
                    f"Document extraction failed: {err}", rule="EXTRACTION_FAILURE"
                ))
            return ExceptionResult(
                routing=RoutingDecision.HARD_REJECT,
                exceptions=exceptions,
                pipeline_confidence=0.0,
                review_priority="HIGH",
                review_reason="; ".join(doc_result.errors[:2]),
            )

        if proc_result.status == "FAILED":
            for err in proc_result.errors:
                exceptions.append(ExceptionItem(
                    ExceptionType.MISSING_MANDATORY, "CRITICAL",
                    f"Billing calculation failed: {err}", rule="PROCESSING_FAILURE"
                ))
            pipeline_conf = _blend_confidence(doc_result.confidence, 0.0, 0.0)
            return ExceptionResult(
                routing=RoutingDecision.HARD_REJECT,
                exceptions=exceptions,
                pipeline_confidence=pipeline_conf,
                review_priority="HIGH",
                review_reason="; ".join(proc_result.errors[:2]),
            )

        # ── 2. Classify validation rule failures ──────────────────────────────
        for check in val_data.get("report", []):
            if check.get("passed"):
                continue
            rule     = check.get("rule", "")
            msg      = check.get("message", "")
            chk_sev  = check.get("severity", "ERROR")
            exc_type, base_sev = _RULE_MAP.get(rule, (ExceptionType.VALIDATION_WARNING, "MEDIUM"))

            # Downgrade severity when the rule itself only raised a WARNING
            if chk_sev == "WARNING":
                base_sev = {"CRITICAL": "MEDIUM", "HIGH": "MEDIUM", "MEDIUM": "LOW"}.get(base_sev, base_sev)

            item = ExceptionItem(
                exception_type=exc_type,
                severity=base_sev,
                message=msg,
                rule=rule,
                auto_correctable=_auto_correctable(exc_type, client_id),
            )
            exceptions.append(item)

        # ── 3. Extraction confidence ───────────────────────────────────────────
        doc_conf = doc_result.confidence
        if doc_conf < 0.50:
            exceptions.append(ExceptionItem(
                ExceptionType.LOW_EXTRACTION_CONFIDENCE, "CRITICAL",
                f"Extraction confidence {doc_conf:.0%} — document may be unreadable or corrupt",
            ))
        elif doc_conf < 0.75:
            exceptions.append(ExceptionItem(
                ExceptionType.LOW_EXTRACTION_CONFIDENCE, "HIGH",
                f"Extraction confidence {doc_conf:.0%} below the 75% auto-proceed threshold",
            ))

        # ── 4. Unresolved ambiguous fields ────────────────────────────────────
        critical_ambiguous = [
            af for af in doc_result.ambiguous_fields if af.confidence < 0.75
        ]
        if critical_ambiguous:
            names = [af.field_name for af in critical_ambiguous]
            exceptions.append(ExceptionItem(
                ExceptionType.UNRESOLVED_AMBIGUOUS, "HIGH",
                f"Fields still ambiguous after verification pass: {', '.join(names)}",
            ))

        # ── 5. Per-client OT cap ──────────────────────────────────────────────
        ot_cap = get_ot_cap(client_id)
        actual_ot = float(proc_data.get("overtime_hours", 0))
        if ot_cap and actual_ot > ot_cap:
            excess = round(actual_ot - ot_cap, 2)
            exceptions.append(ExceptionItem(
                ExceptionType.OT_CAP_EXCEEDED, "MEDIUM",
                f"{client_id} monthly OT cap is {ot_cap}h; submitted {actual_ot}h (+{excess}h excess)",
                auto_correctable=True,
            ))

        # ── 6. Per-client PO requirement ──────────────────────────────────────
        if po_required(client_id):
            po_regex = get_po_regex(client_id) or ""
            text_corpus = (
                str(doc_result.metadata.get("extraction_notes", "")) +
                json.dumps(doc_data, default=str)
            )
            if po_regex and not re.search(po_regex, text_corpus, re.IGNORECASE):
                proto = get_protocol(client_id)
                exceptions.append(ExceptionItem(
                    ExceptionType.PO_MISSING, "HIGH",
                    f"Client {client_id} requires a PO number "
                    f"(e.g. {proto.get('po_format_example', po_regex)}) — none found in document",
                ))

        # ── 7. Working day count vs staffing agreement ─────────────────────────
        ts_dates = {e.get("date") for e in (doc_data.get("timesheet") or []) if e.get("date")}
        working_days = len(ts_dates)
        if working_days > 0:
            wd_min, wd_max = get_working_day_range(client_id)
            if working_days < wd_min or working_days > wd_max:
                exceptions.append(ExceptionItem(
                    ExceptionType.BILLING_PERIOD_ANOMALY, "MEDIUM",
                    f"Timesheet has {working_days} working days; {client_id} agreement allows {wd_min}–{wd_max}",
                ))

        # ── 8. Special document requirements ──────────────────────────────────
        doc_reqs = get_document_requirements(client_id)
        text_corpus   = (
            str(doc_result.metadata.get("extraction_notes", "")) +
            json.dumps(doc_data, default=str)
        ).lower()

        if "no_handwritten" in doc_reqs:
            if any(kw in text_corpus for kw in ("handwritten", "handwrit", "hand-writ", "manuscript")):
                exceptions.append(ExceptionItem(
                    ExceptionType.VALIDATION_WARNING, "HIGH",
                    f"Client {client_id} does not accept handwritten timesheets — document appears handwritten",
                    rule="DOCUMENT_FORMAT",
                ))

        if "dual_signoff" in doc_reqs:
            if text_corpus.count("sign") < 2 and "dual" not in text_corpus:
                exceptions.append(ExceptionItem(
                    ExceptionType.VALIDATION_WARNING, "MEDIUM",
                    f"Client {client_id} requires dual sign-off — verify both approvals are present",
                    rule="DUAL_SIGNOFF",
                ))

        if "hse_signoff_for_ot" in doc_reqs and actual_ot > 0:
            if "hse" not in text_corpus and "health" not in text_corpus:
                exceptions.append(ExceptionItem(
                    ExceptionType.OT_CAP_EXCEEDED, "HIGH",
                    f"Client {client_id} requires HSE sign-off for overtime — not detected in document",
                    rule="HSE_SIGNOFF",
                ))

        if "shift_id_for_ot" in doc_reqs and actual_ot > 0:
            if "shift" not in text_corpus:
                exceptions.append(ExceptionItem(
                    ExceptionType.OT_CAP_EXCEEDED, "MEDIUM",
                    f"Client {client_id} requires a shift ID on OT entries — not detected in document",
                    rule="SHIFT_ID",
                ))

        if "stamp_if_handwritten" in doc_reqs:
            if any(kw in text_corpus for kw in ("handwritten", "handwrit")):
                if "stamp" not in text_corpus and "seal" not in text_corpus:
                    exceptions.append(ExceptionItem(
                        ExceptionType.VALIDATION_WARNING, "MEDIUM",
                        f"Client {client_id} requires a company stamp on handwritten documents",
                        rule="STAMP_REQUIRED",
                    ))

        # ── 7. Apply auto-corrections ─────────────────────────────────────────
        for exc in exceptions:
            if not exc.auto_correctable:
                continue
            if exc.exception_type == ExceptionType.OT_CAP_EXCEEDED and ot_cap:
                corrections["ot_cap_applied"] = {
                    "original": actual_ot, "capped_to": ot_cap, "client": client_id
                }
                exc.correction_applied = f"OT hours capped to {ot_cap}h per {client_id} staffing agreement"
            elif exc.exception_type == ExceptionType.CURRENCY_MISMATCH:
                master_ccy = (doc_data.get("contract") or {}).get("currency")
                if master_ccy:
                    corrections["currency"] = master_ccy
                    exc.correction_applied = f"Currency auto-corrected to {master_ccy} from master contract"

        # ── 8. Pipeline confidence (weighted blend + exception penalties) ──────
        proc_conf = proc_result.confidence
        val_conf  = val_result.confidence
        pipeline_conf = _blend_confidence(doc_conf, proc_conf, val_conf)
        pipeline_conf = _apply_exception_penalties(pipeline_conf, exceptions)

        # ── 9. Routing decision (SLA determines review priority) ──────────────
        routing, priority, reason = _decide_routing(exceptions, client_id)

        exc_result = ExceptionResult(
            routing=routing,
            exceptions=exceptions,
            pipeline_confidence=pipeline_conf,
            review_priority=priority,
            review_reason=reason,
            corrections=corrections,
            metadata={
                "client_id": client_id,
                "doc_confidence":      round(doc_conf, 3),
                "proc_confidence":     round(proc_conf, 3),
                "val_confidence":      round(val_conf, 3),
                "pipeline_confidence": pipeline_conf,
                "total_exceptions":    len(exceptions),
                "auto_corrected":      len([e for e in exceptions if e.correction_applied]),
                "needs_review":        routing in (RoutingDecision.HUMAN_REVIEW, RoutingDecision.HARD_REJECT),
            },
        )

        logger.info(
            f"ExceptionEngine: routing={routing.value} | "
            f"pipeline_conf={pipeline_conf:.2f} | "
            f"exceptions={len(exceptions)} | client={client_id}"
        )
        return exc_result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _blend_confidence(doc: float, proc: float, val: float) -> float:
    """Weighted harmonic blend: validation counts most, extraction second, processing least."""
    return round(doc * 0.35 + proc * 0.20 + val * 0.45, 3)


def _apply_exception_penalties(conf: float, exceptions: list[ExceptionItem]) -> float:
    uncorrected = [e for e in exceptions if not e.correction_applied]
    for exc in uncorrected:
        if exc.severity == "CRITICAL":
            conf = min(conf, 0.50)
        elif exc.severity == "HIGH":
            conf = max(0.0, conf - 0.10)
        elif exc.severity == "MEDIUM":
            conf = max(0.0, conf - 0.04)
    return round(conf, 3)


def _auto_correctable(exc_type: ExceptionType, client_id: str) -> bool:
    if exc_type == ExceptionType.OT_CAP_EXCEEDED and get_ot_cap(client_id):
        return True
    if exc_type == ExceptionType.CURRENCY_MISMATCH:
        return True
    return False


def _sla_priority(client_id: str) -> str:
    """Map client SLA hours → review queue priority."""
    sla = get_sla_hours(client_id)
    if sla <= 12:
        return "HIGH"
    if sla <= 24:
        return "NORMAL"
    return "LOW"


def _decide_routing(
    exceptions: list[ExceptionItem],
    client_id: str = "UNKNOWN",
) -> tuple[RoutingDecision, str, str]:
    """Returns (routing, review_priority, review_reason).
    Review priority is elevated by the client's SLA window — shorter SLA = higher urgency.
    """
    uncorrected = [e for e in exceptions if not e.correction_applied]

    if not uncorrected:
        has_corrections = any(e.correction_applied for e in exceptions)
        return (
            (RoutingDecision.AUTO_CORRECTED, "LOW", "")
            if has_corrections
            else (RoutingDecision.AUTO_PROCEED, "LOW", "")
        )

    # DUPLICATE always takes priority — return existing invoice regardless of other issues
    dups = [e for e in uncorrected if e.exception_type == ExceptionType.DUPLICATE]
    if dups:
        return RoutingDecision.DUPLICATE_RETURN, "HIGH", dups[0].message

    sla_pri  = _sla_priority(client_id)
    critical = [e for e in uncorrected if e.severity == "CRITICAL"]
    high     = [e for e in uncorrected if e.severity == "HIGH"]
    medium   = [e for e in uncorrected if e.severity == "MEDIUM"]

    if critical:
        # SLA can elevate but never lower from HIGH
        reasons = "; ".join(e.message for e in critical[:2])
        return RoutingDecision.HUMAN_REVIEW, "HIGH", f"Critical: {reasons}"

    if high:
        # SLA can bump NORMAL → HIGH for short-SLA clients
        priority = "HIGH" if sla_pri == "HIGH" else "NORMAL"
        reasons  = "; ".join(e.message for e in high[:2])
        return RoutingDecision.HUMAN_REVIEW, priority, f"High severity: {reasons}"

    if len(medium) >= 3:
        reasons = "; ".join(e.message for e in medium[:2])
        return RoutingDecision.HUMAN_REVIEW, sla_pri, f"Multiple issues: {reasons}"

    # Only low/medium (< 3) — auto-proceed with warnings
    has_corrections = any(e.correction_applied for e in exceptions)
    return (
        (RoutingDecision.AUTO_CORRECTED, "LOW", "")
        if has_corrections
        else (RoutingDecision.AUTO_PROCEED, "LOW", "")
    )
