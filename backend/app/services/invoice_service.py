"""
Invoice service — all invoice-related DB operations.

State machines are type-aware:
  payable:    unpaid → partially_paid | paid | overdue → paid
  receivable: draft → sent → unpaid → partially_paid | paid | overdue → paid

amount_paid_so_far is tracked on the invoice row directly for fast reads.
Payments table remains the source of truth — amount_paid_so_far is derived
by summing payments, then written back to invoices on every payment event.
"""

import uuid
import logging
from datetime import datetime, date

from supabase import Client

from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.models.schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    LineItemCreate,
    get_valid_transitions,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_audit(db: Client, company_id: str, invoice_id: str,
                 old_data: dict, new_data: dict) -> None:
    try:
        db.table("audit_logs").insert({
            "company_id": company_id,
            "table_name": "invoices",
            "record_id":  invoice_id,
            "action":     "update",
            "performed_by": None,
            "old_data":   old_data,
            "new_data":   new_data,
        }).execute()
    except Exception as e:
        log.error(f"Audit log write failed for invoice {invoice_id}: {e}")


def _notify(db: Client, company_id: str, type: str,
            title: str, message: str, invoice_id: str | None = None) -> None:
    try:
        from app.services.notification_service import create_notification
        create_notification(db, company_id, type=type, title=title,
                            message=message, related_invoice_id=invoice_id)
    except Exception as e:
        log.error(f"Notification creation failed: {e}")


def _attach_vendor_client_names(db: Client, invoices: list[dict]) -> list[dict]:
    """Batch-fetch vendor and client names and attach to invoice rows."""
    if not invoices:
        return invoices

    vendor_ids = list(set(i["vendor_id"] for i in invoices if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in invoices if i.get("client_id")))

    vendor_map: dict[str, str] = {}
    client_map: dict[str, str] = {}

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


# ---------------------------------------------------------------------------
# CRUD
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
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    invoice_type: str | None = None,
    search: str | None = None,
) -> dict:
    """
    Paginated invoice list with optional filters:
      - status: single status value
      - invoice_type: 'payable' | 'receivable'
      - search: matches invoice_number, vendor name, or client name

    Returns { data, total, limit, offset } — each row has vendor_name, client_name.
    """
    try:
        search_vendor_ids: list[str] = []
        search_client_ids: list[str] = []

        if search:
            try:
                vr = (
                    db.table("vendors").select("id")
                    .eq("company_id", str(company_id))
                    .ilike("name", f"%{search}%")
                    .execute()
                )
                search_vendor_ids = [v["id"] for v in (vr.data or [])]
            except Exception:
                pass

            try:
                cr = (
                    db.table("clients").select("id")
                    .eq("company_id", str(company_id))
                    .ilike("name", f"%{search}%")
                    .execute()
                )
                search_client_ids = [c["id"] for c in (cr.data or [])]
            except Exception:
                pass

        if search:
            # Fetch all matching IDs first, then paginate in Python
            broad_q = (
                db.table("invoices")
                .select("id, invoice_number, vendor_id, client_id")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                broad_q = broad_q.eq("status", status)
            if invoice_type:
                broad_q = broad_q.eq("invoice_type", invoice_type)

            broad_result = broad_q.execute()
            search_lower = search.lower()
            matching_ids = []
            for row in (broad_result.data or []):
                if search_lower in (row.get("invoice_number") or "").lower():
                    matching_ids.append(row["id"])
                elif row.get("vendor_id") in search_vendor_ids:
                    matching_ids.append(row["id"])
                elif row.get("client_id") in search_client_ids:
                    matching_ids.append(row["id"])

            total = len(matching_ids)
            if not matching_ids:
                return {"data": [], "total": 0, "limit": limit, "offset": offset}

            page_ids = matching_ids[offset: offset + limit]
            data_result = (
                db.table("invoices").select("*")
                .in_("id", page_ids)
                .order("created_at", desc=True)
                .execute()
            )
            invoices = data_result.data or []

        else:
            # No search — straightforward paginated query
            count_q = (
                db.table("invoices")
                .select("id", count="exact")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                count_q = count_q.eq("status", status)
            if invoice_type:
                count_q = count_q.eq("invoice_type", invoice_type)

            count_result = count_q.execute()
            total = count_result.count or 0

            data_q = (
                db.table("invoices").select("*")
                .eq("company_id", str(company_id))
                .is_("deleted_at", "null")
            )
            if status:
                data_q = data_q.eq("status", status)
            if invoice_type:
                data_q = data_q.eq("invoice_type", invoice_type)

            data_result = (
                data_q.order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
            invoices = data_result.data or []

    except Exception as e:
        raise DatabaseError("Failed to list invoices", detail=str(e))

    invoices = _attach_vendor_client_names(db, invoices)
    return {"data": invoices, "total": total, "limit": limit, "offset": offset}


def get_invoice(db: Client, invoice_id: uuid.UUID) -> dict:
    """Fetch invoice with nested vendor and client objects."""
    try:
        result = (
            db.table("invoices").select("*")
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
                .eq("id", vendor_id).single().execute()
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
                .eq("id", client_id).single().execute()
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
            db.table("invoices").update(data)
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
# Invoice Lifecycle — Type-Aware Status Transitions
# ---------------------------------------------------------------------------

def transition_invoice_status(
    db: Client,
    company_id: str,
    invoice_id: uuid.UUID,
    new_status: str,
) -> dict:
    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice_type = invoice.get("invoice_type", "payable")
    old_status   = invoice.get("status", "unpaid")
    allowed      = get_valid_transitions(invoice_type, old_status)

    if new_status not in allowed:
        if not allowed:
            raise ValidationError(
                f"Invoice is '{old_status}' — terminal state, no transitions allowed"
            )
        raise ValidationError(
            f"Cannot transition {invoice_type} from '{old_status}' to '{new_status}'. "
            f"Allowed: {', '.join(allowed)}"
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

    updated = result.data[0]
    inv_number = invoice.get("invoice_number", "Unknown")

    _write_audit(db, company_id, str(invoice_id),
                 {"status": old_status}, {"status": new_status})

    _notify(db, company_id,
            type="status_change",
            title="Invoice status changed",
            message=f"Invoice {inv_number} ({invoice_type}) changed from '{old_status}' to '{new_status}'",
            invoice_id=str(invoice_id))

    # Wire: receivable sent → PDF generation + email (called from router layer)
    # Wire: any → overdue  → email/SMS (called from overdue_service)
    return updated


# ---------------------------------------------------------------------------
# Payment Recording with amount_paid_so_far tracking
# ---------------------------------------------------------------------------

def record_payment(
    db: Client,
    company_id: str,
    invoice_id: uuid.UUID,
    payment_data: dict,
) -> dict:
    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    # Insert payment record
    try:
        pay_result = db.table("payments").insert({
            "company_id":   company_id,
            "invoice_id":   str(invoice_id),
            "payment_date": payment_data.get("payment_date", date.today().isoformat()),
            "amount":       payment_data["amount"],
            "method":       payment_data.get("method"),
            "reference":    payment_data.get("reference"),
        }).execute()
    except Exception as e:
        raise DatabaseError("Failed to record payment", detail=str(e))
    if not pay_result.data:
        raise DatabaseError("Payment insert returned no data")

    payment = pay_result.data[0]

    # Sum all payments for this invoice
    try:
        all_payments = (
            db.table("payments").select("amount")
            .eq("invoice_id", str(invoice_id))
            .eq("company_id", company_id)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to sum payments", detail=str(e))

    total_paid  = sum(float(p.get("amount") or 0) for p in (all_payments.data or []))
    grand_total = float(invoice.get("grand_total") or 0)
    inv_number  = invoice.get("invoice_number", "Unknown")
    invoice_type = invoice.get("invoice_type", "payable")
    old_status  = invoice.get("status", "unpaid")

    # Determine new status
    if grand_total > 0 and total_paid >= grand_total:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partially_paid"
    else:
        new_status = old_status

    # Update invoice: amount_paid_so_far + status if changed
    update_payload: dict = {"amount_paid_so_far": round(total_paid, 2),
                            "updated_at": datetime.utcnow().isoformat()}
    if new_status != old_status:
        allowed = get_valid_transitions(invoice_type, old_status)
        if new_status in allowed:
            update_payload["status"] = new_status

    try:
        db.table("invoices").update(update_payload).eq("id", str(invoice_id)).execute()
    except Exception as e:
        log.error(f"Failed to update invoice after payment: {e}")

    # Audit + notification
    if new_status != old_status:
        _write_audit(db, company_id, str(invoice_id),
                     {"status": old_status, "amount_paid_so_far": invoice.get("amount_paid_so_far")},
                     {"status": new_status, "amount_paid_so_far": round(total_paid, 2)})

    if new_status == "paid":
        _notify(db, company_id, type="payment", title="Invoice fully paid",
                message=f"Invoice {inv_number} fully paid (${total_paid:.2f})",
                invoice_id=str(invoice_id))
    elif new_status == "partially_paid":
        _notify(db, company_id, type="payment", title="Partial payment recorded",
                message=f"Partial payment ${float(payment_data['amount']):.2f} on {inv_number} (${total_paid:.2f}/${grand_total:.2f})",
                invoice_id=str(invoice_id))

    payment["invoice_status"]    = new_status
    payment["total_paid"]        = round(total_paid, 2)
    payment["grand_total"]       = round(grand_total, 2)
    payment["amount_paid_so_far"] = round(total_paid, 2)
    return payment


# ---------------------------------------------------------------------------
# Raw Document
# ---------------------------------------------------------------------------

def get_raw_document_for_company(
    db: Client, company_id: str, invoice_id: uuid.UUID,
) -> dict:
    try:
        result = (
            db.table("invoice_raw_documents")
            .select("raw_text, extraction_json, schema_version, created_at, storage_path")
            .eq("invoice_id", str(invoice_id))
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get raw document", detail=str(e))
    if not result.data:
        raise NotFoundError(f"No raw document for invoice {invoice_id}")
    return result.data[0]


# ---------------------------------------------------------------------------
# Line Items
# ---------------------------------------------------------------------------

def get_line_items(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = (
            db.table("line_items").select("*")
            .eq("invoice_id", str(invoice_id)).execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get line items", detail=str(e))
    return result.data or []


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
# Payments (read)
# ---------------------------------------------------------------------------

def get_payments(db: Client, invoice_id: uuid.UUID) -> list[dict]:
    try:
        result = (
            db.table("payments").select("*")
            .eq("invoice_id", str(invoice_id)).execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to get payments", detail=str(e))
    return result.data or []


# ---------------------------------------------------------------------------
# Raw Documents (read / create)
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