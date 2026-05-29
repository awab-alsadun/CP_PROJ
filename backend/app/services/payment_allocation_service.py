"""
Payment Allocation Service — FIFO
----------------------------------
Allocates a lump-sum payment across open invoices for an entity
(client paying receivables, or company paying vendor payables).

Rules:
  - FIFO: earliest issue_date first
  - Currency must match invoice currency exactly — never cross-currency
  - Overpayment → credited to entity's credit_balance
  - Duplicate reference → warn, don't block
  - Minimum owed threshold: 0.01 (ignore floating-point dust invoices)
  - All mutations write audit_logs
  - All status changes create notifications
  - Embedding header refreshed per affected invoice
"""

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from supabase import Client

from app.core.exceptions import DatabaseError, ValidationError

log = logging.getLogger(__name__)

OPEN_STATUSES = ["unpaid", "partially_paid", "sent", "overdue"]
DUST_THRESHOLD = Decimal("0.01")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_open_invoices(
    db: Client,
    company_id: str,
    entity_id: str,
    entity_type: str,
    currency: str,
) -> list[dict]:
    """
    Fetch open invoices for entity in FIFO order (issue_date ASC).
    Currency filter applied — never cross-currency allocation.
    """
    try:
        q = (
            db.table("invoices")
            .select("id, invoice_number, invoice_type, status, currency, "
                    "grand_total, amount_paid_so_far, issue_date")
            .eq("company_id", company_id)
            .eq("currency", currency)
            .in_("status", OPEN_STATUSES)
            .is_("deleted_at", "null")
            .order("issue_date", desc=False)   # FIFO
        )

        if entity_type == "client":
            q = q.eq("invoice_type", "receivable").eq("client_id", entity_id)
        elif entity_type == "vendor":
            q = q.eq("invoice_type", "payable").eq("vendor_id", entity_id)
        else:
            raise ValidationError(f"Invalid entity_type '{entity_type}'. Must be 'client' or 'vendor'.")

        result = q.execute()
        return result.data or []
    except ValidationError:
        raise
    except Exception as e:
        raise DatabaseError("Failed to fetch open invoices for allocation", detail=str(e))


def _check_duplicate_reference(
    db: Client, company_id: str, reference: str | None
) -> bool:
    """Returns True if this payment reference already exists."""
    if not reference:
        return False
    try:
        result = (
            db.table("payments")
            .select("id")
            .eq("company_id", company_id)
            .eq("reference", reference)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


def _apply_to_invoice(
    db: Client,
    company_id: str,
    invoice: dict,
    amount_applied: Decimal,
    method: str | None,
    reference: str | None,
    payment_date: str,
) -> dict:
    """
    Insert payment record, update invoice amount_paid_so_far and status.
    Returns allocation detail dict.
    """
    invoice_id     = invoice["id"]
    invoice_number = invoice.get("invoice_number", "Unknown")
    grand_total    = Decimal(str(invoice.get("grand_total") or 0))
    paid_so_far    = Decimal(str(invoice.get("amount_paid_so_far") or 0))
    old_status     = invoice.get("status", "unpaid")
    invoice_type   = invoice.get("invoice_type", "payable")

    new_paid_total = (paid_so_far + amount_applied).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Determine new status
    if new_paid_total >= grand_total:
        new_status = "paid"
    elif new_paid_total > Decimal("0"):
        new_status = "partially_paid"
    else:
        new_status = old_status

    remaining_balance = max(Decimal("0"), grand_total - new_paid_total)

    # Insert payment record
    try:
        db.table("payments").insert({
            "company_id":   company_id,
            "invoice_id":   invoice_id,
            "payment_date": payment_date,
            "amount":       float(amount_applied),
            "method":       method,
            "reference":    reference,
        }).execute()
    except Exception as e:
        raise DatabaseError(
            f"Failed to insert payment for invoice {invoice_id}", detail=str(e)
        )

    # Update invoice
    update_payload = {
        "amount_paid_so_far": float(new_paid_total),
        "updated_at":         payment_date,
    }
    if new_status != old_status:
        update_payload["status"] = new_status

    try:
        db.table("invoices").update(update_payload).eq("id", invoice_id).execute()
    except Exception as e:
        log.error(f"Failed to update invoice {invoice_id} after allocation: {e}")

    # Audit log
    try:
        db.table("audit_logs").insert({
            "company_id": company_id,
            "table_name": "invoices",
            "record_id":  invoice_id,
            "action":     "update",
            "performed_by": None,
            "old_data": {
                "status": old_status,
                "amount_paid_so_far": float(paid_so_far),
            },
            "new_data": {
                "status": new_status,
                "amount_paid_so_far": float(new_paid_total),
                "payment_applied":    float(amount_applied),
            },
        }).execute()
    except Exception as e:
        log.error(f"Audit log failed for invoice {invoice_id}: {e}")

    # Notification
    try:
        from app.services.notification_service import create_notification
        if new_status == "paid":
            create_notification(
                db, company_id,
                type="payment",
                title="Invoice fully paid",
                message=(
                    f"Invoice {invoice_number} fully paid "
                    f"(${float(new_paid_total):.2f} received)"
                ),
                related_invoice_id=invoice_id,
            )
        elif new_status == "partially_paid":
            create_notification(
                db, company_id,
                type="payment",
                title="Partial payment allocated",
                message=(
                    f"${float(amount_applied):.2f} allocated to invoice {invoice_number} "
                    f"(${float(new_paid_total):.2f}/${float(grand_total):.2f})"
                ),
                related_invoice_id=invoice_id,
            )
    except Exception as e:
        log.error(f"Notification failed for invoice {invoice_id}: {e}")

    # Refresh header embedding (non-fatal)
    if new_status != old_status:
        try:
            from app.services.embedding_service import refresh_header_embedding
            refresh_header_embedding(db, company_id, invoice_id, new_status)
        except Exception as e:
            log.error(f"Embedding refresh failed for invoice {invoice_id}: {e}")

    return {
        "invoice_id":       invoice_id,
        "invoice_number":   invoice_number,
        "amount_applied":   float(amount_applied),
        "previous_status":  old_status,
        "new_status":       new_status,
        "remaining_balance": float(remaining_balance),
    }


def _update_entity_credit_balance(
    db: Client,
    company_id: str,
    entity_id: str,
    entity_type: str,
    delta: Decimal,
) -> float:
    """Add delta to entity credit_balance. Returns new balance."""
    table = "clients" if entity_type == "client" else "vendors"
    try:
        current = (
            db.table(table)
            .select("credit_balance")
            .eq("id", entity_id)
            .eq("company_id", company_id)
            .single()
            .execute()
        )
        current_balance = Decimal(str(current.data.get("credit_balance") or 0))
        new_balance = (current_balance + delta).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        db.table(table).update({
            "credit_balance": float(new_balance),
        }).eq("id", entity_id).execute()
        return float(new_balance)
    except Exception as e:
        log.error(f"Failed to update credit_balance for {entity_type} {entity_id}: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# Main allocation function
# ---------------------------------------------------------------------------

def allocate_payment(
    db: Client,
    company_id: str,
    entity_id: str,
    entity_type: str,          # 'client' | 'vendor'
    amount: Decimal,
    currency: str,
    method: str | None,
    reference: str | None,
    payment_date: str,         # YYYY-MM-DD
) -> dict:
    """
    Allocate a payment across open invoices using FIFO.

    Args:
        db:           Supabase client.
        company_id:   Tenant UUID.
        entity_id:    Client or vendor UUID.
        entity_type:  'client' (receivables) | 'vendor' (payables).
        amount:       Total payment amount.
        currency:     ISO currency code — must match invoice currency.
        method:       Payment method string (optional).
        reference:    External payment reference (optional).
        payment_date: Date of payment (YYYY-MM-DD).

    Returns:
        AllocationResult-compatible dict.
    """
    amount = Decimal(str(amount))

    if amount <= Decimal("0"):
        raise ValidationError("Payment amount must be greater than zero")

    if entity_type not in ("client", "vendor"):
        raise ValidationError(
            f"Invalid entity_type '{entity_type}'. Must be 'client' or 'vendor'."
        )

    # Duplicate reference check (warn, don't block)
    if reference and _check_duplicate_reference(db, company_id, reference):
        log.warning(
            f"Duplicate payment reference '{reference}' for company {company_id}. "
            f"Proceeding — manual review recommended."
        )
        try:
            db.table("audit_logs").insert({
                "company_id": company_id,
                "table_name": "payments",
                "record_id":  company_id,  # no specific record yet
                "action":     "create",
                "performed_by": None,
                "old_data": None,
                "new_data": {
                    "warning": "duplicate_reference",
                    "reference": reference,
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                },
            }).execute()
        except Exception:
            pass

    # Fetch open invoices (FIFO, currency-matched)
    invoices = _fetch_open_invoices(
        db, company_id, entity_id, entity_type, currency
    )

    if not invoices:
        raise ValidationError(
            f"No open {currency} invoices found for this {entity_type}. "
            f"Cannot allocate payment."
        )

    # FIFO allocation loop
    remaining    = amount
    allocations  = []

    for inv in invoices:
        if remaining <= Decimal("0"):
            break

        grand_total = Decimal(str(inv.get("grand_total") or 0))
        paid_so_far = Decimal(str(inv.get("amount_paid_so_far") or 0))
        owed        = grand_total - paid_so_far

        # Skip dust invoices
        if owed < DUST_THRESHOLD:
            continue

        applied   = min(remaining, owed)
        remaining -= applied

        detail = _apply_to_invoice(
            db, company_id, inv, applied, method, reference, payment_date
        )
        allocations.append(detail)

    allocated_amount = amount - remaining

    # Handle overpayment
    overpayment_credited = Decimal("0")
    entity_credit_balance = 0.0

    if remaining > Decimal("0"):
        overpayment_credited = remaining.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        entity_credit_balance = _update_entity_credit_balance(
            db, company_id, entity_id, entity_type, overpayment_credited
        )
        log.info(
            f"Overpayment of {overpayment_credited} {currency} "
            f"credited to {entity_type} {entity_id}"
        )
        try:
            db.table("audit_logs").insert({
                "company_id": company_id,
                "table_name": "clients" if entity_type == "client" else "vendors",
                "record_id":  entity_id,
                "action":     "update",
                "performed_by": None,
                "old_data": None,
                "new_data": {
                    "overpayment_credited": float(overpayment_credited),
                    "currency":             currency,
                    "reference":            reference,
                },
            }).execute()
        except Exception as e:
            log.error(f"Overpayment audit log failed: {e}")

    return {
        "total_amount":           float(amount),
        "allocated_amount":       float(allocated_amount),
        "overpayment_credited":   float(overpayment_credited),
        "allocations":            allocations,
        "entity_credit_balance":  entity_credit_balance,
    }