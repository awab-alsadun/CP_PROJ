"""
Client endpoints. Delegates to services/client_service.py.
"""
from supabase import Client

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client as SupabaseClient

from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError
from app.models.schemas import ClientCreate, ClientRead, ClientUpdate
from app.services import client_service
from app.core.config import get_settings
settings = get_settings()


router = APIRouter(prefix="/clients", tags=["clients"])


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except DatabaseError as e:
        raise HTTPException(502, e.message)


@router.post("/", response_model=ClientRead, status_code=201)
def create_client(payload: ClientCreate, db: SupabaseClient = Depends(get_supabase)):
    return _handle(client_service.create_client, db, payload)


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
def get_latest_address(
    client_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    """
    Return the most recently used address for a client, scoped to company.
    Looks up the most recent invoice (by issue_date) for this client that
    has a non-null client_address_id, then returns that address.
    """
    company_id = settings.MVP_COMPANY_ID

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
    except Exception as e:
        raise HTTPException(502, f"Failed to query invoices: {e}")

    if not inv.data:
        raise HTTPException(404, "No address on file")

    address_id = inv.data[0]["client_address_id"]

    try:
        addr = (
            db.table("addresses")
            .select("street, city")
            .eq("id", address_id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(404, "No address on file")

    if not addr.data:
        raise HTTPException(404, "No address on file")

    return {"street": addr.data.get("street"), "city": addr.data.get("city")}

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