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

For payroll/salary documents that lack daily timesheet rows:
- Set timesheet to [] (the system will synthesise entries from contracted_hours)
- Set contracted_hours = days_worked * 8 if explicit daily count is given
- Set billing_rate = basic_salary / contracted_hours if no explicit rate is given
- Set billing_period_start to the first day of the pay period month
- Set billing_period_end to the last day of the pay period month
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
