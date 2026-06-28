from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from engines.document_engine import DocumentEngine
from engines.processing_engine import ProcessingEngine
from engines.validation_engine import ValidationEngine
from engines.exception_engine import ExceptionEngine, ExceptionResult, RoutingDecision
from engines.invoice_engine import InvoiceEngine
from services.database_service import DatabaseService
from models.validation import EngineResult
from utils.logger import get_logger

logger = get_logger("pipeline")


@dataclass
class PipelineResult:
    document:          EngineResult
    processing:        EngineResult | None = None
    validation:        EngineResult | None = None
    exception:         ExceptionResult | None = None
    invoice:           EngineResult | None = None
    invoice_number:    str = ""
    pdf_path:          str = ""
    excel_path:        str = ""
    routed_to_review:  bool = False
    review_queue_id:   int | None = None
    is_duplicate:      bool = False
    pipeline_confidence: float = 1.0

    @property
    def success(self) -> bool:
        return (
            self.invoice is not None
            and self.invoice.status == "SUCCESS"
            and not self.routed_to_review
        )

    @property
    def final_status(self) -> str:
        if self.is_duplicate:
            return "DUPLICATE"
        if self.routed_to_review:
            return "REVIEW_REQUIRED"
        if self.invoice and self.invoice.status == "SUCCESS":
            return "COMPLETE"
        for stage in [self.validation, self.processing, self.document]:
            if stage and stage.status == "FAILED":
                return "FAILED"
        return "UNKNOWN"

    def summary(self) -> dict:
        last = (
            self.invoice or self.validation
            or self.processing or self.document
        )
        return {
            "status":               self.final_status,
            "invoice_number":       self.invoice_number,
            "pdf_path":             self.pdf_path,
            "excel_path":           self.excel_path,
            "routed_to_review":     self.routed_to_review,
            "review_queue_id":      self.review_queue_id,
            "is_duplicate":         self.is_duplicate,
            "pipeline_confidence":  self.pipeline_confidence,
            "document_confidence":  self.document.confidence,
            "errors":               last.errors if last else [],
            "warnings":             last.warnings if last else [],
            "exception_routing":    self.exception.routing.value if self.exception else None,
            "exception_count":      len(self.exception.exceptions) if self.exception else 0,
        }


class SentinelPipeline:
    """
    Five-stage pipeline with ExceptionEngine as the sole routing authority.

    Stage 1 — DocumentEngine   : AI extraction + backfill + verification
    Stage 2 — ProcessingEngine : Billing calculation (pure Python)
    Stage 3 — ValidationEngine : 14 business-rule checks
    Stage 4 — ExceptionEngine  : Classify exceptions, auto-correct, decide routing
    Stage 5 — InvoiceEngine    : PDF + ERP Excel generation
    """

    def __init__(self):
        DatabaseService.initialise()

    def run(self, file_path: str | Path) -> PipelineResult:
        file_path = Path(file_path)
        logger.info(f"Pipeline started: {file_path.name}")

        # ── Stage 1: Document Engine ───────────────────────────────────────────
        doc_result = DocumentEngine.process(file_path)
        result = PipelineResult(
            document=doc_result,
            pipeline_confidence=doc_result.confidence,
        )

        DatabaseService.log_event(
            "DOCUMENT_PROCESSED",
            invoice_number=file_path.stem,
            stage="document",
            status=doc_result.status,
            confidence=doc_result.confidence,
            message=f"File: {file_path.name}",
        )

        if doc_result.status == "FAILED":
            exc = ExceptionEngine.process(doc_result)
            result.exception = exc
            result.pipeline_confidence = exc.pipeline_confidence
            return self._route(result, exc, file_path)

        # ── Stage 2: Processing Engine ─────────────────────────────────────────
        proc_result = ProcessingEngine.process(doc_result)
        result.processing = proc_result

        DatabaseService.log_event(
            "PROCESSING_COMPLETE",
            stage="processing",
            status=proc_result.status,
            confidence=proc_result.confidence,
        )

        if proc_result.status == "FAILED":
            exc = ExceptionEngine.process(doc_result, proc_result)
            result.exception = exc
            result.pipeline_confidence = exc.pipeline_confidence
            return self._route(result, exc, file_path)

        # ── Stage 3: Validation Engine ─────────────────────────────────────────
        existing = self._get_existing_invoices(doc_result)
        val_result = ValidationEngine.process(doc_result, proc_result, existing)
        result.validation = val_result

        DatabaseService.log_event(
            "VALIDATION_COMPLETE",
            stage="validation",
            status=val_result.status,
            confidence=val_result.confidence,
            message=f"Overall: {val_result.data.get('overall') if val_result.data else 'N/A'}",
        )

        # ── Stage 4: Exception Engine ─────────────────────────────────────────
        exc = ExceptionEngine.process(doc_result, proc_result, val_result)
        result.exception = exc
        result.pipeline_confidence = exc.pipeline_confidence

        DatabaseService.log_event(
            "EXCEPTION_EVALUATED",
            stage="exception",
            status=exc.routing.value,
            confidence=exc.pipeline_confidence,
            message=(
                f"routing={exc.routing.value} | "
                f"exceptions={len(exc.exceptions)} | "
                f"priority={exc.review_priority}"
            ),
        )

        # ── Routing decision ───────────────────────────────────────────────────
        if exc.routing == RoutingDecision.DUPLICATE_RETURN:
            if existing:
                inv_db = existing[0]
                result.invoice_number = inv_db["invoice_number"]
                result.pdf_path       = inv_db.get("pdf_path", "")
                result.excel_path     = inv_db.get("excel_path", "")
                result.is_duplicate   = True
                synthetic = EngineResult(stage="invoice", status="SUCCESS")
                synthetic.data = inv_db
                result.invoice = synthetic
                logger.info(f"Duplicate — returning existing {inv_db['invoice_number']}")
                return result
            # No existing found despite duplicate flag — fall through to review
            exc.review_reason = "Duplicate flag raised but no existing invoice found"

        if exc.routing in (RoutingDecision.HUMAN_REVIEW, RoutingDecision.HARD_REJECT):
            return self._route(result, exc, file_path)

        # AUTO_PROCEED or AUTO_CORRECTED → generate invoice
        # ── Stage 5: Invoice Engine ────────────────────────────────────────────
        exception_summary = [
            e.correction_applied for e in exc.exceptions if e.correction_applied
        ]
        sequence   = DatabaseService.next_sequence(doc_result.data["client"]["client_id"])
        inv_result = InvoiceEngine.process(
            doc_result, proc_result, val_result, sequence,
            pipeline_confidence=exc.pipeline_confidence,
            exception_summary=exception_summary,
        )
        result.invoice = inv_result

        if inv_result.status == "FAILED":
            logger.error(f"Invoice stage failed: {inv_result.errors}")
            return result

        # ── Stage 6: Persist ──────────────────────────────────────────────────
        DatabaseService.save_invoice(inv_result.data)
        DatabaseService.log_event(
            "INVOICE_GENERATED",
            invoice_number=inv_result.data["invoice_number"],
            stage="invoice",
            status="SUCCESS",
            confidence=exc.pipeline_confidence,
            message=f"PDF: {inv_result.data.get('pdf_path')}",
        )

        result.invoice_number = inv_result.data["invoice_number"]
        result.pdf_path       = inv_result.data.get("pdf_path", "")
        result.excel_path     = inv_result.data.get("excel_path", "")

        logger.info(
            f"Pipeline complete: {result.invoice_number} | "
            f"status={result.final_status} | "
            f"pipeline_confidence={result.pipeline_confidence:.2f}"
        )
        return result

    # ── Routing helpers ────────────────────────────────────────────────────────

    def _route(
        self,
        result: PipelineResult,
        exc: ExceptionResult,
        file_path: Path,
    ) -> PipelineResult:
        """Route to human review queue using ExceptionEngine classification."""
        doc_result = result.document
        raw_data   = doc_result.data or {}
        emp_name   = (raw_data.get("employee") or {}).get("name", "")
        cli_name   = (raw_data.get("client")   or {}).get("company_name", "")

        ambiguous_fields = [af.model_dump() for af in doc_result.ambiguous_fields]
        all_errors   = (result.validation or result.processing or result.document).errors
        all_warnings = (result.validation or result.processing or result.document).warnings

        queue_id = DatabaseService.add_to_review_queue(
            stage=exc.exceptions[0].rule if exc.exceptions else "unknown",
            confidence=exc.pipeline_confidence,
            errors=all_errors,
            warnings=all_warnings,
            ambiguous_fields=ambiguous_fields,
            raw_data={
                **raw_data,
                "exception_summary": exc.to_dict(),
            },
            source_file=str(file_path),
            employee_name=emp_name,
            client_name=cli_name,
            priority=exc.review_priority,
        )

        DatabaseService.log_event(
            "ROUTED_TO_REVIEW",
            stage="exception",
            status="REVIEW_REQUIRED",
            confidence=exc.pipeline_confidence,
            message=(
                f"Queue ID: {queue_id} | "
                f"routing={exc.routing.value} | "
                f"priority={exc.review_priority} | "
                f"reason={exc.review_reason[:80]}"
            ),
        )

        result.routed_to_review = True
        result.review_queue_id  = queue_id
        logger.warning(
            f"Routed to review: queue_id={queue_id} | "
            f"routing={exc.routing.value} | "
            f"priority={exc.review_priority} | "
            f"pipeline_confidence={exc.pipeline_confidence:.2f}"
        )
        return result

    def run_batch(self, file_path) -> list[PipelineResult]:
        """
        Process a multi-row Excel file.  Each row is parsed in Python (no Gemini)
        and run through stages 2–5 of the pipeline independently.
        Returns one PipelineResult per employee row.
        """
        from utils.excel_batch import parse_batch
        from pathlib import Path as _Path

        doc_results = parse_batch(file_path)
        all_results = []
        for doc_result in doc_results:
            result = PipelineResult(
                document=doc_result,
                pipeline_confidence=doc_result.confidence,
            )

            DatabaseService.log_event(
                "DOCUMENT_PROCESSED",
                invoice_number=_Path(file_path).stem,
                stage="document",
                status=doc_result.status,
                confidence=doc_result.confidence,
                message=f"Batch row: {doc_result.metadata.get('row_index')}",
            )

            if doc_result.status == "FAILED":
                exc = ExceptionEngine.process(doc_result)
                result.exception = exc
                result.pipeline_confidence = exc.pipeline_confidence
                all_results.append(self._route(result, exc, _Path(file_path)))
                continue

            # Stage 2
            proc_result = ProcessingEngine.process(doc_result)
            result.processing = proc_result
            if proc_result.status == "FAILED":
                exc = ExceptionEngine.process(doc_result, proc_result)
                result.exception = exc
                result.pipeline_confidence = exc.pipeline_confidence
                all_results.append(self._route(result, exc, _Path(file_path)))
                continue

            # Stage 3
            existing = self._get_existing_invoices(doc_result)
            val_result = ValidationEngine.process(doc_result, proc_result, existing)
            result.validation = val_result

            # Stage 4
            exc = ExceptionEngine.process(doc_result, proc_result, val_result)
            result.exception = exc
            result.pipeline_confidence = exc.pipeline_confidence

            if exc.routing == RoutingDecision.DUPLICATE_RETURN and existing:
                inv_db = existing[0]
                result.invoice_number = inv_db["invoice_number"]
                result.pdf_path       = inv_db.get("pdf_path", "")
                result.excel_path     = inv_db.get("excel_path", "")
                result.is_duplicate   = True
                synthetic = EngineResult(stage="invoice", status="SUCCESS")
                synthetic.data = inv_db
                result.invoice = synthetic
                all_results.append(result)
                continue

            if exc.routing in (RoutingDecision.HUMAN_REVIEW, RoutingDecision.HARD_REJECT):
                all_results.append(self._route(result, exc, _Path(file_path)))
                continue

            # Stage 5
            exception_summary = [e.correction_applied for e in exc.exceptions if e.correction_applied]
            sequence   = DatabaseService.next_sequence(doc_result.data["client"]["client_id"])
            inv_result = InvoiceEngine.process(
                doc_result, proc_result, val_result, sequence,
                pipeline_confidence=exc.pipeline_confidence,
                exception_summary=exception_summary,
            )
            result.invoice = inv_result

            if inv_result.status == "SUCCESS":
                DatabaseService.save_invoice(inv_result.data)
                result.invoice_number = inv_result.data["invoice_number"]
                result.pdf_path       = inv_result.data.get("pdf_path", "")
                result.excel_path     = inv_result.data.get("excel_path", "")
                DatabaseService.log_event(
                    "INVOICE_GENERATED",
                    invoice_number=inv_result.data["invoice_number"],
                    stage="invoice", status="SUCCESS",
                    confidence=exc.pipeline_confidence,
                )

            all_results.append(result)

        return all_results

    def _get_existing_invoices(self, doc_result: EngineResult) -> list[dict]:
        try:
            emp_id    = doc_result.data["employee"]["employee_id"]
            client_id = doc_result.data["client"]["client_id"]
            return DatabaseService.list_invoices(
                employee_id=emp_id, client_id=client_id
            )
        except Exception:
            return []
