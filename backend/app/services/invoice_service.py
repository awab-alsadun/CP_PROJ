"""
Invoice service — all invoice-related DB operations.

Routers call these functions. The OCR/extraction pipeline will also call these
directly (e.g. create_invoice, create_line_items) without going through HTTP.

Every function accepts a Supabase client as its first argument.
This makes the auth migration trivial: swap the client, logic stays identical.
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


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

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
        if "No rows" in str(e) or "multiple" in str(e):
            raise NotFoundError(f"Invoice {invoice_id} not found")
        raise DatabaseError("Failed to get invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")
    return result.data


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
    db: Client,
    company_id: str,
    invoice_id: uuid.UUID,
    new_status: str,
) -> dict:
    """
    Transition invoice status with state machine enforcement.
    Writes audit log. Returns updated invoice.
    """
    from app.services.notification_service import create_notification

    # Fetch current invoice
    invoice = get_invoice(db, invoice_id)

    # Verify tenant ownership
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    old_status = invoice.get("status", "draft")

    # Validate transition
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

    # Update status
    try:
        result = (
            db.table("invoices")
            .update({
                "status": new_status,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", str(invoice_id))
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to update invoice status", detail=str(e))
    if not result.data:
        raise DatabaseError("Status update returned no data")

    updated_invoice = result.data[0]

    # Write audit log
    try:
        db.table("audit_logs").insert({
            "company_id": company_id,
            "table_name": "invoices",
            "record_id": str(invoice_id),
            "action": "update",
            "performed_by": None,
            "old_data": {"status": old_status},
            "new_data": {"status": new_status},
        }).execute()
    except Exception as e:
        # Audit log failure should not break the transition
        import logging
        logging.getLogger(__name__).error(f"Audit log write failed: {e}")

    # Create notification
    try:
        inv_number = invoice.get("invoice_number", "Unknown")
        create_notification(
            db, company_id,
            type="status_change",
            title="Invoice status changed",
            message=f"Invoice {inv_number} status changed from {old_status} to {new_status}",
            related_invoice_id=str(invoice_id),
        )
    except Exception:
        pass  # Notification failure should not break the transition

    return updated_invoice


# ---------------------------------------------------------------------------
# Payment Recording with Auto-Reconciliation
# ---------------------------------------------------------------------------

def record_payment(
    db: Client,
    company_id: str,
    invoice_id: uuid.UUID,
    payment_data: dict,
) -> dict:
    """
    Record a payment against an invoice.
    Auto-transitions to 'paid' if total payments >= grand_total.
    """
    from app.services.notification_service import create_notification

    # Verify invoice exists and belongs to company
    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    # Insert payment
    try:
        result = db.table("payments").insert({
            "company_id": company_id,
            "invoice_id": str(invoice_id),
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

    # Compute total paid
    try:
        all_payments = (
            db.table("payments")
            .select("amount")
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

    # Auto-transition to paid if fully paid
    if total_paid >= grand_total and grand_total > 0 and current_status != "paid":
        try:
            # Only transition if it's a valid transition
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if "paid" in allowed:
                db.table("invoices").update({
                    "status": "paid",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", str(invoice_id)).execute()

                # Audit log
                db.table("audit_logs").insert({
                    "company_id": company_id,
                    "table_name": "invoices",
                    "record_id": str(invoice_id),
                    "action": "update",
                    "performed_by": None,
                    "old_data": {"status": current_status},
                    "new_data": {"status": "paid"},
                }).execute()

                create_notification(
                    db, company_id,
                    type="payment",
                    title="Invoice fully paid",
                    message=f"Invoice {inv_number} fully paid (${total_paid:.2f} received)",
                    related_invoice_id=str(invoice_id),
                )

                payment["invoice_status"] = "paid"
            else:
                payment["invoice_status"] = current_status
        except Exception:
            payment["invoice_status"] = current_status
    elif total_paid > 0 and total_paid < grand_total:
        # Partial payment notification
        try:
            create_notification(
                db, company_id,
                type="payment",
                title="Partial payment recorded",
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
    db: Client, company_id: str, invoice_id: uuid.UUID
) -> dict:
    """Get raw document with company_id check."""
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