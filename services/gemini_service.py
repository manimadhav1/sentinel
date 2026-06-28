from __future__ import annotations
import json
import re
import base64
import time
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL
from utils.logger import get_logger

logger = get_logger("gemini_service")

_client = genai.Client(api_key=GEMINI_API_KEY)

_RETRY_DELAYS = [3, 8, 20]  # seconds between retries


def _call_with_retry(model: str, contents) -> object:
    """Call Gemini with exponential backoff on 503/429 errors."""
    last_exc = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            logger.warning(f"Gemini unavailable — retrying in {delay}s (attempt {attempt+1})")
            time.sleep(delay)
        try:
            return _client.models.generate_content(model=model, contents=contents)
        except Exception as e:
            msg = str(e)
            if "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "quota" in msg.lower():
                last_exc = e
            else:
                raise
    raise last_exc

EXTRACTION_PROMPT = """
You are an intelligent document parser for an enterprise invoice automation system.

Your job is to extract structured data from the uploaded document and return it as a single valid JSON object.

Extract the following fields:

{
  "employee": {
    "employee_id": "string or null",
    "name": "string",
    "designation": "string or null",
    "department": "string or null",
    "email": "string or null",
    "hsn_code": "string or null"
  },
  "client": {
    "client_id": "string or null",
    "company_name": "string",
    "billing_address": "string or null",
    "country": "string",
    "currency": "string (ISO 4217 code e.g. INR, USD, GBP)",
    "gst_number": "string or null",
    "timezone": "string or null",
    "contact_email": "string or null"
  },
  "contract": {
    "contract_id": "string or null",
    "billing_rate": "number",
    "currency": "string",
    "billing_type": "hourly or daily or fixed",
    "contracted_hours": "number or null",
    "overtime_allowed": "boolean",
    "overtime_multiplier": "number (default 1.5)",
    "early_completion_policy": "pay_full or pay_actual",
    "late_penalty_per_hour": "number (default 0)",
    "gst_applicable": "boolean",
    "gst_rate": "number (e.g. 0.18 for 18%)",
    "payment_terms_days": "number (default 30)"
  },
  "timesheet": [
    {
      "date": "YYYY-MM-DD",
      "employee_id": "string",
      "hours_worked": "number",
      "task_description": "string or null",
      "overtime_hours": "number (default 0)"
    }
  ],
  "billing_period_start": "YYYY-MM-DD",
  "billing_period_end": "YYYY-MM-DD",
  "confidence_scores": {
    "employee": "0.0 to 1.0",
    "client": "0.0 to 1.0",
    "contract": "0.0 to 1.0",
    "timesheet": "0.0 to 1.0",
    "overall": "0.0 to 1.0"
  },
  "ambiguous_fields": [
    {
      "field": "field_name",
      "reason": "why it is ambiguous",
      "extracted_value": "what was found",
      "suggested_value": "best guess or null"
    }
  ],
  "extraction_notes": "any observations about document quality"
}

Rules:
- Return ONLY valid JSON. No markdown, no explanation, no code blocks.
- If a field is not present in the document, use null.
- For dates, always use YYYY-MM-DD format.
- For currency, use ISO 4217 codes (INR, USD, GBP, EUR, AED, SGD).
- Confidence score of 1.0 means you are certain. 0.5 means you guessed.
- Only list fields in ambiguous_fields if they are CRITICAL and cannot be inferred. Do NOT flag optional fields (hsn_code, billing_address, timezone, task_description) or fields with safe defaults (overtime_multiplier, payment_terms_days).
- If handwriting is unclear, still attempt extraction and lower the confidence score.

Client ID mapping (apply automatically when you see these codes in the document):
- CUST001 → CL001, CUST002 → CL002, CUST003 → CL003, CUST004 → CL004,
  CUST005 → CL005, CUST006 → CL006, CUST007 → CL007, CUST008 → CL008

UNIVERSAL DOCUMENT HANDLING — apply regardless of column names or format:
- Employee identification: look for any column containing "emp", "id", "staff", "worker", "name", "personnel"
- Client/customer: look for "client", "customer", "cust", "company", "org", "account"
- Hours worked: look for "hours", "days", "working_days", "days_worked", "duration", "time"
  → If days are given, multiply by 8 to get hours
- Billing rate: look for "rate", "salary", "pay", "wage", "cost", "price", "amount_per"
  → If monthly salary given, divide by total hours to get hourly rate
- Dates/period: look for "date", "period", "month", "week", "from", "to", "start", "end"
  → If only a month name or "June 2026" is given, use first and last day of that month
- Amount/total: look for "amount", "total", "gross", "net", "billed", "invoice"

For payroll/salary documents that lack daily timesheet rows:
- Set timesheet to [] (the system will synthesise daily entries from contracted_hours)
- Set contracted_hours = days_worked * 8 if day count is available
- Set billing_rate = salary / contracted_hours if no explicit rate exists
- Set billing_period_start to the 1st of the pay period month
- Set billing_period_end to the last day of the pay period month
- Set contract_id to null (system will derive it from employee+client IDs)
"""


def _encode_image(file_path: Path) -> tuple[str, str]:
    ext = file_path.suffix.lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    data = base64.standard_b64encode(file_path.read_bytes()).decode("utf-8")
    return mime, data


def _extract_json(raw: str) -> dict:
    """Strip markdown fences if present and parse JSON."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return json.loads(cleaned)


def call_gemini(file_path: Path, file_type: str) -> dict:
    """
    Single Gemini API call. Accepts any supported file type.
    Returns raw extracted dict (not yet validated against Pydantic).
    """
    logger.info(f"Calling Gemini for {file_path.name} (type={file_type})")

    if file_type == "image":
        mime, data = _encode_image(file_path)
        response = _call_with_retry(
            model=GEMINI_MODEL,
            contents=[
                EXTRACTION_PROMPT,
                types.Part.from_bytes(data=base64.b64decode(data), mime_type=mime),
            ],
        )

    elif file_type == "pdf":
        pdf_bytes = file_path.read_bytes()
        response = _call_with_retry(
            model=GEMINI_MODEL,
            contents=[
                EXTRACTION_PROMPT,
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            ],
        )

    elif file_type in ("excel", "csv"):
        text = _read_tabular(file_path, file_type)
        response = _call_with_retry(
            model=GEMINI_MODEL,
            contents=EXTRACTION_PROMPT + f"\n\nDocument content:\n{text}",
        )

    else:
        raise ValueError(f"Unsupported file type for Gemini: {file_type}")

    raw = response.text
    logger.debug(f"Gemini raw response length: {len(raw)} chars")

    extracted = _extract_json(raw)
    logger.info(f"Extraction complete. Overall confidence: {extracted.get('confidence_scores', {}).get('overall', 'N/A')}")
    return extracted


_CLIENT_PROTOCOLS = {
    "CL001": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 20, "po_required": True,  "po_format": "PO-AD-#####",      "valid_working_days": "20-26", "rate_tolerance": 1},
    "CL002": {"ot_multiplier": 1.25,"ot_cap_monthly_hours": 15, "po_required": True,  "po_format": "PHD-PO-2026-###",  "valid_working_days": "20-26", "rate_tolerance": 0, "special": "no handwritten docs"},
    "CL003": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 25, "po_required": False,                                   "valid_working_days": "20-26", "rate_tolerance": 0},
    "CL004": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 10, "po_required": True,  "po_format": "ADE-PO-######",   "valid_working_days": "20-26", "rate_tolerance": 0, "special": "HSE sign-off required for OT"},
    "CL005": {"ot_multiplier": 1.25,"ot_cap_monthly_hours": 15, "po_required": False,                                   "valid_working_days": "20-26", "rate_tolerance": 1},
    "CL006": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 8,  "po_required": True,  "po_format": "CGB-FIN-####",    "valid_working_days": "20-26", "rate_tolerance": 0, "special": "dual sign-off required"},
    "CL007": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 30, "po_required": True,  "po_format": "BHL-PO-####",     "valid_working_days": "20-26", "rate_tolerance": 1, "special": "OT must include shift ID"},
    "CL008": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 25, "po_required": False,                                   "valid_working_days": "20-26", "rate_tolerance": 0, "special": "handwritten docs need stamp"},
    "CL009": {"ot_multiplier": 1.25,"ot_cap_monthly_hours": 15, "po_required": True,  "po_format": "SPG-PO-2026-###", "valid_working_days": "20-26", "rate_tolerance": 1},
    "CL010": {"ot_multiplier": 1.5, "ot_cap_monthly_hours": 35, "po_required": False,                                   "valid_working_days": "20-26", "rate_tolerance": 1},
}

_VERIFICATION_PROMPT = """
You are a senior document verification specialist for an enterprise staffing invoice system.

A first AI pass extracted data from a document but flagged the following AMBIGUOUS FIELDS that need verification:

AMBIGUOUS FIELDS TO VERIFY:
{ambiguous_json}

FIRST PASS EXTRACTION (full context):
{extraction_json}

CLIENT PROTOCOLS & GUIDELINES for {client_id}:
{protocols_json}

Your task:
1. Re-examine EACH ambiguous field carefully using all context clues in the extraction
2. Apply the client protocols to validate or correct values (e.g., OT multiplier, PO format)
3. If billing_period is ambiguous, use the timesheet dates as ground truth
4. For employee/client IDs: cross-reference names, PO numbers, and contract IDs in the extraction
5. Correct values only when you have evidence — do NOT guess without justification

Return ONLY valid JSON in this exact format:
{{
  "corrections": {{
    "field_name": {{
      "confirmed_value": <corrected or confirmed value>,
      "confidence": <0.0 to 1.0>,
      "reason": "<evidence for this value>"
    }}
  }},
  "overall_verification_confidence": <0.0 to 1.0>,
  "verification_notes": "<summary of what was verified and how>"
}}

If you cannot improve confidence on a field, still include it with the original value and your reasoning.
Return ONLY the JSON object — no markdown, no explanation.
"""


def verify_ambiguous_fields(
    file_path: Path,
    file_type: str,
    extraction: dict,
    ambiguous_fields: list[dict],
) -> dict:
    """
    Second-pass Gemini call to verify and correct ambiguous fields.
    Returns a dict of field_name → corrected value for fields where confidence improved.
    """
    if not ambiguous_fields:
        return {}

    client_id = (extraction.get("client") or {}).get("client_id", "UNKNOWN")
    protocols = _CLIENT_PROTOCOLS.get(client_id, {})

    import json as _json
    prompt = _VERIFICATION_PROMPT.format(
        ambiguous_json=_json.dumps(ambiguous_fields, indent=2),
        extraction_json=_json.dumps(extraction, indent=2, default=str),
        client_id=client_id,
        protocols_json=_json.dumps(protocols, indent=2) if protocols else "Not available — apply general staffing guidelines",
    )

    logger.info(f"Running verification pass for {len(ambiguous_fields)} ambiguous field(s) | client={client_id}")

    try:
        if file_type == "image":
            mime, data = _encode_image(file_path)
            response = _call_with_retry(
                model=GEMINI_MODEL,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=base64.b64decode(data), mime_type=mime),
                ],
            )
        elif file_type == "pdf":
            pdf_bytes = file_path.read_bytes()
            response = _call_with_retry(
                model=GEMINI_MODEL,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                ],
            )
        else:
            # For tabular formats, text-only is sufficient — the extraction already has content
            response = _call_with_retry(
                model=GEMINI_MODEL,
                contents=prompt,
            )

        result = _extract_json(response.text)
        corrections = result.get("corrections", {})
        logger.info(
            f"Verification complete — {len(corrections)} field(s) resolved | "
            f"confidence={result.get('overall_verification_confidence', 'N/A')}"
        )
        return result

    except Exception as exc:
        logger.warning(f"Verification pass failed ({exc}) — continuing with first-pass extraction")
        return {}


def _read_tabular(file_path: Path, file_type: str) -> str:
    """Convert Excel/CSV to plain text for prompt injection."""
    import pandas as pd
    if file_type == "excel":
        df = pd.read_excel(file_path, sheet_name=None)
        parts = []
        for sheet_name, sheet_df in df.items():
            parts.append(f"Sheet: {sheet_name}\n{sheet_df.to_string(index=False)}")
        return "\n\n".join(parts)
    else:
        import pandas as pd
        df = pd.read_csv(file_path)
        return df.to_string(index=False)
