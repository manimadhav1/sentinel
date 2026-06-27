from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from engines.document_engine import DocumentEngine
from engines.processing_engine import ProcessingEngine
from engines.validation_engine import ValidationEngine
from engines.invoice_engine import InvoiceEngine
from services.database_service import DatabaseService
from models.validation import EngineResult
from utils.logger import get_logger

logger = get_logger("pipeline")


@dataclass
class PipelineResult:
    document:   EngineResult
    processing: EngineResult | None = None
    validation: EngineResult | None = None
    invoice:    EngineResult | None = None
    invoice_number: str = ""
    pdf_path:   str = ""
    excel_path: str = ""
    routed_to_review: bool = False
    review_queue_id:  int | None = None

    @property
    def success(self) -> bool:
        return (
            self.invoice is not None and
            self.invoice.status == "SUCCESS" and
            not self.routed_to_review
        )

    @property
    def final_status(self) -> str:
        if self.routed_to_review:
            return "REVIEW_REQUIRED"
        if self.invoice and self.invoice.status == "SUCCESS":
            return "COMPLETE"
        for stage in [self.validation, self.processing, self.document]:
            if stage and stage.status == "FAILED":
                return "FAILED"
        return "UNKNOWN"

    def summary(self) -> dict:
        return {
            "status":           self.final_status,
            "invoice_number":   self.invoice_number,
            "pdf_path":         self.pdf_path,
            "excel_path":       self.excel_path,
            "routed_to_review": self.routed_to_review,
            "review_queue_id":  self.review_queue_id,
            "document_confidence": self.document.confidence,
            "errors":  (self.invoice or self.validation or
                        self.processing or self.document).errors,
            "warnings":(self.invoice or self.validation or
                        self.processing or self.document).warnings,
        }


class SentinelPipeline:
    """
    Orchestrates the full invoice automation pipeline.
    Document → Processing → Validation → Invoice → Database
    """

    def __init__(self):
        DatabaseService.initialise()

    def run(self, file_path: str | Path) -> PipelineResult:
        file_path = Path(file_path)
        logger.info(f"Pipeline started: {file_path.name}")

        result = PipelineResult(document=EngineResult(stage="document",
                                                       status="PENDING"))

        # ── Stage 1: Document Engine ───────────────────────────────────────────
        doc_result = DocumentEngine.process(file_path)
        result.document = doc_result

        _inv_ref = file_path.stem  # temporary reference until invoice number known
        DatabaseService.log_event(
            "DOCUMENT_PROCESSED",
            invoice_number=_inv_ref,
            stage="document",
            status=doc_result.status,
            confidence=doc_result.confidence,
            message=f"File: {file_path.name}",
        )

        if doc_result.status == "FAILED":
            logger.error(f"Document stage failed: {doc_result.errors}")
            return result

        # Route to human review if confidence too low
        if doc_result.requires_human_review:
            return self._route_to_review(result, doc_result, file_path)

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
            logger.error(f"Processing stage failed: {proc_result.errors}")
            return result

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

        if val_result.requires_human_review or val_result.status == "FAILED":
            return self._route_to_review(result, val_result, file_path)

        # ── Stage 4: Invoice Engine ────────────────────────────────────────────
        sequence   = DatabaseService.next_sequence(doc_result.data["client"]["client_id"])
        inv_result = InvoiceEngine.process(doc_result, proc_result, val_result, sequence)
        result.invoice = inv_result

        if inv_result.status == "FAILED":
            logger.error(f"Invoice stage failed: {inv_result.errors}")
            return result

        # ── Stage 5: Persist to database ──────────────────────────────────────
        DatabaseService.save_invoice(inv_result.data)
        DatabaseService.log_event(
            "INVOICE_GENERATED",
            invoice_number=inv_result.data["invoice_number"],
            stage="invoice",
            status="SUCCESS",
            confidence=1.0,
            message=f"PDF: {inv_result.data.get('pdf_path')}",
        )

        result.invoice_number = inv_result.data["invoice_number"]
        result.pdf_path       = inv_result.data.get("pdf_path", "")
        result.excel_path     = inv_result.data.get("excel_path", "")

        logger.info(
            f"Pipeline complete: {result.invoice_number} | "
            f"status={result.final_status}"
        )
        return result

    def _route_to_review(
        self,
        result: PipelineResult,
        failed_stage: EngineResult,
        file_path: Path,
    ) -> PipelineResult:
        priority = failed_stage.metadata.get("priority", "NORMAL")
        raw_data = failed_stage.data or {}

        # Extract employee/client names if available
        emp_name = ""
        cli_name = ""
        if failed_stage.data:
            emp_name = (failed_stage.data.get("employee") or {}).get("name", "")
            cli_name = (failed_stage.data.get("client") or {}).get("company_name", "")

        queue_id = DatabaseService.add_to_review_queue(
            stage=failed_stage.stage,
            confidence=failed_stage.confidence,
            errors=failed_stage.errors,
            warnings=failed_stage.warnings,
            ambiguous_fields=[af.model_dump() for af in failed_stage.ambiguous_fields],
            raw_data=raw_data,
            source_file=str(file_path),
            employee_name=emp_name,
            client_name=cli_name,
            priority=priority,
        )
        DatabaseService.log_event(
            "ROUTED_TO_REVIEW",
            stage=failed_stage.stage,
            status="REVIEW_REQUIRED",
            confidence=failed_stage.confidence,
            message=f"Queue ID: {queue_id} | Priority: {priority}",
        )

        result.routed_to_review = True
        result.review_queue_id  = queue_id
        logger.warning(
            f"Routed to human review: queue_id={queue_id} "
            f"stage={failed_stage.stage} confidence={failed_stage.confidence:.2f}"
        )
        return result

    def _get_existing_invoices(self, doc_result: EngineResult) -> list[dict]:
        """Fetch existing invoices for duplicate detection."""
        try:
            emp_id    = doc_result.data["employee"]["employee_id"]
            client_id = doc_result.data["client"]["client_id"]
            return DatabaseService.list_invoices(
                employee_id=emp_id, client_id=client_id
            )
        except Exception:
            return []
