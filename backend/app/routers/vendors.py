"""
Vendor endpoints. Delegates to services/vendor_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError
from app.models.schemas import VendorCreate, VendorRead, VendorUpdate
from app.services import vendor_service
from app.core.config import get_settings


settings = get_settings()

router = APIRouter(prefix="/vendors", tags=["vendors"])


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except DatabaseError as e:
        raise HTTPException(502, e.message)


@router.post("/", response_model=VendorRead, status_code=201)
def create_vendor(payload: VendorCreate, db: Client = Depends(get_supabase)):
    return _handle(vendor_service.create_vendor, db, payload)


@router.get("/")
def list_vendors(
    company_id: uuid.UUID = Query(...),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    db: Client = Depends(get_supabase),
):
    return _handle(vendor_service.list_vendors, db, company_id, limit, offset, search)


@router.get("/{vendor_id}", response_model=VendorRead)
def get_vendor(vendor_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(vendor_service.get_vendor, db, vendor_id)


# ============================================================
# ADD TO: app/routers/vendors.py
# 1. Add this import at the top with the existing imports:
#    from app.core.config import get_settings
#    settings = get_settings()
#
# 2. Paste the endpoint below after get_vendor, before update_vendor.
# ============================================================

@router.get("/{vendor_id}/latest-address")
def get_latest_vendor_address(
    vendor_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    """
    Return the most recently used address for a vendor.
    Step 1: most recent invoice with a non-null vendor_address_id.
    Step 2: most recent address row tagged with vendor_id directly.
    Returns {id, street, city}. 404 if neither finds anything.
    """
    from app.services.vendor_service import get_latest_vendor_address
    result = get_latest_vendor_address(
        db, settings.MVP_COMPANY_ID, str(vendor_id)
    )
    if not result:
        raise HTTPException(404, "No address on file")
    return result
 

@router.patch("/{vendor_id}", response_model=VendorRead)
def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    db: Client = Depends(get_supabase),
):
    return _handle(vendor_service.update_vendor, db, vendor_id, payload)


@router.delete("/{vendor_id}", status_code=204)
def delete_vendor(vendor_id: uuid.UUID, db: Client = Depends(get_supabase)):
    _handle(vendor_service.soft_delete_vendor, db, vendor_id)