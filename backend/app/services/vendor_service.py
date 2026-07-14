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
    db: Client,
    company_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
) -> dict:
    """Returns paginated response with optional search on name/tax_id.
    Each vendor row includes invoice_count.
    """
    try:
        count_query = (
            db.table("vendors")
            .select("id", count="exact")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
        )
        data_query = (
            db.table("vendors")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
        )

        if search:
            or_filter = f"name.ilike.%{search}%,tax_id.ilike.%{search}%"
            count_query = count_query.or_(or_filter)
            data_query  = data_query.or_(or_filter)

        count_result = count_query.execute()
        total = count_result.count or 0

        result = (
            data_query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        vendors = result.data or []
    except Exception as e:
        raise DatabaseError("Failed to list vendors", detail=str(e))

    # Attach invoice_count per vendor
    if vendors:
        vendor_ids = [v["id"] for v in vendors]
        try:
            all_inv = (
                db.table("invoices")
                .select("vendor_id")
                .in_("vendor_id", vendor_ids)
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
                .execute()
            )
            count_map: dict[str, int] = {}
            for row in (all_inv.data or []):
                vid = row["vendor_id"]
                count_map[vid] = count_map.get(vid, 0) + 1
            for v in vendors:
                v["invoice_count"] = count_map.get(v["id"], 0)
        except Exception:
            for v in vendors:
                v["invoice_count"] = None

    return {
        "data":   vendors,
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }
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
    
    
# ============================================================
# ADD TO: app/services/vendor_service.py
# Paste both functions at the bottom of the file.
# No existing code changes — pure addition.
# ============================================================


def get_or_create_vendor_by_name(
    db: Client,
    company_id: uuid.UUID,
    name: str,
    tax_id: str = "N/A",
    email: str | None = None,
    phone: str | None = None,
) -> dict:
    """
    Match on LOWER(TRIM(name)) first.
    Falls back to tax_id match only when tax_id is real (not N/A).
    Creates a new vendor if no match found.
    """
    name_clean = name.strip().lower()

    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
            .execute()
        )
        for row in (result.data or []):
            if (row.get("name") or "").strip().lower() == name_clean:
                return row
    except Exception as e:
        raise DatabaseError("Failed to lookup vendor by name", detail=str(e))

    if tax_id and tax_id != "N/A":
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
            if result.data:
                return result.data[0]
        except Exception as e:
            raise DatabaseError("Failed to lookup vendor by tax_id", detail=str(e))

    payload = VendorCreate(
        company_id=company_id,
        name=name,
        tax_id=tax_id,
        email=email,
        phone=phone,
    )
    return create_vendor(db, payload)


def get_latest_vendor_address(
    db: Client,
    company_id: str,
    vendor_id: str,
) -> dict | None:
    """
    Return the most recently used address for a vendor.
    Step 1: most recent invoice with a non-null vendor_address_id.
    Step 2: most recent address row tagged with vendor_id directly.
    Returns {id, street, city} or None.
    """
    address_id = None

    try:
        inv = (
            db.table("invoices")
            .select("vendor_address_id")
            .eq("vendor_id", vendor_id)
            .eq("company_id", company_id)
            .not_.is_("vendor_address_id", "null")
            .is_("deleted_at", "null")
            .order("issue_date", desc=True)
            .limit(1)
            .execute()
        )
        if inv.data:
            address_id = inv.data[0]["vendor_address_id"]
    except Exception:
        pass

    if not address_id:
        try:
            addr_row = (
                db.table("addresses")
                .select("id")
                .eq("vendor_id", vendor_id)
                .eq("company_id", company_id)
                .is_("deleted_at", "null")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if addr_row.data:
                address_id = addr_row.data[0]["id"]
        except Exception:
            pass

    if not address_id:
        return None

    try:
        addr = (
            db.table("addresses")
            .select("id, street, city")
            .eq("id", address_id)
            .single()
            .execute()
        )
        if addr.data:
            return {
                "id":     addr.data.get("id"),
                "street": addr.data.get("street"),
                "city":   addr.data.get("city"),
            }
    except Exception:
        pass

    return None