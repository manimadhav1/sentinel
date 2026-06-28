from __future__ import annotations
import json
import urllib.request
from utils.logger import get_logger

logger = get_logger("exchange_rates")

_FALLBACK: dict[str, float] = {
    "INR": 1.0, "USD": 83.5, "EUR": 90.2,
    "GBP": 105.3, "AED": 22.7, "SGD": 61.8,
}

_cached: dict[str, float] | None = None


def get_rates_to_inr() -> dict[str, float]:
    """
    Fetch live exchange rates to INR via frankfurter.app (no API key needed).
    Caches result for the session lifetime. Falls back to hardcoded values if
    the API is unreachable.
    """
    global _cached
    if _cached is not None:
        return _cached

    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=INR,EUR,GBP,AED,SGD"
        req = urllib.request.Request(url, headers={"User-Agent": "sentinel/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        # data["rates"] = {"INR": 83.5, "EUR": 0.92, "GBP": 0.79, "AED": 3.67, "SGD": 1.34}
        # 1 AED in INR = INR_per_USD / AED_per_USD
        rates = data.get("rates", {})
        inr_per_usd = float(rates.get("INR", _FALLBACK["USD"]))

        result: dict[str, float] = {"INR": 1.0, "USD": inr_per_usd}
        for currency in ("EUR", "GBP", "AED", "SGD"):
            usd_rate = float(rates.get(currency, 0))
            if usd_rate > 0:
                result[currency] = round(inr_per_usd / usd_rate, 4)
            else:
                result[currency] = _FALLBACK.get(currency, 1.0)

        _cached = result
        logger.info(f"Live exchange rates (to INR): {result}")
        return result

    except Exception as exc:
        logger.warning(f"Exchange rate API unavailable ({exc}) — using fallback rates")
        return dict(_FALLBACK)
