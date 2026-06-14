"""
Settings router.
Company profile management, branding, tax rates, password protection, pipeline config.
All logic in services/settings_service.py.

Endpoint groups:
  /settings           — company profile (password-protected if configured)
  /settings/branding  — cosmetic branding (NEVER password-protected)
  /settings/tax-rates — read-only country tax lookup
  /settings/pipeline  — read-only AI pipeline config
  /settings/set-password — manage the company profile password
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Header, File, UploadFile
from pydantic import BaseModel
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.services import settings_service
from app.services.storage_service import upload_branding_logo

router = APIRouter(prefix="/settings", tags=["settings"])
settings = get_settings()


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except ValidationError as e:
        raise HTTPException(400, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


# ---------------------------------------------------------------------------
# Hex color validation
# ---------------------------------------------------------------------------

HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _validate_hex(value: str | None, field: str) -> None:
    if value is not None and not HEX_COLOR_RE.match(value):
        raise HTTPException(
            400,
            f"Invalid hex color for {field}: '{value}'. Expected format: #RRGGBB",
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SettingsUpdateRequest(BaseModel):
    """
    Company profile fields. Branding fields are NOT accepted here —
    use PATCH /settings/branding for those.
    """
    name:             str   | None = None
    country:          str   | None = None
    default_tax_rate: float | None = None   # was Decimal — not JSON-serializable, caused 502
    address:          str   | None = None
    phone:            str   | None = None
    email:            str   | None = None
    tax_id:           str   | None = None


class BrandingUpdateRequest(BaseModel):
    """
    Cosmetic branding only. No password required.
    """
    invoice_primary_color:  str | None = None
    invoice_accent_color:   str | None = None
    invoice_text_color:     str | None = None
    invoice_footer_text:    str | None = None


class PasswordSetRequest(BaseModel):
    password: str   # empty string = clear password protection


# ---------------------------------------------------------------------------
# Logo upload constants
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
EXT_MAP = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


# ===========================================================================
# GET /settings — full read (includes branding fields too, for backwards compat)
# ===========================================================================

@router.get("")
def get_settings_endpoint(db: Client = Depends(get_supabase)):
    """
    Returns the full company row: profile fields + branding fields.
    Password hash is never included.
    Also returns whether the profile is password-protected.
    """
    data = _handle(
        settings_service.get_company_settings,
        db,
        settings.MVP_COMPANY_ID,
    )
    data["password_protected"] = settings_service.is_password_protected(
        db, settings.MVP_COMPANY_ID
    )
    return data


# ===========================================================================
# PATCH /settings — company profile only (password-protected if configured)
# ===========================================================================

@router.patch("")
def update_settings_endpoint(
    body: SettingsUpdateRequest,
    x_settings_password: str | None = Header(default=None),
    db: Client = Depends(get_supabase),
):
    """
    Update company profile (name, tax_id, country, address, phone, email,
    default_tax_rate). Branding fields are NOT accepted here — they have
    their own endpoint at PATCH /settings/branding.
    Password-protected if a settings password is configured.
    """
    # Password check
    try:
        password_ok = settings_service.verify_settings_password(
            db, settings.MVP_COMPANY_ID, x_settings_password or ""
        )
    except (NotFoundError, DatabaseError) as e:
        raise HTTPException(502, str(e))

    if not password_ok:
        raise HTTPException(
            status_code=403,
            detail="Invalid settings password. Provide the correct X-Settings-Password header.",
        )

    data = body.model_dump(exclude_none=True)
    return _handle(
        settings_service.update_company_settings,
        db,
        settings.MVP_COMPANY_ID,
        data,
    )


# ===========================================================================
# GET /settings/branding — branding-only read (no password)
# ===========================================================================

@router.get("/branding")
def get_branding(db: Client = Depends(get_supabase)):
    """
    Returns only the branding-related fields. No password required.
    Used by the Branding tab in the settings UI.
    """
    full = _handle(
        settings_service.get_company_settings,
        db,
        settings.MVP_COMPANY_ID,
    )
    return {
        "logo_url":              full.get("logo_url"),
        "invoice_primary_color": full.get("invoice_primary_color"),
        "invoice_accent_color":  full.get("invoice_accent_color"),
        "invoice_text_color":    full.get("invoice_text_color"),
        "invoice_footer_text":   full.get("invoice_footer_text"),
    }


# ===========================================================================
# PATCH /settings/branding — update cosmetic branding (NO password)
# ===========================================================================

@router.patch("/branding")
def update_branding(
    body: BrandingUpdateRequest,
    db: Client = Depends(get_supabase),
):
    """
    Update cosmetic branding fields (colors + footer text).
    NO password required — branding is cosmetic, not security-sensitive.
    Validates hex colors before writing.
    """
    _validate_hex(body.invoice_primary_color, "invoice_primary_color")
    _validate_hex(body.invoice_accent_color,  "invoice_accent_color")
    _validate_hex(body.invoice_text_color,    "invoice_text_color")

    data = body.model_dump(exclude_none=True)
    updated = _handle(
        settings_service.update_company_settings,
        db,
        settings.MVP_COMPANY_ID,
        data,
    )
    # Mirror the GET /branding shape on return
    return {
        "logo_url":              updated.get("logo_url"),
        "invoice_primary_color": updated.get("invoice_primary_color"),
        "invoice_accent_color":  updated.get("invoice_accent_color"),
        "invoice_text_color":    updated.get("invoice_text_color"),
        "invoice_footer_text":   updated.get("invoice_footer_text"),
    }


# ===========================================================================
# POST /settings/branding/logo — upload logo (NO password)
# ===========================================================================

@router.post("/branding/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Client = Depends(get_supabase),
):
    """
    Upload a company logo (png, jpg, jpeg, webp; max 2 MB).
    Stores in public 'branding' bucket at {company_id}/logo.{ext}.
    Writes the permanent public URL to companies.logo_url.
    NO password required — branding is cosmetic.
    """
    # Validate content type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400,
            f"Unsupported file type '{file.content_type}'. "
            "Allowed: image/png, image/jpeg, image/webp",
        )

    # Read and validate size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Logo exceeds 2 MB limit.")

    ext = EXT_MAP[file.content_type]

    # Upload to branding bucket
    try:
        public_url = upload_branding_logo(
            db, settings.MVP_COMPANY_ID, file_bytes, ext
        )
    except ValueError as e:
        raise HTTPException(502, str(e))

    # Write URL onto companies row
    _handle(
        settings_service.update_company_settings,
        db,
        settings.MVP_COMPANY_ID,
        {"logo_url": public_url},
    )

    return {"logo_url": public_url}


# ===========================================================================
# Tax rates
# ===========================================================================

@router.get("/tax-rates")
def get_tax_rates():
    """
    Returns hardcoded country → standard tax rate (%) mapping.
    """
    rates = settings_service.get_tax_rates()
    return {
        "tax_rates": [
            {"country": country, "rate": rate}
            for country, rate in rates.items()
        ]
    }


# ===========================================================================
# Pipeline config (read-only)
# ===========================================================================

@router.get("/pipeline")
def get_pipeline_config():
    """
    Returns read-only pipeline configuration.
    No secrets included.
    """
    return settings_service.get_pipeline_config()