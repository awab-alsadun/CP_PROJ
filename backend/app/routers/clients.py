"""
Client endpoints. Delegates to services/client_service.py.
"""
from supabase import Client

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client as SupabaseClient

from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, DuplicateError
from app.models.schemas import (
    ClientCreate, ClientRead, ClientUpdate,
    ClientCreateWithAddress, ClientReadWithAddress, AddressCreate,
)
from app.services import client_service
from app.core.config import get_settings
settings = get_settings()


router = APIRouter(prefix="/clients", tags=["clients"])


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except DuplicateError as e:
        raise HTTPException(409,  e.message)
    except DatabaseError as e:
        raise HTTPException(502, e.message)


@router.post("/", response_model=ClientReadWithAddress, status_code=201)
def create_client(
    payload: ClientCreateWithAddress,
    db: SupabaseClient = Depends(get_supabase),
):
    company_id = settings.MVP_COMPANY_ID

    client_create = ClientCreate(
        company_id=company_id,
        name=payload.name,
        tax_id=payload.tax_id,
        email=payload.email,
        phone=payload.phone,
    )

    address_create = None
    if payload.address is not None:
        address_create = AddressCreate(
            company_id=company_id,
            street=payload.address.street,
            city=payload.address.city,
            state=payload.address.state,
            postal_code=payload.address.postal_code,
            country=payload.address.country,
        )

    return _handle(client_service.create_client, db, client_create, address_create)

@router.get("/")
def list_clients(
    company_id: uuid.UUID = Query(...),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    db: SupabaseClient = Depends(get_supabase),
):
    return _handle(client_service.list_clients, db, company_id, limit, offset, search)


@router.get("/{client_id}", response_model=ClientRead)
def get_client(client_id: uuid.UUID, db: SupabaseClient = Depends(get_supabase)):
    return _handle(client_service.get_client, db, client_id)
@router.get("/{client_id}/latest-address")

@router.get("/{client_id}/latest-address")
def get_latest_address(
    client_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    """
    Return the most recently used address for a client.
    Step 1: most recent invoice with a non-null client_address_id.
    Step 2: most recent address row tagged with client_id directly.
    Returns {id, street, city}. 404 if neither step finds anything.
    """
    company_id = settings.MVP_COMPANY_ID
    address_id = None

    # Step 1 — invoice lookup
    try:
        inv = (
            db.table("invoices")
            .select("client_address_id")
            .eq("client_id", str(client_id))
            .eq("company_id", company_id)
            .not_.is_("client_address_id", "null")
            .is_("deleted_at", "null")
            .order("issue_date", desc=True)
            .limit(1)
            .execute()
        )
        if inv.data:
            address_id = inv.data[0]["client_address_id"]
    except Exception as e:
        raise HTTPException(502, f"Failed to query invoices: {e}")

    # Step 2 — direct client_id tag on addresses table
    if not address_id:
        try:
            addr_row = (
                db.table("addresses")
                .select("id")
                .eq("client_id", str(client_id))
                .eq("company_id", company_id)
                .is_("deleted_at", "null")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if addr_row.data:
                address_id = addr_row.data[0]["id"]
        except Exception as e:
            raise HTTPException(502, f"Failed to query addresses: {e}")

    if not address_id:
        raise HTTPException(404, "No address on file")

    # Fetch full address row
    try:
        addr = (
            db.table("addresses")
            .select("id, street, city")
            .eq("id", address_id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(404, "No address on file")

    if not addr.data:
        raise HTTPException(404, "No address on file")

    return {
        "id":     addr.data.get("id"),
        "street": addr.data.get("street"),
        "city":   addr.data.get("city"),
    }
@router.patch("/{client_id}", response_model=ClientRead)
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: SupabaseClient = Depends(get_supabase),
):
    return _handle(client_service.update_client, db, client_id, payload)


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: uuid.UUID, db: SupabaseClient = Depends(get_supabase)):
    _handle(client_service.soft_delete_client, db, client_id)