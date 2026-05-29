"""
Credit Service
--------------
Handles credit notes and refunds.

Credit note: issued when an invoice amount needs to be reduced after payment.
  - Reduces amount_paid_so_far on the invoice
  - Adds the credited amount to the entity's credit_balance
  - Recalculates invoice status

Refund: reverses a specific payment.
  - Validates payment exists and amount is within payment amount
  - Inserts into refunds table
  - Reduces amount_paid_so_far on the invoice
  - Recalculates invoice status
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from supabase import Client

from app.core.exceptions import DatabaseError, NotFoundError, ValidationError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _recalculate_status(amount_paid: Decimal, grand_total: Decimal) -> str:
    if grand_total <= Decimal("0"):
        return "unpaid"
    if amount_paid <= Decimal("0"):
        return "unpaid"
    if amount_paid >= grand_total:
        return "paid"
    return "partially_paid"


def _write_audit(
    db: Client, company_id: str, table: str, record_id: str,
    old_data: dict, new_data: dict,
) -> None:
    try:
        db.table("audit_logs").insert({
            "company_id":   company_id,
            "table_name":   table,
            "record_id":    record_id,
            "action":       "update",
            "performed_by": None,
            "old_data":     old_data,
            "new_data":     new_data,
        }).execute()
    except Exception as e:
        log.error(f"Audit log failed for {table}/{record_id}: {e}")


def _notify(
    db: Client, company_id: str,
    type: str, title: str, message: str, invoice_id: str,
) -> None:
    try:
        from app.services.notification_service import create_notification
        create_notification(
            db, company_id,
            type=type, title=title, message=message,
            related_invoice_id=invoice_id,
        )
    except Exception as e:
        log.error(f"Notification failed for invoice {invoice_id}: {e}")


def _update_entity_credit(
    db: Client, company_id: str, invoice: dict, delta: Decimal
) -> None:
    """Add delta to the relevant entity's credit_balance."""
    invoice_type = invoice.get("invoice_type", "payable")
    if invoice_type == "payable":
        entity_table = "vendors"
        entity_id    = invoice.get("vendor_id")
    else:
        entity_table = "clients"
        entity_id    = invoice.get("client_id")

    if not entity_id:
        return

    try:
        current = (
            db.table(entity_table)
            .select("credit_balance")
            .eq("id", entity_id)
            .eq("company_id", company_id)
            .single()
            .execute()
        )
        current_balance = Decimal(str(current.data.get("credit_balance") or 0))
        new_balance     = (current_balance + delta).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        db.table(entity_table).update({
            "credit_balance": float(new_balance),
        }).eq("id", entity_id).execute()
        log.info(
            f"credit_balance updated for {entity_table}/{entity_id}: "
            f"{float(current_balance):.2f} → {float(new_balance):.2f}"
        )
    except Exception as e:
        log.error(
            f"Failed to update credit_balance for {entity_table}/{entity_id}: {e}"
        )


# ---------------------------------------------------------------------------
# Credit Notes
# ---------------------------------------------------------------------------

def apply_credit_note(
    db: Client,
    company_id: str,
    invoice_id: str,
    amount: Decimal,
    reason: str | None,
) -> dict:
    """
    Apply a credit note to an invoice.

    Validates:
      - Invoice exists and belongs to company
      - Amount <= amount_paid_so_far (can't credit more than was paid)

    Effects:
      - Inserts credit_note record
      - Reduces invoice.amount_paid_so_far
      - Recalculates invoice status
      - Adds amount to entity credit_balance
      - Audit log + notification
    """
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise ValidationError("Credit note amount must be greater than zero")

    # Fetch invoice
    try:
        inv_result = (
            db.table("invoices").select("*")
            .eq("id", invoice_id)
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch invoice", detail=str(e))

    if not inv_result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice       = inv_result.data
    paid_so_far   = Decimal(str(invoice.get("amount_paid_so_far") or 0))
    grand_total   = Decimal(str(invoice.get("grand_total") or 0))
    old_status    = invoice.get("status", "unpaid")
    inv_number    = invoice.get("invoice_number", "Unknown")

    if amount > paid_so_far:
        raise ValidationError(
            f"Credit note amount {float(amount):.2f} exceeds "
            f"amount paid so far {float(paid_so_far):.2f}"
        )

    # Insert credit note
    try:
        cn_result = db.table("credit_notes").insert({
            "company_id": company_id,
            "invoice_id": invoice_id,
            "amount":     float(amount),
            "reason":     reason,
        }).execute()
    except Exception as e:
        raise DatabaseError("Failed to insert credit note", detail=str(e))

    if not cn_result.data:
        raise DatabaseError("Credit note insert returned no data")

    credit_note = cn_result.data[0]

    # Recalculate
    new_paid    = (paid_so_far - amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    new_paid    = max(Decimal("0"), new_paid)
    new_status  = _recalculate_status(new_paid, grand_total)

    # Update invoice
    try:
        db.table("invoices").update({
            "amount_paid_so_far": float(new_paid),
            "status":             new_status,
            "updated_at":         datetime.utcnow().isoformat(),
        }).eq("id", invoice_id).execute()
    except Exception as e:
        raise DatabaseError("Failed to update invoice after credit note", detail=str(e))

    # Entity credit_balance: for payable → vendor owes you; for receivable → you owe client
    _update_entity_credit(db, company_id, invoice, amount)

    # Audit
    _write_audit(db, company_id, "invoices", invoice_id,
                 {"status": old_status, "amount_paid_so_far": float(paid_so_far)},
                 {"status": new_status, "amount_paid_so_far": float(new_paid),
                  "credit_note_applied": float(amount)})

    # Notification
    _notify(db, company_id,
            type="credit_note",
            title="Credit note applied",
            message=f"Credit note of ${float(amount):.2f} applied to invoice {inv_number}. {reason or ''}",
            invoice_id=invoice_id)

    # Refresh embedding
    try:
        from app.services.embedding_service import refresh_header_embedding
        refresh_header_embedding(db, company_id, invoice_id, new_status)
    except Exception as e:
        log.error(f"Embedding refresh failed after credit note for {invoice_id}: {e}")

    return {
        "credit_note":  credit_note,
        "invoice_id":   invoice_id,
        "invoice_number": inv_number,
        "amount_credited": float(amount),
        "new_amount_paid_so_far": float(new_paid),
        "previous_status": old_status,
        "new_status":      new_status,
    }


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

def process_refund(
    db: Client,
    company_id: str,
    invoice_id: str,
    payment_id: str,
    amount: Decimal,
) -> dict:
    """
    Process a refund against a specific payment.

    Validates:
      - Payment exists and belongs to this invoice
      - Amount <= payment.amount

    Effects:
      - Inserts refund record
      - Reduces invoice.amount_paid_so_far
      - Recalculates invoice status
      - Audit log + notification
    """
    amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise ValidationError("Refund amount must be greater than zero")

    # Fetch payment
    try:
        pay_result = (
            db.table("payments").select("*")
            .eq("id", payment_id)
            .eq("invoice_id", invoice_id)
            .eq("company_id", company_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch payment", detail=str(e))

    if not pay_result.data:
        raise NotFoundError(f"Payment {payment_id} not found for invoice {invoice_id}")

    payment        = pay_result.data
    payment_amount = Decimal(str(payment.get("amount") or 0))

    if amount > payment_amount:
        raise ValidationError(
            f"Refund amount {float(amount):.2f} exceeds "
            f"original payment {float(payment_amount):.2f}"
        )

    # Fetch invoice
    try:
        inv_result = (
            db.table("invoices").select("*")
            .eq("id", invoice_id)
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch invoice", detail=str(e))

    if not inv_result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice     = inv_result.data
    paid_so_far = Decimal(str(invoice.get("amount_paid_so_far") or 0))
    grand_total = Decimal(str(invoice.get("grand_total") or 0))
    old_status  = invoice.get("status", "unpaid")
    inv_number  = invoice.get("invoice_number", "Unknown")

    # Insert refund
    try:
        ref_result = db.table("refunds").insert({
            "company_id": company_id,
            "invoice_id": invoice_id,
            "payment_id": payment_id,
            "amount":     float(amount),
        }).execute()
    except Exception as e:
        raise DatabaseError("Failed to insert refund", detail=str(e))

    if not ref_result.data:
        raise DatabaseError("Refund insert returned no data")

    refund = ref_result.data[0]

    # Recalculate
    new_paid   = (paid_so_far - amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    new_paid   = max(Decimal("0"), new_paid)
    new_status = _recalculate_status(new_paid, grand_total)

    # Update invoice
    try:
        db.table("invoices").update({
            "amount_paid_so_far": float(new_paid),
            "status":             new_status,
            "updated_at":         datetime.utcnow().isoformat(),
        }).eq("id", invoice_id).execute()
    except Exception as e:
        raise DatabaseError("Failed to update invoice after refund", detail=str(e))

    # Audit
    _write_audit(db, company_id, "invoices", invoice_id,
                 {"status": old_status, "amount_paid_so_far": float(paid_so_far)},
                 {"status": new_status, "amount_paid_so_far": float(new_paid),
                  "refund_applied": float(amount)})

    # Notification
    _notify(db, company_id,
            type="refund",
            title="Refund processed",
            message=f"Refund of ${float(amount):.2f} processed for invoice {inv_number}.",
            invoice_id=invoice_id)

    # Refresh embedding
    try:
        from app.services.embedding_service import refresh_header_embedding
        refresh_header_embedding(db, company_id, invoice_id, new_status)
    except Exception as e:
        log.error(f"Embedding refresh failed after refund for {invoice_id}: {e}")

    return {
        "refund":       refund,
        "invoice_id":   invoice_id,
        "invoice_number": inv_number,
        "amount_refunded": float(amount),
        "new_amount_paid_so_far": float(new_paid),
        "previous_status": old_status,
        "new_status":      new_status,
    }