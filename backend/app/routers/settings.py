"""
Settings router.
Company profile management, tax rates, password protection, pipeline config.
All logic in services/settings_service.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from decimal import Decimal
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.services import settings_service

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
# Request models
# ---------------------------------------------------------------------------

class SettingsUpdateRequest(BaseModel):
    name:             str | None = None
    country:          str | None = None
    default_tax_rate: Decimal | None = None
    address:          str | None = None
    phone:            str | None = None
    email:            str | None = None
    tax_id:           str | None = None


class PasswordSetRequest(BaseModel):
    password: str   # empty string = clear password protection


# ---------------------------------------------------------------------------
# GET settings
# ---------------------------------------------------------------------------

@router.get("")
def get_settings_endpoint(db: Client = Depends(get_supabase)):
    """
    Returns company profile settings.
    Password hash is never included in the response.
    Also returns whether password protection is active.
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


# ---------------------------------------------------------------------------
# PATCH settings (password protected if set)
# ---------------------------------------------------------------------------

@router.patch("")
def update_settings_endpoint(
    body: SettingsUpdateRequest,
    x_settings_password: str | None = Header(default=None),
    db: Client = Depends(get_supabase),
):
    """
    Update company profile settings.
    If a settings password has been configured, X-Settings-Password header is required.
    """
    # Verify password if protection is active
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


# ---------------------------------------------------------------------------
# Tax rates
# ---------------------------------------------------------------------------

@router.get("/tax-rates")
def get_tax_rates():
    """
    Returns hardcoded country → standard tax rate (%) mapping.
    Frontend uses this to auto-fill default_tax_rate when country is selected.
    """
    rates = settings_service.get_tax_rates()
    return {
        "tax_rates": [
            {"country": country, "rate": rate}
            for country, rate in rates.items()
        ]
    }


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

@router.post("/set-password")
def set_password(
    body: PasswordSetRequest,
    x_settings_password: str | None = Header(default=None),
    db: Client = Depends(get_supabase),
):
    """
    Set or clear the settings password.
    If a password is already set, the current password must be provided
    in X-Settings-Password to change it.
    Pass empty string to clear password protection.
    """
    # Must verify existing password before changing it
    try:
        password_ok = settings_service.verify_settings_password(
            db, settings.MVP_COMPANY_ID, x_settings_password or ""
        )
    except (NotFoundError, DatabaseError) as e:
        raise HTTPException(502, str(e))

    if not password_ok:
        raise HTTPException(
            status_code=403,
            detail="Current password is incorrect.",
        )

    return _handle(
        settings_service.set_settings_password,
        db,
        settings.MVP_COMPANY_ID,
        body.password,
    )


# ---------------------------------------------------------------------------
# Pipeline config (read-only)
# ---------------------------------------------------------------------------

@router.get("/pipeline")
def get_pipeline_config():
    """
    Returns read-only pipeline configuration:
    LLM provider, models, OCR engine, embedding config.
    No secrets included.
    """
    return settings_service.get_pipeline_config()