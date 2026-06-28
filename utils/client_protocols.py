from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

from config import CLIENT_PROTOCOLS_PATH
from utils.logger import get_logger

logger = get_logger("client_protocols")

_FALLBACK: dict[str, dict] = {}


@lru_cache(maxsize=1)
def load_protocols() -> dict[str, dict]:
    """
    Load per-client staffing agreement rules from client_protocols.json.
    Cached after first load. Falls back to empty dict if file missing.
    """
    path = Path(CLIENT_PROTOCOLS_PATH)
    if not path.exists():
        logger.warning(f"client_protocols.json not found at {path} — per-client rules disabled")
        return _FALLBACK
    try:
        data = json.loads(path.read_text())
        logger.info(f"Loaded protocols for {len(data)} clients from {path.name}")
        return data
    except Exception as exc:
        logger.error(f"Failed to load client_protocols.json: {exc}")
        return _FALLBACK


def get_protocol(client_id: str) -> dict:
    """Return the protocol dict for a given client ID, or {} if unknown."""
    return load_protocols().get(client_id, {})


def get_ot_cap(client_id: str) -> float | None:
    return get_protocol(client_id).get("ot_cap_monthly_hours")


def get_ot_multiplier(client_id: str) -> float:
    return float(get_protocol(client_id).get("ot_multiplier", 1.5))


def po_required(client_id: str) -> bool:
    return bool(get_protocol(client_id).get("po_required", False))


def get_po_regex(client_id: str) -> str | None:
    return get_protocol(client_id).get("po_format")


def get_sla_hours(client_id: str) -> int:
    return int(get_protocol(client_id).get("sla_hours", 24))


def get_working_day_range(client_id: str) -> tuple[int, int]:
    p = get_protocol(client_id)
    return int(p.get("valid_working_days_min", 20)), int(p.get("valid_working_days_max", 26))


def get_rate_tolerance(client_id: str) -> int:
    """Tolerance in days vs Schedule A (0 = exact match required, 1 = ±1 day allowed)."""
    return int(get_protocol(client_id).get("rate_tolerance_days", 1))


def get_special_rules(client_id: str) -> list[str]:
    return get_protocol(client_id).get("special_rules", [])


def get_document_requirements(client_id: str) -> list[str]:
    return get_protocol(client_id).get("document_requirements", [])


def get_leave_codes(client_id: str) -> list[str]:
    return get_protocol(client_id).get("leave_codes", [])
