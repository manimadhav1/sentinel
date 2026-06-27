from __future__ import annotations
import json
from datetime import date

from models.schema import ExtractedDocument, Contract, TimesheetEntry
from models.invoice import BillingResult, LineItem
from models.validation import EngineResult
from utils.helpers import convert_to_inr, round_hours
from utils.logger import get_logger

logger = get_logger("processing_engine")


class ProcessingEngine:

    @staticmethod
    def process(engine_result: EngineResult) -> EngineResult:
        """
        Accepts the EngineResult from DocumentEngine.
        Returns a new EngineResult with BillingResult in result.data.
        Pure Python — no AI.
        """
        result = EngineResult(stage="processing", status="SUCCESS", confidence=1.0)

        if not engine_result.is_ok() and engine_result.status != "AMBIGUOUS":
            result.add_error("Cannot process — upstream document stage failed")
            return result

        try:
            doc = ExtractedDocument(**engine_result.data)
        except Exception as e:
            result.add_error(f"Failed to deserialise document: {e}")
            return result

        try:
            billing = ProcessingEngine._calculate_billing(doc, result)
        except Exception as e:
            result.add_error(f"Billing calculation error: {e}")
            return result

        result.data = json.loads(billing.model_dump_json())
        logger.info(
            f"Processing complete | employee={doc.employee.name} | "
            f"total={billing.total_amount} {billing.currency}"
        )
        return result

    # ── Core billing logic ─────────────────────────────────────────────────────

    @staticmethod
    def _calculate_billing(doc: ExtractedDocument, result: EngineResult) -> BillingResult:
        contract = doc.contract
        timesheet = doc.timesheet
        line_items: list[LineItem] = []
        notes: list[str] = []

        # ── Step 1: Aggregate hours ────────────────────────────────────────────
        total_hours = round_hours(sum(e.hours_worked for e in timesheet))
        declared_ot = round_hours(sum(e.overtime_hours for e in timesheet))

        # ── Step 2: Determine regular vs overtime hours ────────────────────────
        contracted = contract.contracted_hours or total_hours

        if total_hours <= contracted:
            # Under or exactly on contracted hours
            regular_hours, overtime_hours = ProcessingEngine._apply_early_completion(
                total_hours, contracted, contract, notes
            )
        else:
            # Exceeded contracted hours
            regular_hours, overtime_hours = ProcessingEngine._apply_overtime(
                total_hours, contracted, contract, notes, result
            )

        # ── Step 3: Calculate amounts ──────────────────────────────────────────
        rate = contract.billing_rate
        regular_amount = round(regular_hours * rate, 2)
        overtime_rate = rate * contract.overtime_multiplier
        overtime_amount = round(overtime_hours * overtime_rate, 2)
        subtotal = round(regular_amount + overtime_amount, 2)

        # ── Step 4: Late penalty ───────────────────────────────────────────────
        penalty_amount = 0.0
        if total_hours > contracted and contract.late_penalty_per_hour > 0:
            excess = round_hours(total_hours - contracted)
            penalty_amount = round(excess * contract.late_penalty_per_hour, 2)
            subtotal = round(subtotal - penalty_amount, 2)
            notes.append(f"Late penalty applied: {excess}h × {contract.late_penalty_per_hour} = {penalty_amount}")
            line_items.append(LineItem(
                description="Late completion penalty",
                hours=excess,
                rate=contract.late_penalty_per_hour,
                amount=-penalty_amount,
            ))

        # ── Step 5: GST ────────────────────────────────────────────────────────
        gst_amount = 0.0
        if contract.gst_applicable:
            gst_amount = round(subtotal * contract.gst_rate, 2)
            notes.append(f"GST @ {int(contract.gst_rate * 100)}% = {gst_amount}")

        total_amount = round(subtotal + gst_amount, 2)

        # ── Step 6: Currency conversion ────────────────────────────────────────
        currency = contract.currency
        rate_to_inr = 1.0
        total_inr = total_amount

        if currency != "INR":
            from config import EXCHANGE_RATES_TO_INR
            rate_to_inr = EXCHANGE_RATES_TO_INR.get(currency, 1.0)
            total_inr = round(total_amount * rate_to_inr, 2)
            notes.append(f"Currency: {currency} → INR @ {rate_to_inr}")

        # ── Step 7: Build line items ───────────────────────────────────────────
        line_items.insert(0, LineItem(
            description=f"Regular hours ({regular_hours}h × {rate} {currency}/hr)",
            hours=regular_hours,
            rate=rate,
            amount=regular_amount,
        ))

        if overtime_hours > 0:
            line_items.insert(1, LineItem(
                description=f"Overtime hours ({overtime_hours}h × {overtime_rate} {currency}/hr)",
                hours=overtime_hours,
                rate=overtime_rate,
                amount=overtime_amount,
            ))

        return BillingResult(
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            regular_amount=regular_amount,
            overtime_amount=overtime_amount,
            subtotal=subtotal,
            gst_amount=gst_amount,
            total_amount=total_amount,
            currency=currency,
            exchange_rate_to_inr=rate_to_inr,
            total_amount_inr=total_inr,
            line_items=line_items,
            billing_notes=notes,
        )

    # ── Contract scenario handlers ─────────────────────────────────────────────

    @staticmethod
    def _apply_early_completion(
        actual: float, contracted: float,
        contract: Contract, notes: list
    ) -> tuple[float, float]:
        """Task completed early or on time."""
        if actual == contracted:
            notes.append("Completed exactly on contracted hours.")
            return actual, 0.0

        # Under-delivery
        if contract.early_completion_policy == "pay_full":
            notes.append(
                f"Early completion: billing full contracted {contracted}h "
                f"(policy=pay_full)"
            )
            return contracted, 0.0
        else:
            notes.append(
                f"Early completion: billing actual {actual}h "
                f"(policy=pay_actual)"
            )
            return actual, 0.0

    @staticmethod
    def _apply_overtime(
        actual: float, contracted: float,
        contract: Contract, notes: list,
        result: EngineResult,
    ) -> tuple[float, float]:
        """Task exceeded contracted hours."""
        excess = round_hours(actual - contracted)

        if contract.overtime_allowed:
            notes.append(
                f"Overtime: {excess}h excess at {contract.overtime_multiplier}x rate"
            )
            return contracted, excess
        else:
            result.add_warning(
                f"{excess}h worked beyond contracted hours but overtime not allowed — "
                f"billing contracted hours only"
            )
            notes.append("Overtime not allowed per contract — excess hours unbilled.")
            return contracted, 0.0
