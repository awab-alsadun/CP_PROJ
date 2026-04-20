"""
Invoice service — all invoice-related DB operations.

Routers call these functions. The OCR/extraction pipeline will also call these
directly (e.g. create_invoice, create_line_items) without going through HTTP.

Every function accepts a Supabase client as its first argument.
This makes the auth migration trivial: swap the client, logic stays identical.
"""

import uuid
from datetime import datetime

from supabase import Client

from app.core.exceptions import NotFoundError, DatabaseError
from app.models.schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    LineItemCreate,
)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

def create_invoice(db: Client, payload: InvoiceCreate) -> dict:
    try:
        data = payload.model_dump(mode="json")
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]


def list_invoices(
    db: Client,
    company_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    try:
        result = (
            db.table("invoices")
            .select("*")
            .eq("company_id", str(company_id))
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to list invoices", detail=str(e))
    return result.data


def get_invoice(db: Client, invoice_id: uuid.UUID) -> dict:
    try:
        result = (
            db.table("invoices")
            .select("*")
            .eq("id", str(invoice_id))
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        # supabase-py raises on .single() with 0 rows
        if "No rows" in str(e) or "multiple" in str(e):
            raise NotFoundError(f"Invoice {invoice_id} not found")
        raise DatabaseError("Failed to get invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")
    return result.data


def update_invoice(db: Client, invoice_id: uuid.UUID, payload: InvoiceUpdate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return get_invoice(db, invoice_id)  # nothing to update, return current
    data["updated_at"] = datetime.utcnow().isoformat()
    try:
        result = (
            db.table("invoices")
            .update(data)
            .eq("id", str(invoice_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to update invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")
    return result.data[0]


def soft_delete_invoice(db: Client, invoice_id: uuid.UUID) -> None:
    try:
        result = (
            db.table("invoices")
            .update({"deleted_at": datetime.utcnow().isoformat()})
            .eq("id", str(invoice_id))
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to delete invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")


# ---------------------------------------------------------------------------
# Line Items (sub-resource of invoice)
# ---------------------------------------------------------------------------

def get_line_items(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = (
            db.table("line_items")
            .select("*")
            .eq("invoice_id", str(invoice_id))
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get line items", detail=str(e))
    return result.data


def create_line_items(db: Client, items: list[LineItemCreate]) -> list[dict]:
    """Bulk insert line items. Used by extraction pipeline."""
    if not items:
        return []
    try:
        data = [item.model_dump(mode="json") for item in items]
        result = db.table("line_items").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create line items", detail=str(e))
    return result.data or []


# ---------------------------------------------------------------------------
# Payments (sub-resource of invoice)
# ---------------------------------------------------------------------------

def get_payments(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = (
            db.table("payments")
            .select("*")
            .eq("invoice_id", str(invoice_id))
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get payments", detail=str(e))
    return result.data


# ---------------------------------------------------------------------------
# Raw Documents (sub-resource of invoice)
# ---------------------------------------------------------------------------

def get_raw_document(db: Client, invoice_id: uuid.UUID) -> dict | None:
    try:
        result = (
            db.table("invoice_raw_documents")
            .select("*")
            .eq("invoice_id", str(invoice_id))
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get raw document", detail=str(e))
    return result.data[0] if result.data else None


def create_raw_document(db: Client, data: dict) -> dict:
    """Used by extraction pipeline to store OCR text + LLM JSON."""
    try:
        result = db.table("invoice_raw_documents").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create raw document", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]