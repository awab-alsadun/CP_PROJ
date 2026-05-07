"""
Extraction Service
------------------
Sends OCR text to OpenAI and receives structured invoice JSON.

Extracted from rag_pipeline/ingest_invoices.py and adapted for FastAPI:
- Uses Settings for OpenAI config (key, model)
- Same extraction prompt and retry logic
- Returns validated dict matching schema_version 1.0
"""

import json
import time
import logging

from openai import OpenAI

from app.core.config import get_settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Extraction Prompt (from ingest_invoices.py — kept identical)
# ---------------------------------------------------------------------------

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


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def extract_structured_data(raw_text: str) -> dict:
    """
    Send raw OCR text to OpenAI and get structured invoice JSON.

    Args:
        raw_text: The OCR-extracted text from an invoice.

    Returns:
        Dict matching the extraction schema (schema_version 1.0).

    Raises:
        ValueError: If the LLM response cannot be parsed as JSON.
        Exception: On unrecoverable API errors.
    """
    settings = get_settings()
    client = _get_openai_client()

    max_retries = 5

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": EXTRACTION_PROMPT + raw_text}
                ],
            )

            content = response.choices[0].message.content.strip()

            # Strip markdown fences if model ignores instructions
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content)
            log.info(f"LLM extraction succeeded (attempt {attempt + 1})")
            return parsed

        except json.JSONDecodeError as e:
            log.error(f"LLM returned invalid JSON (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise ValueError(f"Failed to parse LLM response as JSON after {max_retries} attempts")

        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                wait = 60
                log.warning(f"Rate limit hit, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise