"""
Vendor service — DB operations for vendors.
"""

import uuid
from datetime import datetime

from supabase import Client

from app.core.exceptions import NotFoundError, DatabaseError
from app.models.schemas import VendorCreate, VendorUpdate


def create_vendor(db: Client, payload: VendorCreate) -> dict:
    try:
        data = payload.model_dump(mode="json")
        result = db.table("vendors").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create vendor", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]


def get_or_create_vendor(
    db: Client, company_id: uuid.UUID, name: str, tax_id: str, **kwargs
) -> dict:
    """
    Upsert by (company_id, tax_id). Used by extraction pipeline —
    if the vendor already exists for this tenant, return it.
    Otherwise create it.
    """
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("company_id", str(company_id))
            .eq("tax_id", tax_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to lookup vendor", detail=str(e))

    if result.data:
        return result.data[0]

    payload = VendorCreate(
        company_id=company_id, name=name, tax_id=tax_id, **kwargs
    )
    return create_vendor(db, payload)


def list_vendors(
    db: Client, company_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[dict]:
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to list vendors", detail=str(e))
    return result.data


def get_vendor(db: Client, vendor_id: uuid.UUID) -> dict:
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("id", str(vendor_id))
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        if "No rows" in str(e):
            raise NotFoundError(f"Vendor {vendor_id} not found")
        raise DatabaseError("Failed to get vendor", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Vendor {vendor_id} not found")
    return result.data


def update_vendor(db: Client, vendor_id: uuid.UUID, payload: VendorUpdate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return get_vendor(db, vendor_id)
    try:
        result = (
            db.table("vendors")
            .update(data)
            .eq("id", str(vendor_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to update vendor", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Vendor {vendor_id} not found")
    return result.data[0]


def soft_delete_vendor(db: Client, vendor_id: uuid.UUID) -> None:
    try:
        result = (
            db.table("vendors")
            .update({"deleted_at": datetime.utcnow().isoformat()})
            .eq("id", str(vendor_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to delete vendor", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Vendor {vendor_id} not found")