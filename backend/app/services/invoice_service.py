"""
Invoice service — all invoice-related DB operations.
"""

import uuid
from datetime import datetime, date

from supabase import Client

from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.models.schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    LineItemCreate,
)


VALID_TRANSITIONS = {
    "draft":   ["sent"],
    "sent":    ["paid", "overdue"],
    "overdue": ["paid"],
    "paid":    [],
}


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


def _attach_vendor_client_names(db: Client, invoices: list[dict]) -> list[dict]:
    """Batch-fetch vendor and client names and attach to invoice rows."""
    if not invoices:
        return invoices

    vendor_ids = list(set(i["vendor_id"] for i in invoices if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in invoices if i.get("client_id")))

    vendor_map = {}
    client_map = {}

    if vendor_ids:
        try:
            vr = db.table("vendors").select("id, name").in_("id", vendor_ids).execute()
            vendor_map = {v["id"]: v["name"] for v in (vr.data or [])}
        except Exception:
            pass

    if client_ids:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids).execute()
            client_map = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    for inv in invoices:
        inv["vendor_name"] = vendor_map.get(inv.get("vendor_id"), None)
        inv["client_name"] = client_map.get(inv.get("client_id"), None)

    return invoices


def list_invoices(
    db: Client,
    company_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    """
    Returns paginated response with vendor/client names attached.
    Search matches invoice_number, vendor name, or client name.
    """
    try:
        # If searching by text, we need to find matching vendor/client IDs first
        search_vendor_ids = None
        search_client_ids = None

        if search:
            try:
                vr = (
                    db.table("vendors")
                    .select("id")
                    .eq("company_id", str(company_id))
                    .ilike("name", f"%{search}%")
                    .execute()
                )
                search_vendor_ids = [v["id"] for v in (vr.data or [])]
            except Exception:
                search_vendor_ids = []

            try:
                cr = (
                    db.table("clients")
                    .select("id")
                    .eq("company_id", str(company_id))
                    .ilike("name", f"%{search}%")
                    .execute()
                )
                search_client_ids = [c["id"] for c in (cr.data or [])]
            except Exception:
                search_client_ids = []

        # Build the base filter
        # supabase-py doesn't support OR across columns natively,
        # so for search we fetch a broader set and filter in Python
        if search and (search_vendor_ids or search_client_ids):
            # Fetch all invoices for this company (with status filter),
            # then filter by invoice_number OR vendor_id OR client_id in Python
            count_query = (
                db.table("invoices")
                .select("id, invoice_number, vendor_id, client_id", count="exact")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                count_query = count_query.eq("status", status)
            all_ids_result = count_query.execute()

            # Filter matching IDs
            matching_ids = []
            search_lower = search.lower()
            for row in (all_ids_result.data or []):
                if search_lower in (row.get("invoice_number") or "").lower():
                    matching_ids.append(row["id"])
                elif row.get("vendor_id") in search_vendor_ids:
                    matching_ids.append(row["id"])
                elif row.get("client_id") in search_client_ids:
                    matching_ids.append(row["id"])

            total = len(matching_ids)

            if not matching_ids:
                return {"data": [], "total": 0, "limit": limit, "offset": offset}

            # Paginate the matching IDs
            page_ids = matching_ids[offset:offset + limit]

            data_result = (
                db.table("invoices")
                .select("*")
                .in_("id", page_ids)
                .order("created_at", desc=True)
                .execute()
            )
            invoices = data_result.data or []

        elif search:
            # Search term provided but no vendor/client matches — only search invoice_number
            count_query = (
                db.table("invoices")
                .select("id", count="exact")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
                .ilike("invoice_number", f"%{search}%")
            )
            if status:
                count_query = count_query.eq("status", status)
            count_result = count_query.execute()
            total = count_result.count or 0

            data_query = (
                db.table("invoices")
                .select("*")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
                .ilike("invoice_number", f"%{search}%")
            )
            if status:
                data_query = data_query.eq("status", status)
            data_result = (
                data_query
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            invoices = data_result.data or []

        else:
            # No search — simple paginated query
            count_query = (
                db.table("invoices")
                .select("id", count="exact")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                count_query = count_query.eq("status", status)
            count_result = count_query.execute()
            total = count_result.count or 0

            data_query = (
                db.table("invoices")
                .select("*")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                data_query = data_query.eq("status", status)
            data_result = (
                data_query
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            invoices = data_result.data or []

    except Exception as e:
        raise DatabaseError("Failed to list invoices", detail=str(e))

    # Attach vendor/client names to every invoice
    invoices = _attach_vendor_client_names(db, invoices)

    return {
        "data": invoices,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_invoice(db: Client, invoice_id: uuid.UUID) -> dict:
    """Fetch invoice with vendor and client data joined."""
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
        if "No rows" in str(e) or "multiple" in str(e):
            raise NotFoundError(f"Invoice {invoice_id} not found")
        raise DatabaseError("Failed to get invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice = result.data

    vendor_id = invoice.get("vendor_id")
    if vendor_id:
        try:
            vr = (
                db.table("vendors")
                .select("id, name, email, phone, tax_id")
                .eq("id", vendor_id)
                .single()
                .execute()
            )
            invoice["vendor"] = vr.data if vr.data else None
        except Exception:
            invoice["vendor"] = None
    else:
        invoice["vendor"] = None

    client_id = invoice.get("client_id")
    if client_id:
        try:
            cr = (
                db.table("clients")
                .select("id, name, email, phone, tax_id")
                .eq("id", client_id)
                .single()
                .execute()
            )
            invoice["client"] = cr.data if cr.data else None
        except Exception:
            invoice["client"] = None
    else:
        invoice["client"] = None

    return invoice


def update_invoice(db: Client, invoice_id: uuid.UUID, payload: InvoiceUpdate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return get_invoice(db, invoice_id)
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
# Invoice Lifecycle — Status Transitions
# ---------------------------------------------------------------------------

def transition_invoice_status(
    db: Client, company_id: str, invoice_id: uuid.UUID, new_status: str,
) -> dict:
    from app.services.notification_service import create_notification

    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    old_status = invoice.get("status", "draft")
    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        if not allowed:
            raise ValidationError(
                f"Invoice is '{old_status}' — this is a terminal state, no transitions allowed"
            )
        raise ValidationError(
            f"Cannot transition from '{old_status}' to '{new_status}'. "
            f"Allowed transitions: {', '.join(allowed)}"
        )

    try:
        result = (
            db.table("invoices")
            .update({"status": new_status, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", str(invoice_id))
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to update invoice status", detail=str(e))
    if not result.data:
        raise DatabaseError("Status update returned no data")

    updated_invoice = result.data[0]

    try:
        db.table("audit_logs").insert({
            "company_id": company_id, "table_name": "invoices",
            "record_id": str(invoice_id), "action": "update",
            "performed_by": None,
            "old_data": {"status": old_status}, "new_data": {"status": new_status},
        }).execute()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Audit log write failed: {e}")

    try:
        inv_number = invoice.get("invoice_number", "Unknown")
        create_notification(
            db, company_id, type="status_change", title="Invoice status changed",
            message=f"Invoice {inv_number} status changed from {old_status} to {new_status}",
            related_invoice_id=str(invoice_id),
        )
    except Exception:
        pass

    return updated_invoice


# ---------------------------------------------------------------------------
# Payment Recording with Auto-Reconciliation
# ---------------------------------------------------------------------------

def record_payment(
    db: Client, company_id: str, invoice_id: uuid.UUID, payment_data: dict,
) -> dict:
    from app.services.notification_service import create_notification

    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    try:
        result = db.table("payments").insert({
            "company_id": company_id, "invoice_id": str(invoice_id),
            "payment_date": payment_data.get("payment_date", date.today().isoformat()),
            "amount": payment_data["amount"],
            "method": payment_data.get("method"),
            "reference": payment_data.get("reference"),
        }).execute()
    except Exception as e:
        raise DatabaseError("Failed to record payment", detail=str(e))
    if not result.data:
        raise DatabaseError("Payment insert returned no data")

    payment = result.data[0]

    try:
        all_payments = (
            db.table("payments").select("amount")
            .eq("invoice_id", str(invoice_id))
            .eq("company_id", company_id)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to sum payments", detail=str(e))

    total_paid = sum(float(p.get("amount") or 0) for p in (all_payments.data or []))
    grand_total = float(invoice.get("grand_total") or 0)
    inv_number = invoice.get("invoice_number", "Unknown")
    current_status = invoice.get("status", "draft")

    if total_paid >= grand_total and grand_total > 0 and current_status != "paid":
        try:
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if "paid" in allowed:
                db.table("invoices").update({
                    "status": "paid", "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", str(invoice_id)).execute()
                db.table("audit_logs").insert({
                    "company_id": company_id, "table_name": "invoices",
                    "record_id": str(invoice_id), "action": "update",
                    "performed_by": None,
                    "old_data": {"status": current_status}, "new_data": {"status": "paid"},
                }).execute()
                create_notification(
                    db, company_id, type="payment", title="Invoice fully paid",
                    message=f"Invoice {inv_number} fully paid (${total_paid:.2f} received)",
                    related_invoice_id=str(invoice_id),
                )
                payment["invoice_status"] = "paid"
            else:
                payment["invoice_status"] = current_status
        except Exception:
            payment["invoice_status"] = current_status
    elif total_paid > 0 and total_paid < grand_total:
        try:
            create_notification(
                db, company_id, type="payment", title="Partial payment recorded",
                message=f"Partial payment of ${float(payment_data['amount']):.2f} recorded for invoice {inv_number} (${total_paid:.2f}/${grand_total:.2f})",
                related_invoice_id=str(invoice_id),
            )
        except Exception:
            pass
        payment["invoice_status"] = current_status
    else:
        payment["invoice_status"] = current_status

    payment["total_paid"] = round(total_paid, 2)
    payment["grand_total"] = round(grand_total, 2)
    return payment


# ---------------------------------------------------------------------------
# Raw Document (with company_id filter)
# ---------------------------------------------------------------------------

def get_raw_document_for_company(
    db: Client, company_id: str, invoice_id: uuid.UUID,
) -> dict:
    try:
        result = (
            db.table("invoice_raw_documents")
            .select("raw_text, extraction_json, schema_version, created_at")
            .eq("invoice_id", str(invoice_id))
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get raw document", detail=str(e))
    if not result.data:
        raise NotFoundError(f"No raw document found for invoice {invoice_id}")
    return result.data[0]


# ---------------------------------------------------------------------------
# Line Items
# ---------------------------------------------------------------------------

def get_line_items(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = db.table("line_items").select("*").eq("invoice_id", str(invoice_id)).execute()
    except Exception as e:
        raise DatabaseError("Failed to get line items", detail=str(e))
    return result.data


def create_line_items(db: Client, items: list[LineItemCreate]) -> list[dict]:
    if not items:
        return []
    try:
        data = [item.model_dump(mode="json") for item in items]
        result = db.table("line_items").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create line items", detail=str(e))
    return result.data or []


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def get_payments(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = db.table("payments").select("*").eq("invoice_id", str(invoice_id)).execute()
    except Exception as e:
        raise DatabaseError("Failed to get payments", detail=str(e))
    return result.data


# ---------------------------------------------------------------------------
# Raw Documents
# ---------------------------------------------------------------------------

def get_raw_document(db: Client, invoice_id: uuid.UUID) -> dict | None:
    try:
        result = (
            db.table("invoice_raw_documents").select("*")
            .eq("invoice_id", str(invoice_id)).limit(1).execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get raw document", detail=str(e))
    return result.data[0] if result.data else None


def create_raw_document(db: Client, data: dict) -> dict:
    try:
        result = db.table("invoice_raw_documents").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create raw document", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]