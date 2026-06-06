"""
Client service — DB operations for clients.
"""

import uuid
from datetime import datetime

from supabase import Client as SupabaseClient

from app.core.exceptions import NotFoundError, DatabaseError, DuplicateError
from app.models.schemas import ClientCreate, ClientUpdate


def create_client(
    db: SupabaseClient,
    payload: ClientCreate,
    address_payload: "AddressCreate | None" = None,
) -> dict:
    """
    Insert a new client after deduplication check on (company_id, tax_id).
    If address_payload is provided, inserts the address AFTER the client
    and tags it with client_id so reverse lookup works.
    Raises DuplicateError (HTTP 409) if tax_id already exists for this company.
    """
    from app.models.schemas import AddressCreate

    # ── 1. Duplicate check ────────────────────────────────────────────────
    try:
        dup = (
            db.table("clients")
            .select("id")
            .eq("company_id", str(payload.company_id))
            .eq("tax_id", payload.tax_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to check duplicate client", detail=str(e))

    if dup.data:
        raise DuplicateError("Client with this tax_id already exists.")

    # ── 2. Insert client ──────────────────────────────────────────────────
    try:
        data = payload.model_dump(mode="json")
        result = db.table("clients").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create client", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")

    client = result.data[0]

    # ── 3. Insert address tagged with client_id (only if client succeeded) ─
    address = None
    if address_payload is not None:
        address_payload.client_id = uuid.UUID(client["id"])
        from app.services.address_service import get_or_create_address
        address = get_or_create_address(
            db,
            company_id=address_payload.company_id,
            street=address_payload.street,
            city=address_payload.city,
            postal_code=address_payload.postal_code,
            country=address_payload.country,
            state=address_payload.state,
            client_id=address_payload.client_id,
            vendor_id=address_payload.vendor_id,
        )

    client["address"] = address
    return client

def get_or_create_client(
    db: SupabaseClient, company_id: uuid.UUID, name: str, tax_id: str, **kwargs
) -> dict:
    try:
        result = (
            db.table("clients")
            .select("*")
            .eq("company_id", str(company_id))
            .eq("tax_id", tax_id)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to lookup client", detail=str(e))

    if result.data:
        return result.data[0]

    payload = ClientCreate(
        company_id=company_id, name=name, tax_id=tax_id, **kwargs
    )
    return create_client(db, payload)


def list_clients(
    db: SupabaseClient,
    company_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
) -> dict:
    """Returns paginated response with optional search on name/tax_id."""
    try:
        count_query = (
            db.table("clients")
            .select("id", count="exact")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
        )

        data_query = (
            db.table("clients")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
        )

        if search:
            or_filter = f"name.ilike.%{search}%,tax_id.ilike.%{search}%"
            count_query = count_query.or_(or_filter)
            data_query = data_query.or_(or_filter)

        count_result = count_query.execute()
        total = count_result.count or 0

        result = (
            data_query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to list clients", detail=str(e))

    return {
        "data": result.data or [],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_client(db: SupabaseClient, client_id: uuid.UUID) -> dict:
    try:
        result = (
            db.table("clients")
            .select("*")
            .eq("id", str(client_id))
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        if "No rows" in str(e):
            raise NotFoundError(f"Client {client_id} not found")
        raise DatabaseError("Failed to get client", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Client {client_id} not found")
    return result.data


def update_client(
    db: SupabaseClient, client_id: uuid.UUID, payload: ClientUpdate
) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return get_client(db, client_id)
    try:
        result = (
            db.table("clients")
            .update(data)
            .eq("id", str(client_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to update client", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Client {client_id} not found")
    return result.data[0]


def soft_delete_client(db: SupabaseClient, client_id: uuid.UUID) -> None:
    try:
        result = (
            db.table("clients")
            .update({"deleted_at": datetime.utcnow().isoformat()})
            .eq("id", str(client_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to delete client", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Client {client_id} not found")