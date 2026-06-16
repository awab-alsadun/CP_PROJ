"""
Settings router.
Company profile management, branding, tax rates, password protection, pipeline config.
All logic in services/settings_service.py.

Endpoint groups:
  /settings              — company profile
  /settings/branding     — cosmetic branding (NEVER password-protected)
  /settings/tax-rates    — read-only country tax lookup
  /settings/pipeline     — read-only AI pipeline config
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
# Validation
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
    name:             str   | None = None
    country:          str   | None = None
    default_tax_rate: float | None = None
    address:          str   | None = None
    phone:            str   | None = None
    email:            str   | None = None
    tax_id:           str   | None = None


class BrandingUpdateRequest(BaseModel):
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
MAX_LOGO_BYTES = 2 * 1024 * 1024
EXT_MAP = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


# ===========================================================================
# GET /settings
# ===========================================================================

@router.get("")
def get_settings_endpoint(db: Client = Depends(get_supabase)):
    data = _handle(settings_service.get_company_settings, db, settings.MVP_COMPANY_ID)
    data["password_protected"] = settings_service.is_password_protected(db, settings.MVP_COMPANY_ID)
    return data


# ===========================================================================
# PATCH /settings
# ===========================================================================

@router.patch("")
def update_settings_endpoint(
    body: SettingsUpdateRequest,
    db: Client = Depends(get_supabase),
):
    data = body.model_dump(exclude_none=True)
    return _handle(
        settings_service.update_company_settings,
        db, settings.MVP_COMPANY_ID, data,
    )


# ===========================================================================
# POST /settings/set-password
# ===========================================================================

@router.post("/set-password")
def set_password_endpoint(
    body: PasswordSetRequest,
    x_settings_password: str | None = Header(default=None),
    db: Client = Depends(get_supabase),
):
    """
    Set, change, or clear the settings password.
    - If a password is currently set: X-Settings-Password header must match the current one.
    - If no password is set: header is ignored.
    - Empty body.password = clear password (still requires current password if one is set).
    """
    return _handle(
        settings_service.set_settings_password,
        db,
        settings.MVP_COMPANY_ID,
        body.password,
        x_settings_password or "",
    ) or {"ok": True, "password_protected": bool(body.password)}


# ===========================================================================
# GET /settings/branding
# ===========================================================================

@router.get("/branding")
def get_branding(db: Client = Depends(get_supabase)):
    full = _handle(settings_service.get_company_settings, db, settings.MVP_COMPANY_ID)
    return {
        "logo_url":              full.get("logo_url"),
        "invoice_primary_color": full.get("invoice_primary_color"),
        "invoice_accent_color":  full.get("invoice_accent_color"),
        "invoice_text_color":    full.get("invoice_text_color"),
        "invoice_footer_text":   full.get("invoice_footer_text"),
    }


# ===========================================================================
# PATCH /settings/branding
# ===========================================================================

@router.patch("/branding")
def update_branding(
    body: BrandingUpdateRequest,
    db: Client = Depends(get_supabase),
):
    _validate_hex(body.invoice_primary_color, "invoice_primary_color")
    _validate_hex(body.invoice_accent_color,  "invoice_accent_color")
    _validate_hex(body.invoice_text_color,    "invoice_text_color")

    data = body.model_dump(exclude_none=True)
    updated = _handle(
        settings_service.update_company_settings,
        db, settings.MVP_COMPANY_ID, data,
    )
    return {
        "logo_url":              updated.get("logo_url"),
        "invoice_primary_color": updated.get("invoice_primary_color"),
        "invoice_accent_color":  updated.get("invoice_accent_color"),
        "invoice_text_color":    updated.get("invoice_text_color"),
        "invoice_footer_text":   updated.get("invoice_footer_text"),
    }


# ===========================================================================
# POST /settings/branding/logo
# ===========================================================================

@router.post("/branding/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Client = Depends(get_supabase),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400,
            f"Unsupported file type '{file.content_type}'. "
            "Allowed: image/png, image/jpeg, image/webp",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Logo exceeds 2 MB limit.")

    ext = EXT_MAP[file.content_type]

    try:
        public_url = upload_branding_logo(db, settings.MVP_COMPANY_ID, file_bytes, ext)
    except ValueError as e:
        raise HTTPException(502, str(e))

    _handle(
        settings_service.update_company_settings,
        db, settings.MVP_COMPANY_ID, {"logo_url": public_url},
    )

    return {"logo_url": public_url}


# ===========================================================================
# Tax rates
# ===========================================================================

@router.get("/tax-rates")
def get_tax_rates():
    rates = settings_service.get_tax_rates()
    return {
        "tax_rates": [
            {"country": country, "rate": rate}
            for country, rate in rates.items()
        ]
    }


# ===========================================================================
# Pipeline config
# ===========================================================================

@router.get("/pipeline")
def get_pipeline_config():
    return settings_service.get_pipeline_config()