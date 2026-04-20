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


@router.get("/", response_model=list[VendorRead])
def list_vendors(
    company_id: uuid.UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Client = Depends(get_supabase),
):
    return _handle(vendor_service.list_vendors, db, company_id, limit, offset)


@router.get("/{vendor_id}", response_model=VendorRead)
def get_vendor(vendor_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(vendor_service.get_vendor, db, vendor_id)


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