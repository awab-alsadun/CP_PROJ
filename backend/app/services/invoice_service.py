"""
invoice_service.py — record_payment with overpayment guard.
get_raw_document_for_company removed (endpoint deleted).
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


def _write_audit(db, company_id, invoice_id, old_data, new_data):
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


def _notify(db, company_id, type, title, message, invoice_id=None):
    try:
        from app.services.notification_service import create_notification
        create_notification(db, company_id, type=type, title=title,
                            message=message, related_invoice_id=invoice_id)
    except Exception as e:
        log.error(f"Notification creation failed: {e}")


def _attach_vendor_client_names(db, invoices):
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


def _insert_compliance_flag(db, company_id, invoice_id, flag_type, severity, reason):
    try:
        db.table("compliance_flags").insert({
            "company_id": company_id,
            "invoice_id": invoice_id,
            "flag_type":  flag_type,
            "severity":   severity,
            "reason":     reason,
        }).execute()
    except Exception as e:
        log.error(f"compliance_flag_insert_failed  invoice_id={invoice_id}  error={e}")


def _generate_invoice_number(db, company_id):
    year = datetime.utcnow().year
    try:
        result = (
            db.table("invoices").select("id", count="exact")
            .eq("company_id", company_id)
            .eq("invoice_type", "receivable")
            .execute()
        )
        n = (result.count or 0) + 1
    except Exception as e:
        log.error(f"invoice_number_count_failed: {e}")
        n = int(datetime.utcnow().strftime("%H%M%S"))
    return f"REC-{year}-{n:04d}"


def create_invoice(db, payload):
    try:
        data = payload.model_dump(mode="json")
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]


def list_invoices(db, company_id, limit=20, offset=0, status=None, invoice_type=None, search=None):
    try:
        search_vendor_ids: list[str] = []
        search_client_ids: list[str] = []

        if search:
            try:
                vr = (db.table("vendors").select("id")
                      .eq("company_id", str(company_id))
                      .ilike("name", f"%{search}%").execute())
                search_vendor_ids = [v["id"] for v in (vr.data or [])]
            except Exception:
                pass
            try:
                cr = (db.table("clients").select("id")
                      .eq("company_id", str(company_id))
                      .ilike("name", f"%{search}%").execute())
                search_client_ids = [c["id"] for c in (cr.data or [])]
            except Exception:
                pass

        if search:
            broad_q = (db.table("invoices")
                       .select("id, invoice_number, vendor_id, client_id")
                       .eq("company_id", str(company_id))
                       .is_("deleted_at", "null"))
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
            data_result = (db.table("invoices").select("*")
                           .in_("id", page_ids)
                           .order("created_at", desc=True).execute())
            invoices = data_result.data or []
        else:
            count_q = (db.table("invoices").select("id", count="exact")
                       .eq("company_id", str(company_id))
                       .is_("deleted_at", "null"))
            if status:
                count_q = count_q.eq("status", status)
            if invoice_type:
                count_q = count_q.eq("invoice_type", invoice_type)
            total = count_q.execute().count or 0

            data_q = (db.table("invoices").select("*")
                      .eq("company_id", str(company_id))
                      .is_("deleted_at", "null"))
            if status:
                data_q = data_q.eq("status", status)
            if invoice_type:
                data_q = data_q.eq("invoice_type", invoice_type)
            invoices = (data_q.order("created_at", desc=True)
                        .range(offset, offset + limit - 1).execute().data or [])
    except Exception as e:
        raise DatabaseError("Failed to list invoices", detail=str(e))

    invoices = _attach_vendor_client_names(db, invoices)
    return {"data": invoices, "total": total, "limit": limit, "offset": offset}


def get_invoice(db, invoice_id):
    try:
        result = (db.table("invoices").select("*")
                  .eq("id", str(invoice_id))
                  .is_("deleted_at", "null")
                  .single().execute())
    except Exception as e:
        if "No rows" in str(e) or "multiple" in str(e):
            raise NotFoundError(f"Invoice {invoice_id} not found")
        raise DatabaseError("Failed to get invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice = result.data

    if invoice.get("vendor_id"):
        try:
            vr = (db.table("vendors").select("id, name, email, phone, tax_id")
                  .eq("id", invoice["vendor_id"]).single().execute())
            invoice["vendor"] = vr.data if vr.data else None
        except Exception:
            invoice["vendor"] = None
    else:
        invoice["vendor"] = None

    if invoice.get("client_id"):
        try:
            cr = (db.table("clients").select("id, name, email, phone, tax_id")
                  .eq("id", invoice["client_id"]).single().execute())
            invoice["client"] = cr.data if cr.data else None
        except Exception:
            invoice["client"] = None
    else:
        invoice["client"] = None

    return invoice


def update_invoice(db, invoice_id, payload):
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return get_invoice(db, invoice_id)
    data["updated_at"] = datetime.utcnow().isoformat()
    try:
        result = (db.table("invoices").update(data)
                  .eq("id", str(invoice_id))
                  .is_("deleted_at", "null").execute())
    except Exception as e:
        raise DatabaseError("Failed to update invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")
    return result.data[0]


def soft_delete_invoice(db, invoice_id):
    try:
        result = (db.table("invoices")
                  .update({"deleted_at": datetime.utcnow().isoformat()})
                  .eq("id", str(invoice_id))
                  .is_("deleted_at", "null").execute())
    except Exception as e:
        raise DatabaseError("Failed to delete invoice", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")


def _fetch_client_for_pdf(db, client_id, client_address_id):
    if not client_id:
        return {"address": {}}
    try:
        cr = (db.table("clients").select("name, tax_id, email, phone")
              .eq("id", str(client_id)).single().execute())
        client = cr.data or {}
    except Exception as e:
        log.error(f"client fetch failed for {client_id}: {e}")
        client = {}
    address: dict = {}
    if client_address_id:
        try:
            ar = (db.table("addresses")
                  .select("street, city, state, postal_code, country")
                  .eq("id", str(client_address_id)).single().execute())
            address = ar.data or {}
        except Exception as e:
            log.error(f"address fetch failed for {client_address_id}: {e}")
    return {**client, "address": address}


def _build_raw_text(invoice, client, line_items):
    lines: list[str] = []
    lines.append(f"Invoice: {invoice.get('invoice_number')}")
    lines.append("Type: receivable")
    lines.append("")
    lines.append("From: K4Y")
    lines.append(f"To: {client.get('name', 'Unknown')}")
    lines.append(f"Issue date: {invoice.get('issue_date')}")
    if invoice.get("due_date"):
        lines.append(f"Due date: {invoice['due_date']}")
    lines.append(f"Currency: {invoice.get('currency')}")
    lines.append("Line items:")
    for i, li in enumerate(line_items, 1):
        lines.append(
            f"  {i}. {li.get('description')} | "
            f"qty={li.get('quantity')} | "
            f"unit_price={li.get('unit_price')} | "
            f"subtotal={li.get('line_subtotal')}"
        )
    lines.append(f"Subtotal: {invoice.get('subtotal')}")
    lines.append(f"Tax ({invoice.get('tax_percent')}%): {invoice.get('total_tax')}")
    lines.append(f"Grand total: {invoice.get('grand_total')}")
    return "\n".join(lines)


def _build_extraction_json(invoice, client, line_items):
    return {
        "schema_version": "1.0",
        "document_metadata": {
            "document_type":        "invoice",
            "extraction_timestamp": datetime.utcnow().isoformat(),
            "confidence_score":     1.0,
            "source":               "form_input",
        },
        "invoice": {
            "invoice_number": invoice.get("invoice_number"),
            "issue_date":     invoice.get("issue_date"),
            "due_date":       invoice.get("due_date"),
            "currency":       invoice.get("currency"),
            "tax_percent":    invoice.get("tax_percent"),
            "subtotal":       invoice.get("subtotal"),
            "total_tax":      invoice.get("total_tax"),
            "grand_total":    invoice.get("grand_total"),
            "discount":       invoice.get("discount"),
            "payment_method": invoice.get("payment_method"),
            "description":    invoice.get("description"),
            "status":         invoice.get("status"),
        },
        "vendor": None,
        "client": {
            "name":    client.get("name"),
            "tax_id":  client.get("tax_id"),
            "email":   client.get("email"),
            "phone":   client.get("phone"),
            "address": client.get("address") or {},
        },
        "line_items": [
            {
                "description":   li.get("description"),
                "quantity":      li.get("quantity"),
                "unit_price":    li.get("unit_price"),
                "line_subtotal": li.get("line_subtotal"),
                "discount":      li.get("discount", 0),
            } for li in line_items
        ],
        "payments": [],
    }


def create_receivable_invoice(db, payload):
    data = payload.model_dump(mode="json")
    line_items_input = data.pop("line_items", []) or []
    company_id = data.get("company_id")

    data["invoice_number"] = _generate_invoice_number(db, company_id)

    try:
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create receivable invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Invoice insert returned no data")

    invoice    = result.data[0]
    invoice_id = invoice["id"]
    inv_num    = invoice.get("invoice_number", "Unknown")

    log.info(f"receivable_create  invoice_id={invoice_id}  invoice_number={inv_num!r}")

    line_items_rows: list[dict] = []
    if line_items_input:
        rows = [{
            "company_id":    company_id,
            "invoice_id":    invoice_id,
            "description":   li.get("description", ""),
            "quantity":      li.get("quantity", 1),
            "unit_price":    li.get("unit_price", 0),
            "line_subtotal": li.get("line_subtotal", 0),
            "discount":      li.get("discount", 0),
        } for li in line_items_input]
        try:
            li_result = db.table("line_items").insert(rows).execute()
            line_items_rows = li_result.data or rows
        except Exception as e:
            log.error(f"receivable_create  stage=line_items_insert_failed  error={e}")
            line_items_rows = rows

    client_data     = _fetch_client_for_pdf(db, invoice.get("client_id"), invoice.get("client_address_id"))
    raw_text        = _build_raw_text(invoice, client_data, line_items_rows)
    extraction_json = _build_extraction_json(invoice, client_data, line_items_rows)

    pdf_bytes: bytes | None = None
    try:
        from app.services.receivable_pdf_renderer import render_receivable_pdf
        try:
            company_row = (db.table("companies")
                           .select("name, address, email, phone, tax_id, "
                                   "logo_url, invoice_primary_color, invoice_accent_color, "
                                   "invoice_text_color, invoice_footer_text")
                           .eq("id", str(company_id)).single().execute())
            company_data = company_row.data or {}
        except Exception as e:
            log.warning(f"company_fetch_failed: {e}")
            company_data = {}
        pdf_bytes = render_receivable_pdf(invoice, client_data, line_items_rows, company_data)
    except Exception as e:
        log.error(f"receivable_create  stage=pdf_render_failed  error={e}")
        _insert_compliance_flag(db, company_id, invoice_id, "pdf_render_failed", "medium", f"PDF rendering failed: {e}")

    raw_doc_id: str | None = None
    try:
        raw_doc_result = db.table("invoice_raw_documents").insert({
            "company_id":      company_id,
            "invoice_id":      invoice_id,
            "raw_text":        raw_text,
            "extraction_json": extraction_json,
            "schema_version":  "1.0",
            "storage_path":    None,
        }).execute()
        raw_doc_id = raw_doc_result.data[0]["id"] if raw_doc_result.data else None
    except Exception as e:
        log.error(f"receivable_create  stage=raw_doc_insert_failed  error={e}")

    if pdf_bytes:
        try:
            from app.services.storage_service import upload_invoice_pdf
            from app.services.invoice_processor import _build_storage_path
            target_path  = _build_storage_path(db, company_id, inv_num)
            storage_path = upload_invoice_pdf(db, company_id, invoice_id, pdf_bytes, storage_path=target_path)
            if raw_doc_id:
                db.table("invoice_raw_documents").update({"storage_path": storage_path}).eq("id", raw_doc_id).execute()
        except Exception as e:
            log.error(f"receivable_create  stage=storage_upload_failed  error={e}")
            _insert_compliance_flag(db, company_id, invoice_id, "storage_upload_failed", "medium", f"PDF upload failed: {e}")

    try:
        from app.services.embedding_service import generate_and_store_embeddings
        generate_and_store_embeddings(db, company_id, invoice_id, raw_text, extraction_json)
    except Exception as e:
        log.error(f"receivable_create  stage=embedding_failed  error={e}")
        _insert_compliance_flag(db, company_id, invoice_id, "embedding_failed", "low", f"Embedding failed: {e}")

    try:
        from app.services.compliance_service import validate_invoice_compliance
        validate_invoice_compliance(db, company_id, invoice_id)
    except Exception as e:
        log.error(f"receivable_create  stage=compliance_failed  error={e}")

    return invoice


def transition_invoice_status(db, company_id, invoice_id, new_status):
    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice_type = invoice.get("invoice_type", "payable")
    old_status   = invoice.get("status", "unpaid")
    allowed      = get_valid_transitions(invoice_type, old_status)

    if new_status not in allowed:
        if not allowed:
            raise ValidationError(f"Invoice is '{old_status}' — terminal state, no transitions allowed")
        raise ValidationError(
            f"Cannot transition {invoice_type} from '{old_status}' to '{new_status}'. "
            f"Allowed: {', '.join(allowed)}"
        )

    update_payload: dict = {"status": new_status, "updated_at": datetime.utcnow().isoformat()}

    if new_status == "paid":
        grand_total  = float(invoice.get("grand_total") or 0)
        current_paid = float(invoice.get("amount_paid_so_far") or 0)
        if current_paid < grand_total:
            update_payload["amount_paid_so_far"] = grand_total

    try:
        result = (db.table("invoices").update(update_payload)
                  .eq("id", str(invoice_id)).execute())
    except Exception as e:
        raise DatabaseError("Failed to update invoice status", detail=str(e))
    if not result.data:
        raise DatabaseError("Status update returned no data")

    updated    = result.data[0]
    inv_number = invoice.get("invoice_number", "Unknown")

    _write_audit(db, company_id, str(invoice_id), {"status": old_status}, {"status": new_status})
    _notify(db, company_id, type="status_change", title="Invoice status changed",
            message=f"Invoice {inv_number} ({invoice_type}) changed from '{old_status}' to '{new_status}'",
            invoice_id=str(invoice_id))

    return updated


def record_payment(db, company_id, invoice_id, payment_data):
    """
    Record a direct payment on a specific invoice.
    Overpayment guard: if amount > remaining balance, returns 400.
    No FIFO — payment applies to this invoice only.
    """
    invoice = get_invoice(db, invoice_id)
    if invoice.get("company_id") != company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    grand_total  = float(invoice.get("grand_total") or 0)
    already_paid = float(invoice.get("amount_paid_so_far") or 0)
    remaining    = round(grand_total - already_paid, 2)
    amount       = float(payment_data["amount"])

    if amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")

    if amount > remaining + 0.01:  # 1-cent tolerance for floating point
        raise ValidationError(
            f"Payment amount ({amount:.2f}) exceeds remaining balance ({remaining:.2f}). "
            f"Enter {remaining:.2f} or less to pay in full."
        )

    # Clamp to remaining to handle floating point dust
    amount = min(amount, remaining)

    try:
        pay_result = db.table("payments").insert({
            "company_id":   company_id,
            "invoice_id":   str(invoice_id),
            "payment_date": payment_data.get("payment_date", date.today().isoformat()),
            "amount":       amount,
            "method":       payment_data.get("method"),
            "reference":    payment_data.get("reference"),
        }).execute()
    except Exception as e:
        raise DatabaseError("Failed to record payment", detail=str(e))
    if not pay_result.data:
        raise DatabaseError("Payment insert returned no data")

    payment = pay_result.data[0]

    # Re-sum all payments for accuracy
    try:
        all_payments = (db.table("payments").select("amount")
                        .eq("invoice_id", str(invoice_id))
                        .eq("company_id", company_id).execute())
    except Exception as e:
        raise DatabaseError("Failed to sum payments", detail=str(e))

    total_paid   = sum(float(p.get("amount") or 0) for p in (all_payments.data or []))
    inv_number   = invoice.get("invoice_number", "Unknown")
    invoice_type = invoice.get("invoice_type", "payable")
    old_status   = invoice.get("status", "unpaid")

    if grand_total > 0 and total_paid >= grand_total - 0.01:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partially_paid"
    else:
        new_status = old_status

    update_payload: dict = {
        "amount_paid_so_far": round(total_paid, 2),
        "updated_at":         datetime.utcnow().isoformat(),
    }
    if new_status != old_status:
        allowed = get_valid_transitions(invoice_type, old_status)
        if new_status in allowed:
            update_payload["status"] = new_status

    try:
        db.table("invoices").update(update_payload).eq("id", str(invoice_id)).execute()
    except Exception as e:
        log.error(f"Failed to update invoice after payment: {e}")

    if new_status != old_status:
        _write_audit(db, company_id, str(invoice_id),
                     {"status": old_status, "amount_paid_so_far": already_paid},
                     {"status": new_status, "amount_paid_so_far": round(total_paid, 2)})

    if new_status == "paid":
        _notify(db, company_id, type="payment", title="Invoice fully paid",
                message=f"Invoice {inv_number} fully paid (${total_paid:.2f})",
                invoice_id=str(invoice_id))
    elif new_status == "partially_paid":
        _notify(db, company_id, type="payment", title="Partial payment recorded",
                message=f"Partial payment ${amount:.2f} on {inv_number} (${total_paid:.2f}/${grand_total:.2f})",
                invoice_id=str(invoice_id))

    payment["invoice_status"]     = new_status
    payment["total_paid"]         = round(total_paid, 2)
    payment["grand_total"]        = round(grand_total, 2)
    payment["amount_paid_so_far"] = round(total_paid, 2)
    payment["remaining"]          = round(grand_total - total_paid, 2)
    return payment


def get_line_items(db, invoice_id):
    try:
        result = (db.table("line_items").select("*")
                  .eq("invoice_id", str(invoice_id)).execute())
    except Exception as e:
        raise DatabaseError("Failed to get line items", detail=str(e))
    return result.data or []


def create_line_items(db, items):
    if not items:
        return []
    try:
        data = [item.model_dump(mode="json") for item in items]
        result = db.table("line_items").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create line items", detail=str(e))
    return result.data or []


def get_payments(db, invoice_id):
    try:
        result = (db.table("payments").select("*")
                  .eq("invoice_id", str(invoice_id)).execute())
    except Exception as e:
        raise DatabaseError("Failed to get payments", detail=str(e))
    return result.data or []


def get_raw_document(db, invoice_id):
    try:
        result = (db.table("invoice_raw_documents").select("*")
                  .eq("invoice_id", str(invoice_id)).limit(1).execute())
    except Exception as e:
        raise DatabaseError("Failed to get raw document", detail=str(e))
    return result.data[0] if result.data else None


def create_raw_document(db, data):
    try:
        result = db.table("invoice_raw_documents").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create raw document", detail=str(e))
    if not result.data:
        raise DatabaseError("Insert returned no data")
    return result.data[0]

    # ============================================================
# ADD TO: app/services/invoice_service.py
# Place all three helpers + create_payable_invoice directly
# after the create_receivable_invoice() function.
# No existing code changes — pure addition.
# ============================================================


def _fetch_vendor_for_payable(db, vendor_id, vendor_address_id):
    if not vendor_id:
        return {"address": {}}
    try:
        vr = (db.table("vendors").select("name, tax_id, email, phone")
              .eq("id", str(vendor_id)).single().execute())
        vendor = vr.data or {}
    except Exception as e:
        log.error(f"vendor fetch failed for {vendor_id}: {e}")
        vendor = {}
    address: dict = {}
    if vendor_address_id:
        try:
            ar = (db.table("addresses")
                  .select("street, city, state, postal_code, country")
                  .eq("id", str(vendor_address_id)).single().execute())
            address = ar.data or {}
        except Exception as e:
            log.error(f"address fetch failed for {vendor_address_id}: {e}")
    return {**vendor, "address": address}
 
 
def _build_payable_raw_text(invoice, vendor, line_items):
    lines: list[str] = []
    lines.append(f"Invoice: {invoice.get('invoice_number')}")
    lines.append("Type: payable")
    lines.append("")
    lines.append(f"From: {vendor.get('name', 'Unknown')}")
    lines.append("To: K4Y")
    lines.append(f"Issue date: {invoice.get('issue_date')}")
    if invoice.get("due_date"):
        lines.append(f"Due date: {invoice['due_date']}")
    lines.append(f"Currency: {invoice.get('currency')}")
    lines.append("Line items:")
    for i, li in enumerate(line_items, 1):
        lines.append(
            f"  {i}. {li.get('description')} | "
            f"qty={li.get('quantity')} | "
            f"unit_price={li.get('unit_price')} | "
            f"subtotal={li.get('line_subtotal')}"
        )
    lines.append(f"Subtotal: {invoice.get('subtotal')}")
    lines.append(f"Tax ({invoice.get('tax_percent')}%): {invoice.get('total_tax')}")
    lines.append(f"Grand total: {invoice.get('grand_total')}")
    return "\n".join(lines)
 
 
def _build_payable_extraction_json(invoice, vendor, line_items):
    return {
        "schema_version": "1.0",
        "document_metadata": {
            "document_type":        "invoice",
            "extraction_timestamp": datetime.utcnow().isoformat(),
            "confidence_score":     1.0,
            "source":               "form_input",
        },
        "invoice": {
            "invoice_number": invoice.get("invoice_number"),
            "issue_date":     invoice.get("issue_date"),
            "due_date":       invoice.get("due_date"),
            "currency":       invoice.get("currency"),
            "tax_percent":    invoice.get("tax_percent"),
            "subtotal":       invoice.get("subtotal"),
            "total_tax":      invoice.get("total_tax"),
            "grand_total":    invoice.get("grand_total"),
            "discount":       invoice.get("discount"),
            "payment_method": invoice.get("payment_method"),
            "description":    invoice.get("description"),
            "status":         invoice.get("status"),
        },
        "vendor": {
            "name":    vendor.get("name"),
            "tax_id":  vendor.get("tax_id"),
            "email":   vendor.get("email"),
            "phone":   vendor.get("phone"),
            "address": vendor.get("address") or {},
        },
        "client": None,
        "line_items": [
            {
                "description":   li.get("description"),
                "quantity":      li.get("quantity"),
                "unit_price":    li.get("unit_price"),
                "line_subtotal": li.get("line_subtotal"),
                "discount":      li.get("discount", 0),
            } for li in line_items
        ],
        "payments": [],
    }
 
 
def create_payable_invoice(db, payload):
    """
    Create a payable invoice from structured form input.
    - invoice_type = 'payable'
    - links vendor_id, no client_id
    - status = 'unpaid' (no draft state for payables)
    - invoice_number auto-generated as PAY-{year}-{n:04d}
    - stores raw_doc + extraction_json, generates embeddings, runs compliance
    - no PDF rendered (OCR upload path handles that)
    """
    data = payload.model_dump(mode="json")
    line_items_input = data.pop("line_items", []) or []
    company_id = data.get("company_id")
 
    year = datetime.utcnow().year
    try:
        result = (
            db.table("invoices").select("id", count="exact")
            .eq("company_id", company_id)
            .eq("invoice_type", "payable")
            .execute()
        )
        n = (result.count or 0) + 1
    except Exception as e:
        log.error(f"payable_invoice_number_count_failed: {e}")
        n = int(datetime.utcnow().strftime("%H%M%S"))
    if not data.get("invoice_number"):
        data["invoice_number"] = f"PAY-{year}-{n:04d}"
    data["status"]         = "unpaid"
    data["invoice_type"]   = "payable"
 
    try:
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create payable invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Invoice insert returned no data")
 
    invoice    = result.data[0]
    invoice_id = invoice["id"]
    inv_num    = invoice.get("invoice_number", "Unknown")
 
    log.info(f"payable_create  invoice_id={invoice_id}  invoice_number={inv_num!r}")
 
    line_items_rows: list[dict] = []
    if line_items_input:
        rows = [{
            "company_id":    company_id,
            "invoice_id":    invoice_id,
            "description":   li.get("description", ""),
            "quantity":      li.get("quantity", 1),
            "unit_price":    li.get("unit_price", 0),
            "line_subtotal": li.get("line_subtotal", 0),
            "discount":      li.get("discount", 0),
        } for li in line_items_input]
        try:
            li_result = db.table("line_items").insert(rows).execute()
            line_items_rows = li_result.data or rows
        except Exception as e:
            log.error(f"payable_create  stage=line_items_insert_failed  error={e}")
            line_items_rows = rows
 
    vendor_data     = _fetch_vendor_for_payable(db, invoice.get("vendor_id"), invoice.get("vendor_address_id"))
    raw_text        = _build_payable_raw_text(invoice, vendor_data, line_items_rows)
    extraction_json = _build_payable_extraction_json(invoice, vendor_data, line_items_rows)
 
    try:
        db.table("invoice_raw_documents").insert({
            "company_id":      company_id,
            "invoice_id":      invoice_id,
            "raw_text":        raw_text,
            "extraction_json": extraction_json,
            "schema_version":  "1.0",
            "storage_path":    None,
        }).execute()
    except Exception as e:
        log.error(f"payable_create  stage=raw_doc_insert_failed  error={e}")
 
    try:
        from app.services.embedding_service import generate_and_store_embeddings
        generate_and_store_embeddings(db, company_id, invoice_id, raw_text, extraction_json)
    except Exception as e:
        log.error(f"payable_create  stage=embedding_failed  error={e}")
        _insert_compliance_flag(db, company_id, invoice_id, "embedding_failed", "low", f"Embedding failed: {e}")
 
    try:
        from app.services.compliance_service import validate_invoice_compliance
        validate_invoice_compliance(db, company_id, invoice_id)
    except Exception as e:
        log.error(f"payable_create  stage=compliance_failed  error={e}")
 
    return invoice
 
def _build_payable_raw_text(invoice, vendor, line_items):
    lines: list[str] = []
    lines.append(f"Invoice: {invoice.get('invoice_number')}")
    lines.append("Type: payable")
    lines.append("")
    lines.append(f"From: {vendor.get('name', 'Unknown')}")
    lines.append("To: K4Y")
    lines.append(f"Issue date: {invoice.get('issue_date')}")
    if invoice.get("due_date"):
        lines.append(f"Due date: {invoice['due_date']}")
    lines.append(f"Currency: {invoice.get('currency')}")
    lines.append("Line items:")
    for i, li in enumerate(line_items, 1):
        lines.append(
            f"  {i}. {li.get('description')} | "
            f"qty={li.get('quantity')} | "
            f"unit_price={li.get('unit_price')} | "
            f"subtotal={li.get('line_subtotal')}"
        )
    lines.append(f"Subtotal: {invoice.get('subtotal')}")
    lines.append(f"Tax ({invoice.get('tax_percent')}%): {invoice.get('total_tax')}")
    lines.append(f"Grand total: {invoice.get('grand_total')}")
    return "\n".join(lines)


def _build_payable_extraction_json(invoice, vendor, line_items):
    return {
        "schema_version": "1.0",
        "document_metadata": {
            "document_type":        "invoice",
            "extraction_timestamp": datetime.utcnow().isoformat(),
            "confidence_score":     1.0,
            "source":               "form_input",
        },
        "invoice": {
            "invoice_number": invoice.get("invoice_number"),
            "issue_date":     invoice.get("issue_date"),
            "due_date":       invoice.get("due_date"),
            "currency":       invoice.get("currency"),
            "tax_percent":    invoice.get("tax_percent"),
            "subtotal":       invoice.get("subtotal"),
            "total_tax":      invoice.get("total_tax"),
            "grand_total":    invoice.get("grand_total"),
            "discount":       invoice.get("discount"),
            "payment_method": invoice.get("payment_method"),
            "description":    invoice.get("description"),
            "status":         invoice.get("status"),
        },
        "vendor": {
            "name":    vendor.get("name"),
            "tax_id":  vendor.get("tax_id"),
            "email":   vendor.get("email"),
            "phone":   vendor.get("phone"),
            "address": vendor.get("address") or {},
        },
        "client": None,
        "line_items": [
            {
                "description":   li.get("description"),
                "quantity":      li.get("quantity"),
                "unit_price":    li.get("unit_price"),
                "line_subtotal": li.get("line_subtotal"),
                "discount":      li.get("discount", 0),
            } for li in line_items
        ],
        "payments": [],
    }


def create_payable_invoice(db, payload):
    """
    Create a payable invoice from structured form input.
    - invoice_type = 'payable'
    - links vendor_id, no client_id
    - status = 'unpaid' (no draft state for payables)
    - invoice_number auto-generated as PAY-{year}-{n:04d}
    - stores raw_doc + extraction_json, generates embeddings, runs compliance
    - no PDF rendered (OCR upload path handles that)
    """
    data = payload.model_dump(mode="json")
    line_items_input = data.pop("line_items", []) or []
    company_id = data.get("company_id")

    year = datetime.utcnow().year
    try:
        result = (
            db.table("invoices").select("id", count="exact")
            .eq("company_id", company_id)
            .eq("invoice_type", "payable")
            .execute()
        )
        n = (result.count or 0) + 1
    except Exception as e:
        log.error(f"payable_invoice_number_count_failed: {e}")
        n = int(datetime.utcnow().strftime("%H%M%S"))
    data["invoice_number"] = f"PAY-{year}-{n:04d}"
    data["status"]         = "unpaid"
    data["invoice_type"]   = "payable"

    try:
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create payable invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Invoice insert returned no data")

    invoice    = result.data[0]
    invoice_id = invoice["id"]
    inv_num    = invoice.get("invoice_number", "Unknown")

    log.info(f"payable_create  invoice_id={invoice_id}  invoice_number={inv_num!r}")

    line_items_rows: list[dict] = []
    if line_items_input:
        rows = [{
            "company_id":    company_id,
            "invoice_id":    invoice_id,
            "description":   li.get("description", ""),
            "quantity":      li.get("quantity", 1),
            "unit_price":    li.get("unit_price", 0),
            "line_subtotal": li.get("line_subtotal", 0),
            "discount":      li.get("discount", 0),
        } for li in line_items_input]
        try:
            li_result = db.table("line_items").insert(rows).execute()
            line_items_rows = li_result.data or rows
        except Exception as e:
            log.error(f"payable_create  stage=line_items_insert_failed  error={e}")
            line_items_rows = rows

    vendor_data     = _fetch_vendor_for_payable(db, invoice.get("vendor_id"), invoice.get("vendor_address_id"))
    raw_text        = _build_payable_raw_text(invoice, vendor_data, line_items_rows)
    extraction_json = _build_payable_extraction_json(invoice, vendor_data, line_items_rows)

    try:
        db.table("invoice_raw_documents").insert({
            "company_id":      company_id,
            "invoice_id":      invoice_id,
            "raw_text":        raw_text,
            "extraction_json": extraction_json,
            "schema_version":  "1.0",
            "storage_path":    None,
        }).execute()
    except Exception as e:
        log.error(f"payable_create  stage=raw_doc_insert_failed  error={e}")

    try:
        from app.services.embedding_service import generate_and_store_embeddings
        generate_and_store_embeddings(db, company_id, invoice_id, raw_text, extraction_json)
    except Exception as e:
        log.error(f"payable_create  stage=embedding_failed  error={e}")
        _insert_compliance_flag(db, company_id, invoice_id, "embedding_failed", "low", f"Embedding failed: {e}")

    try:
        from app.services.compliance_service import validate_invoice_compliance
        validate_invoice_compliance(db, company_id, invoice_id)
    except Exception as e:
        log.error(f"payable_create  stage=compliance_failed  error={e}")

    return invoice