from __future__ import annotations
from datetime import date, datetime
from config import EXCHANGE_RATES_TO_INR, CURRENCY_SYMBOLS, INVOICE_PREFIX


def convert_to_inr(amount: float, currency: str) -> float:
    rate = EXCHANGE_RATES_TO_INR.get(currency.upper(), 1.0)
    return round(amount * rate, 2)


def format_currency(amount: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency)
    return f"{symbol}{amount:,.2f}"


def generate_invoice_number(client_id: str, sequence: int) -> str:
    year = datetime.utcnow().year
    return f"{INVOICE_PREFIX}-{year}-{client_id.upper()[:6]}-{sequence:04d}"


def calculate_due_date(invoice_date: date, payment_terms_days: int) -> date:
    from datetime import timedelta
    return invoice_date + timedelta(days=payment_terms_days)


def round_hours(hours: float) -> float:
    return round(hours, 2)


def safe_divide(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    if denominator == 0:
        return fallback
    return numerator / denominator
