from __future__ import annotations
import json
from datetime import date

from models.schema import ExtractedDocument
from models.invoice import BillingResult, Invoice
from models.validation import EngineResult
from services.invoice_service import generate_pdf
from services.export_service import generate_erp_excel
from utils.helpers import generate_invoice_number, calculate_due_date
from utils.logger import get_logger

logger = get_logger("invoice_engine")

# In-memory sequence counter (replaced by DB sequence in Phase 6)
_sequence_counter: dict[str, int] = {}


class InvoiceEngine:

    @staticmethod
    def process(
        doc_result: EngineResult,
        proc_result: EngineResult,
        val_result: EngineResult,
        sequence: int | None = None,
        pipeline_confidence: float = 1.0,
        exception_summary: list[str] | None = None,
    ) -> EngineResult:
        """
        Runs only after validation passes.
        Generates PDF invoice + ERP Excel and returns EngineResult
        with Invoice in result.data.
        """
        result = EngineResult(stage="invoice", status="SUCCESS", confidence=1.0)

        # ── Guard: all upstream stages must have succeeded ─────────────────────
        if val_result.data and val_result.data.get("overall") == "INVALID":
            result.add_error(
                "Cannot generate invoice — validation failed. "
                f"Errors: {val_result.errors}"
            )
            return result

        if not doc_result.data or not proc_result.data:
            result.add_error("Missing upstream data — cannot generate invoice")
            return result

        try:
            doc     = ExtractedDocument(**doc_result.data)
            billing = BillingResult(**proc_result.data)
        except Exception as e:
            result.add_error(f"Failed to deserialise upstream data: {e}")
            return result

        # ── Generate invoice number ────────────────────────────────────────────
        client_id = doc.client.client_id
        if sequence is None:
            _sequence_counter[client_id] = _sequence_counter.get(client_id, 0) + 1
            sequence = _sequence_counter[client_id]

        inv_number = generate_invoice_number(client_id, sequence)
        inv_date   = date.today()
        due_date   = calculate_due_date(inv_date, doc.contract.payment_terms_days)

        invoice = Invoice(
            invoice_number=inv_number,
            invoice_date=inv_date,
            due_date=due_date,
            employee_id=doc.employee.employee_id,
            employee_name=doc.employee.name,
            client_id=client_id,
            client_name=doc.client.company_name,
            contract_id=doc.contract.contract_id,
            billing_period_start=doc.billing_period_start,
            billing_period_end=doc.billing_period_end,
            billing=billing,
            status="GENERATED",
            pipeline_confidence=round(pipeline_confidence, 3),
            exception_summary=exception_summary or [],
        )

        # ── Generate PDF ───────────────────────────────────────────────────────
        try:
            pdf_path = generate_pdf(invoice)
            invoice.pdf_path = str(pdf_path)
            logger.info(f"PDF → {pdf_path.name}")
        except Exception as e:
            result.add_warning(f"PDF generation failed: {e}")
            invoice.pdf_path = None

        # ── Generate ERP Excel ─────────────────────────────────────────────────
        try:
            excel_path = generate_erp_excel(invoice)
            invoice.excel_path = str(excel_path)
            logger.info(f"ERP Excel → {excel_path.name}")
        except Exception as e:
            result.add_warning(f"ERP Excel generation failed: {e}")
            invoice.excel_path = None

        result.data = json.loads(invoice.model_dump_json())
        result.metadata["invoice_number"] = inv_number
        result.metadata["pdf_path"]       = invoice.pdf_path
        result.metadata["excel_path"]     = invoice.excel_path

        logger.info(
            f"Invoice generated: {inv_number} | "
            f"{doc.employee.name} → {doc.client.company_name} | "
            f"{billing.currency} {billing.total_amount:,.2f}"
        )
        return result
