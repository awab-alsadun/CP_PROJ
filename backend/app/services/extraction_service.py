"""
Extraction Service
------------------
Sends OCR text to OpenAI and receives structured invoice JSON.
Derives Phase A compliance signals from the extraction result.

Returns: (extraction_dict, signals: list[dict], had_llm_retry: bool)

Signals shape:
  {flag_type: str, severity: str, reason: str, subkey?: str}
  subkey is used to distinguish multiple required_field_null flags
  on the same invoice.

OCR signals (ocr_low_quality, ocr_fallback_used) are NOT computed here —
the caller (invoice_processor) adds them before computing final confidence,
because OCR state lives outside this service.
"""

import json
import time
import logging

from openai import OpenAI

from app.core.config import get_settings

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert financial document parser specialized in extracting structured data from invoices.

Your task is to extract ALL relevant information from the provided invoice text and return ONLY a valid JSON object that strictly follows the schema below.

You MUST:
- Return ONLY valid JSON (no explanations, no text outside JSON)
- Fill all required fields
- Use null for missing optional values
- Ensure all numeric fields are numbers (not strings)
- Ensure all dates follow YYYY-MM-DD format
- Ensure totals are mathematically consistent
- Do not hallucinate values — if unsure, use null

If data is inconsistent:
- Still return best-effort values
- Do NOT fix numbers silently
- Let totals reflect the document, even if incorrect

### EXTRACTION RULES:
1. Currency: always return ISO code (USD, EUR, TRY). If you see $ infer USD, € infer EUR, ₺ infer TRY. Never return the symbol itself.
2. For addresses in format "City, STATE ZIP": extract city before the comma, state code after the comma, 5-digit number as postal_code. If no country is written figure the country based on the state code and write as 3-letter ISO abbreviation (like USA, KSA, EGY, DEN, FIN, BAH). Always use exactly 3 letters.
3. If a field is genuinely absent from the document, return null. Do not hallucinate.

### JSON SCHEMA:
{
  "schema_version": "1.0",
  "document_metadata": {
    "document_type": "invoice",
    "extraction_timestamp": "ISO-8601",
    "confidence_score": 0.0
  },
  "invoice": {
    "invoice_number": "string",
    "issue_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD or null",
    "currency": "string",
    "tax_percent": 0.0,
    "subtotal": 0.0,
    "total_tax": 0.0,
    "grand_total": 0.0,
    "payment_method": "string or null",
    "description": "string or null",
    "discount": 0.0,
    "status": "draft"
  },
  "vendor": {
    "name": "string",
    "tax_id": "string",
    "email": "string or null",
    "phone": "string or null",
    "address": {
      "street": "string or null",
      "city": "string or null",
      "state": "string or null",
      "postal_code": "string or null",
      "country": "string or null"
    }
  },
  "client": {
    "name": "string",
    "tax_id": "string",
    "email": "string or null",
    "phone": "string or null",
    "address": {
      "street": "string or null",
      "city": "string or null",
      "state": "string or null",
      "postal_code": "string or null",
      "country": "string or null"
    }
  },
  "line_items": [
    {
      "description": "string",
      "quantity": 0.0,
      "unit_price": 0.0,
      "line_subtotal": 0.0,
      "discount": 0.0
    }
  ],
  "payments": [
    {
      "payment_date": "YYYY-MM-DD",
      "amount": 0.0,
      "method": "string or null",
      "reference": "string or null"
    }
  ]
}

Return ONLY the JSON object. No markdown. No explanation.

### INPUT TEXT:
"""

# Confidence penalty weights (only signals that affect confidence)
PHASE_A_PENALTIES = {
    "required_field_null":    0.10,   # per occurrence
    "line_item_sum_mismatch": 0.10,
    "ocr_low_quality":        0.20,
    "ocr_fallback_used":      0.10,
    "llm_retry":              0.15,
    "date_fallback_used":     0.20,
    "tax_id_fallback_used":   0.05,
    "currency_invalid":       0.10,
}

REQUIRED_FIELDS = {
    "invoice_number": lambda e: e.get("invoice", {}).get("invoice_number"),
    "issue_date":     lambda e: e.get("invoice", {}).get("issue_date"),
    "grand_total":    lambda e: e.get("invoice", {}).get("grand_total"),
    "vendor.name":    lambda e: e.get("vendor", {}).get("name"),
    "client.name":    lambda e: e.get("client", {}).get("name"),
}


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _derive_signals(extraction: dict, had_retry: bool) -> list[dict]:
    """Derive Phase A signals from the extraction result (excluding OCR signals)."""
    signals: list[dict] = []
    inv = extraction.get("invoice", {}) or {}

    # required_field_null — one signal per missing required field
    for field, getter in REQUIRED_FIELDS.items():
        val = getter(extraction)
        is_null = val is None or (isinstance(val, str) and not val.strip())
        if is_null:
            signals.append({
                "flag_type": "required_field_null",
                "severity":  "high",
                "reason":    f"Required field {field} was null after extraction",
                "subkey":    field,
            })

    # line_item_sum_mismatch
    try:
        subtotal = float(inv.get("subtotal") or 0)
        items = extraction.get("line_items", []) or []
        if subtotal > 0 and items:
            items_sum = sum(float(i.get("line_subtotal") or 0) for i in items)
            diff = abs(items_sum - subtotal)
            if diff > 0.01:
                signals.append({
                    "flag_type": "line_item_sum_mismatch",
                    "severity":  "medium",
                    "reason":    f"Line items sum ≠ subtotal (off by ${diff:.2f})",
                })
    except (TypeError, ValueError):
        pass

    # llm_retry — fired if any JSON retry happened
    if had_retry:
        signals.append({
            "flag_type": "llm_retry",
            "severity":  "high",
            "reason":    "LLM extraction required retry — output may be unstable",
        })

    # date_fallback_used
    fallback_fields = []
    if inv.get("issue_date") == "1900-01-01":
        fallback_fields.append("issue_date")
    if inv.get("due_date") == "1900-01-01":
        fallback_fields.append("due_date")
    if fallback_fields:
        signals.append({
            "flag_type": "date_fallback_used",
            "severity":  "high",
            "reason":    f"{', '.join(fallback_fields)} used the NOT NULL fallback — extraction failed",
        })

    # tax_id_fallback_used
    vt = ((extraction.get("vendor") or {}).get("tax_id") or "").upper()
    ct = ((extraction.get("client") or {}).get("tax_id") or "").upper()
    if vt == "N/A" or ct == "N/A":
        signals.append({
            "flag_type": "tax_id_fallback_used",
            "severity":  "low",
            "reason":    "tax_id field used the fallback — extraction couldn't find it",
        })

    # currency_invalid
    currency = (inv.get("currency") or "").strip()
    if not currency or len(currency) != 3 or not currency.isalpha():
        signals.append({
            "flag_type": "currency_invalid",
            "severity":  "medium",
            "reason":    "Currency is missing or not a valid ISO code",
        })

    # missing_due_date — Phase A flag with NO confidence penalty
    if not inv.get("due_date"):
        signals.append({
            "flag_type": "missing_due_date",
            "severity":  "medium",
            "reason":    "Invoice has no due_date",
        })

    return signals


def compute_confidence(signals: list[dict]) -> float:
    """
    Compute confidence in [0.0, 1.0] by summing penalties for each signal
    and subtracting from 1.0. Signals not in PHASE_A_PENALTIES contribute 0.
    """
    total = 0.0
    for sig in signals:
        total += PHASE_A_PENALTIES.get(sig.get("flag_type"), 0.0)
    return round(max(0.0, min(1.0, 1.0 - total)), 4)


def extract_structured_data(raw_text: str) -> tuple[dict, list[dict], bool]:
    """
    Send raw OCR text to OpenAI, return structured JSON + signals.

    Returns:
        (extraction_json, phase_a_signals, had_llm_retry)

    Note: OCR signals (ocr_low_quality, ocr_fallback_used) are added by
    the caller (invoice_processor) since they depend on OCR-side state.

    Raises ValueError if the LLM response cannot be parsed after retries.
    """
    settings = get_settings()
    client = _get_openai_client()

    max_retries = 5
    had_retry = False
    parsed: dict | None = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": EXTRACTION_PROMPT + raw_text}],
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content)
            log.info(f"LLM extraction succeeded (attempt {attempt + 1})")
            break

        except json.JSONDecodeError as e:
            had_retry = True
            log.error(f"LLM returned invalid JSON (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to parse LLM response as JSON after {max_retries} attempts"
                )

        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                log.warning(f"Rate limit hit, waiting 60s (attempt {attempt + 1})")
                time.sleep(60)
            else:
                raise

    if parsed is None:
        raise ValueError("LLM extraction produced no result")

    # LLM-self-reported confidence is discarded
    if isinstance(parsed.get("document_metadata"), dict):
        parsed["document_metadata"]["confidence_score"] = None

    signals = _derive_signals(parsed, had_retry)
    return parsed, signals, had_retry