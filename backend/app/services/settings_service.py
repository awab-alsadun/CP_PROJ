"""
Settings Service
----------------
Manages company profile settings, tax rate lookups, and password protection.

Password protection (optional):
  - If settings_password_hash is NULL → settings are freely editable
  - If set → PATCH /settings requires X-Settings-Password header
  - Password stored as SHA-256 hex digest (no salt — MVP simplicity)
  - For production: replace with bcrypt

Tax rates: hardcoded dict of country ISO code → standard VAT/GST/sales tax %.
"""

import hashlib
import logging

from supabase import Client

from app.core.exceptions import DatabaseError, NotFoundError, ValidationError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Country → standard tax rate (%)
# ---------------------------------------------------------------------------

COUNTRY_TAX_RATES: dict[str, float] = {
    "US": 0.0, "UK": 20.0, "DE": 19.0, "FR": 20.0, "TR": 20.0,
    "SA": 15.0, "AE": 5.0, "EG": 14.0, "BH": 10.0, "DK": 25.0,
    "FI": 24.0, "IT": 22.0, "ES": 21.0, "NL": 21.0, "SE": 25.0,
    "NO": 25.0, "JP": 10.0, "KR": 10.0, "CN": 13.0, "IN": 18.0,
    "BR": 17.0, "CA": 13.0, "AU": 10.0, "CY": 19.0, "PL": 23.0,
    "PT": 23.0, "CH": 7.7, "SG": 9.0, "MY": 6.0, "ZA": 15.0,
    "NG": 7.5, "MX": 16.0, "AR": 21.0,
}


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _get_password_hash(db: Client, company_id: str) -> str | None:
    try:
        r = (db.table("companies").select("settings_password_hash")
             .eq("id", company_id).single().execute())
    except Exception as e:
        raise DatabaseError("Failed to fetch password hash", detail=str(e))
    if not r.data:
        raise NotFoundError(f"Company {company_id} not found")
    h = r.data.get("settings_password_hash")
    return h or None  # treat empty string as no password


def is_password_protected(db: Client, company_id: str) -> bool:
    """True if a settings password is currently set."""
    try:
        return _get_password_hash(db, company_id) is not None
    except (NotFoundError, DatabaseError):
        return False


def verify_settings_password(
    db: Client, company_id: str, provided_password: str,
) -> bool:
    """
    Returns True if password matches OR if no password is configured.
    Returns False if a password is set and the provided one is wrong.
    """
    stored_hash = _get_password_hash(db, company_id)
    if stored_hash is None:
        return True  # no password set → access allowed
    if not provided_password:
        return False
    return _hash_password(provided_password) == stored_hash


def set_settings_password(
    db: Client,
    company_id: str,
    new_password: str,
    current_password: str,
) -> None:
    """
    Set/change/clear the settings password.
    - If a password is already set, current_password must match.
    - If no password is set, current_password is ignored.
    - new_password='' clears the password (subject to current_password check).
    Raises ValidationError on bad inputs, NotFoundError if company missing.
    """
    stored_hash = _get_password_hash(db, company_id)

    # Verify current password if one exists
    if stored_hash is not None:
        if not current_password:
            raise ValidationError("Current password required")
        if _hash_password(current_password) != stored_hash:
            raise ValidationError("Current password is incorrect")

    new_hash = _hash_password(new_password) if new_password else None

    try:
        result = (db.table("companies")
                  .update({"settings_password_hash": new_hash})
                  .eq("id", company_id).execute())
    except Exception as e:
        raise DatabaseError("Failed to update password", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Company {company_id} not found")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_company_settings(db: Client, company_id: str) -> dict:
    try:
        result = (
            db.table("companies")
            .select(
                "id, name, domain, country, default_tax_rate, "
                "address, phone, email, tax_id, logo_url, created_at, "
                "invoice_primary_color, invoice_accent_color, "
                "invoice_text_color, invoice_footer_text"
            )
            .eq("id", company_id).single().execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch company settings", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Company {company_id} not found")
    return result.data


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_company_settings(db: Client, company_id: str, data: dict) -> dict:
    if not data:
        return get_company_settings(db, company_id)

    current = get_company_settings(db, company_id)

    data.pop("id", None)
    data.pop("created_at", None)
    data.pop("settings_password_hash", None)

    try:
        result = (db.table("companies").update(data)
                  .eq("id", company_id).execute())
    except Exception as e:
        raise DatabaseError("Failed to update company settings", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Company {company_id} not found")

    try:
        db.table("audit_logs").insert({
            "company_id":   company_id,
            "table_name":   "companies",
            "record_id":    company_id,
            "action":       "update",
            "performed_by": None,
            "old_data":     current,
            "new_data":     data,
        }).execute()
    except Exception as e:
        log.error(f"Audit log failed for settings update: {e}")

    return get_company_settings(db, company_id)


# ---------------------------------------------------------------------------
# Tax rates
# ---------------------------------------------------------------------------

def get_tax_rates() -> dict:
    return COUNTRY_TAX_RATES


def get_tax_rate_for_country(country_code: str) -> float | None:
    return COUNTRY_TAX_RATES.get(country_code.upper())


# ---------------------------------------------------------------------------
# Pipeline config (read-only)
# ---------------------------------------------------------------------------

def get_pipeline_config() -> dict:
    from app.core.config import get_settings
    settings = get_settings()
    return {
        "llm_provider":          settings.LLM_PROVIDER,
        "llm_model":             settings.OPENAI_MODEL if settings.LLM_PROVIDER == "openai" else settings.OLLAMA_MODEL,
        "embedding_model":       settings.OPENAI_EMBEDDING_MODEL if settings.LLM_PROVIDER == "openai" else settings.OLLAMA_EMBEDDING_MODEL,
        "embedding_dimension":   settings.EMBEDDING_DIMENSION,
        "ocr_engine":            "PyMuPDF + Tesseract fallback",
        "tesseract_path":        settings.TESSERACT_PATH or "not configured",
        "rerank_model":          settings.COHERE_RERANK_MODEL,
        "chunk_size_tokens":     settings.DOCUMENT_CHUNK_SIZE_TOKENS,
        "chunk_overlap_tokens":  settings.DOCUMENT_CHUNK_OVERLAP_TOKENS,
    }