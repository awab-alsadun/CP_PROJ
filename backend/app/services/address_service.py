"""
Address service — DB operations for addresses.

Addresses are looked up or created during invoice extraction,
not typically CRUD'd directly by users.
"""

import uuid

from supabase import Client

from app.core.exceptions import DatabaseError
from app.models.schemas import AddressCreate


def get_or_create_address(
    db: Client,
    company_id: uuid.UUID,
    street: str | None,
    city: str | None,
    postal_code: str | None,
    country: str | None,
    state: str | None
) -> dict | None:
    """
    Find existing address by exact field match, or create new.
    Returns None if all fields are None (nothing to store).
    """
    if not any([street, city, postal_code, country]):
        return None

    # Try to find existing
    try:
        query = (
            db.table("addresses")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
        )
        if street:
            query = query.eq("street", street)
        if city:
            query = query.eq("city", city)
        if postal_code:
            query = query.eq("postal_code", postal_code)
        if country:
            query = query.eq("country", country)
        if state:
            query = query.eq("state", state)

        result = query.limit(1).execute()
    except Exception as e:
        raise DatabaseError("Failed to lookup address", detail=str(e))

    if result.data:
        return result.data[0]

    # Create new
    payload = AddressCreate(
        company_id=company_id,
        street=street,
        city=city,
        postal_code=postal_code,
        country=country,
        state=state
    )
    try:
        data = payload.model_dump(mode="json")
        result = db.table("addresses").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create address", detail=str(e))
    if not result.data:
        raise DatabaseError("Address insert returned no data")
    return result.data[0]