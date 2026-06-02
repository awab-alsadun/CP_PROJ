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


def _insert_compliance_flag(
    db: Client, company_id: str, invoice_id: str,
    flag_type: str, severity: str, reason: str,
) -> None:
    """Best-effort compliance flag insert. Never raises."""
    try:
        db.table("compliance_flags").insert({
            "company_id": company_id,
            "invoice_id": invoice_id,
            "flag_type":  flag_type,
            "severity":   severity,
            "reason":     reason,
        }).execute()
        log.warning(
            f"compliance_flag  invoice_id={invoice_id}  type={flag_type}  "
            f"severity={severity}  reason={reason!r}"
        )
    except Exception as e:
        log.error(
            f"compliance_flag_insert_failed  invoice_id={invoice_id}  "
            f"type={flag_type}  error={e}"
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_invoice(db: Client, payload: InvoiceCreate) -> dict:
    """Bare insert. Kept for callers that don't need the full receivable flow."""
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
# Receivable creation (form input) — full flow
# ---------------------------------------------------------------------------

def _fetch_client_for_pdf(
    db: Client,
    client_id: str | None,
    client_address_id: str | None,
) -> dict:
    """Compose the client_data dict the renderer expects."""
    if not client_id:
        return {"address": {}}
    try:
        cr = (
            db.table("clients")
            .select("name, tax_id, email, phone")
            .eq("id", str(client_id))
            .single()
            .execute()
        )
        client = cr.data or {}
    except Exception as e:
        log.error(f"client fetch failed for {client_id}: {e}")
        client = {}

    address: dict = {}
    if client_address_id:
        try:
            ar = (
                db.table("addresses")
                .select("street, city, state, postal_code, country")
                .eq("id", str(client_address_id))
                .single()
                .execute()
            )
            address = ar.data or {}
        except Exception as e:
            log.error(f"address fetch failed for {client_address_id}: {e}")

    return {**client, "address": address}


def _build_raw_text(invoice: dict, client: dict, line_items: list) -> str:
    """Plain-text representation of the invoice for raw_text storage."""
    lines: list[str] = []
    lines.append(f"Invoice: {invoice.get('invoice_number')}")
    lines.append("Type: receivable")
    lines.append("")
    lines.append("From: K4Y")
    lines.append("1200 Tech Park Drive, Suite 400, Austin, TX 78701")
    lines.append("Tax ID: 84-2957301")
    lines.append("")
    lines.append(f"To: {client.get('name', 'Unknown')}")
    addr = client.get("address") or {}
    addr_parts = [
        addr.get("street"),
        ", ".join(p for p in [addr.get("city"), addr.get("state"), addr.get("postal_code")] if p),
        addr.get("country"),
    ]
    for ap in addr_parts:
        if ap:
            lines.append(ap)
    if client.get("tax_id"):
        lines.append(f"Tax ID: {client['tax_id']}")
    lines.append("")
    lines.append(f"Issue date: {invoice.get('issue_date')}")
    if invoice.get("due_date"):
        lines.append(f"Due date: {invoice['due_date']}")
    lines.append(f"Currency: {invoice.get('currency')}")
    lines.append("")
    lines.append("Line items:")
    for i, li in enumerate(line_items, 1):
        lines.append(
            f"  {i}. {li.get('description')} | "
            f"qty={li.get('quantity')} | "
            f"unit_price={li.get('unit_price')} | "
            f"subtotal={li.get('line_subtotal')}"
        )
    lines.append("")
    lines.append(f"Subtotal: {invoice.get('subtotal')}")
    lines.append(f"Tax ({invoice.get('tax_percent')}%): {invoice.get('total_tax')}")
    if invoice.get("discount"):
        lines.append(f"Discount: {invoice.get('discount')}")
    lines.append(f"Grand total: {invoice.get('grand_total')}")
    return "\n".join(lines)


def _build_extraction_json(invoice: dict, client: dict, line_items: list) -> dict:
    """
    Synthetic extraction_json matching the shape the OCR/LLM pipeline produces.
    Used by embedding_service chunk builders, so the same keys must be present.
    """
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


def create_receivable_invoice(db: Client, payload) -> dict:
    """
    Create a receivable invoice from structured form input.

    Flow:
      1. Insert invoice row (fatal on failure)
      2. Insert line_items (best-effort)
      3. Fetch client + address for PDF
      4. Render PDF (non-fatal → pdf_render_failed flag)
      5. Insert raw_doc with storage_path=None (non-fatal)
      6. Upload PDF, update raw_doc.storage_path (non-fatal → storage_upload_failed)
      7. Generate embeddings (non-fatal → embedding_failed)
      8. Run compliance validation (non-fatal)

    payload: any pydantic model exposing model_dump(mode="json"). Must contain
             InvoiceCreate fields plus an optional `line_items` list.
    """
    # ── Step 1: Insert invoice ────────────────────────────────────────────
    data = payload.model_dump(mode="json")
    line_items_input = data.pop("line_items", []) or []

    try:
        result = db.table("invoices").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create receivable invoice", detail=str(e))
    if not result.data:
        raise DatabaseError("Invoice insert returned no data")

    invoice    = result.data[0]
    invoice_id = invoice["id"]
    company_id = invoice["company_id"]
    inv_num    = invoice.get("invoice_number", "Unknown")

    log.info(
        f"receivable_create  invoice_id={invoice_id}  "
        f"invoice_number={inv_num!r}  client_id={invoice.get('client_id')}"
    )

    # ── Step 2: Insert line_items ─────────────────────────────────────────
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
            log.info(
                f"receivable_create  line_items_inserted={len(line_items_rows)}  "
                f"invoice_id={invoice_id}"
            )
        except Exception as e:
            log.error(
                f"receivable_create  stage=line_items_insert_failed  "
                f"invoice_id={invoice_id}  error={e}"
            )
            line_items_rows = rows  # use the prepared rows for PDF/embedding

    # ── Step 3: Fetch client + address for PDF ────────────────────────────
    client_data = _fetch_client_for_pdf(
        db, invoice.get("client_id"), invoice.get("client_address_id")
    )

    # Build text artifacts once — shared by raw_doc and embedding
    raw_text        = _build_raw_text(invoice, client_data, line_items_rows)
    extraction_json = _build_extraction_json(invoice, client_data, line_items_rows)

    # ── Step 4: Render PDF (in-memory) ────────────────────────────────────
    pdf_bytes: bytes | None = None
    try:
        from app.services.receivable_pdf_renderer import render_receivable_pdf
        pdf_bytes = render_receivable_pdf(invoice, client_data, line_items_rows)
        log.info(
            f"receivable_create  stage=pdf_rendered  "
            f"invoice_id={invoice_id}  size_bytes={len(pdf_bytes)}"
        )
    except Exception as e:
        log.error(
            f"receivable_create  stage=pdf_render_failed  "
            f"invoice_id={invoice_id}  error={e}"
        )
        _insert_compliance_flag(
            db, company_id, invoice_id,
            "pdf_render_failed", "medium",
            f"PDF rendering failed: {e}",
        )

    # ── Step 5: Insert raw_doc (storage_path = None for now) ──────────────
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
        log.error(
            f"receivable_create  stage=raw_doc_insert_failed  "
            f"invoice_id={invoice_id}  error={e}"
        )

    # ── Step 6: Upload PDF to storage, update storage_path ────────────────
    if pdf_bytes:
        try:
            from app.services.storage_service import upload_invoice_pdf
            storage_path = upload_invoice_pdf(
                db, company_id, invoice_id, pdf_bytes
            )
            if raw_doc_id:
                db.table("invoice_raw_documents").update({
                    "storage_path": storage_path,
                }).eq("id", raw_doc_id).execute()
            log.info(
                f"receivable_create  stage=storage_uploaded  "
                f"invoice_id={invoice_id}  path={storage_path}"
            )
        except Exception as e:
            log.error(
                f"receivable_create  stage=storage_upload_failed  "
                f"invoice_id={invoice_id}  error={e}"
            )
            _insert_compliance_flag(
                db, company_id, invoice_id,
                "storage_upload_failed", "medium",
                f"PDF upload to storage failed: {e}",
            )

    # ── Step 7: Embeddings ────────────────────────────────────────────────
    try:
        from app.services.embedding_service import generate_and_store_embeddings
        embed_count = generate_and_store_embeddings(
            db, company_id, invoice_id, raw_text, extraction_json
        )
        log.info(
            f"receivable_create  stage=embeddings_stored  "
            f"invoice_id={invoice_id}  chunks={embed_count}"
        )
    except Exception as e:
        log.error(
            f"receivable_create  stage=embedding_failed  "
            f"invoice_id={invoice_id}  error={e}"
        )
        _insert_compliance_flag(
            db, company_id, invoice_id,
            "embedding_failed", "low",
            f"Embedding generation failed: {e}",
        )

    # ── Step 8: Compliance check ──────────────────────────────────────────
    try:
        from app.services.compliance_service import validate_invoice_compliance
        validate_invoice_compliance(db, company_id, invoice_id)
    except Exception as e:
        log.error(
            f"receivable_create  stage=compliance_failed  "
            f"invoice_id={invoice_id}  error={e}"
        )

    log.info(
        f"receivable_create_complete  invoice_id={invoice_id}  "
        f"invoice_number={inv_num!r}"
    )
    return invoice


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

    if grand_total > 0 and total_paid >= grand_total:
        new_status = "paid"
    elif total_paid > 0:
        new_status = "partially_paid"
    else:
        new_status = old_status

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

    payment["invoice_status"]     = new_status
    payment["total_paid"]         = round(total_paid, 2)
    payment["grand_total"]        = round(grand_total, 2)
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