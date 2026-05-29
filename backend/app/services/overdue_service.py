"""
Overdue Service
---------------
Finds invoices where due_date < today and status is still open,
transitions them to 'overdue', creates notifications and audit logs.

Designed as a standalone callable — scheduler-compatible signature.
For now triggered via POST /api/v1/admin/run-overdue-check.
APScheduler can call check_and_mark_overdue() nightly without changes.
"""

import logging
from datetime import date

from supabase import Client

from app.core.exceptions import DatabaseError

log = logging.getLogger(__name__)

# Statuses that can become overdue
OVERDUE_ELIGIBLE_STATUSES = ["unpaid", "sent", "partially_paid"]


def check_and_mark_overdue(db: Client, company_id: str) -> dict:
    """
    Find all open invoices past due_date and mark them overdue.

    Returns:
        { overdue_count, invoices_transitioned: [{ id, invoice_number, invoice_type }] }
    """
    today = date.today().isoformat()

    try:
        result = (
            db.table("invoices")
            .select("id, invoice_number, invoice_type, status, due_date, client_id, vendor_id")
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .in_("status", OVERDUE_ELIGIBLE_STATUSES)
            .lt("due_date", today)           # due_date < today
            .execute()
        )
        candidates = result.data or []
    except Exception as e:
        raise DatabaseError("Failed to fetch overdue candidates", detail=str(e))

    if not candidates:
        log.info("Overdue check: no candidates found")
        return {"overdue_count": 0, "invoices_transitioned": []}

    transitioned = []
    errors       = 0

    for inv in candidates:
        invoice_id   = inv["id"]
        invoice_number = inv.get("invoice_number", "Unknown")
        invoice_type = inv.get("invoice_type", "payable")
        old_status   = inv.get("status", "unpaid")

        try:
            # Update status
            db.table("invoices").update({
                "status":     "overdue",
                "updated_at": date.today().isoformat(),
            }).eq("id", invoice_id).execute()

            # Audit log
            try:
                db.table("audit_logs").insert({
                    "company_id": company_id,
                    "table_name": "invoices",
                    "record_id":  invoice_id,
                    "action":     "update",
                    "performed_by": None,
                    "old_data":   {"status": old_status},
                    "new_data":   {"status": "overdue"},
                }).execute()
            except Exception as e:
                log.error(f"Audit log failed for overdue invoice {invoice_id}: {e}")

            # Notification
            try:
                from app.services.notification_service import create_notification
                if invoice_type == "receivable":
                    msg = f"Invoice {invoice_number} sent to client is now overdue."
                else:
                    msg = f"Payable invoice {invoice_number} is overdue — payment required."
                create_notification(
                    db, company_id,
                    type="overdue",
                    title="Invoice overdue",
                    message=msg,
                    related_invoice_id=invoice_id,
                )
            except Exception as e:
                log.error(f"Overdue notification failed for {invoice_id}: {e}")

            # Email/SMS (fire-and-forget)
            try:
                _send_overdue_delivery(db, company_id, inv)
            except Exception as e:
                log.error(f"Overdue delivery failed for {invoice_id}: {e}")

            # Re-run compliance check (overdue_no_action flag may now apply)
            try:
                from app.services.compliance_service import validate_invoice_compliance
                validate_invoice_compliance(db, company_id, invoice_id)
            except Exception as e:
                log.error(f"Compliance recheck failed for overdue invoice {invoice_id}: {e}")

            # Refresh header embedding so RAG shows correct status
            try:
                from app.services.embedding_service import refresh_header_embedding
                refresh_header_embedding(db, company_id, invoice_id, "overdue")
            except Exception as e:
                log.error(f"Embedding refresh failed for overdue invoice {invoice_id}: {e}")

            transitioned.append({
                "id":             invoice_id,
                "invoice_number": invoice_number,
                "invoice_type":   invoice_type,
            })
            log.info(f"Marked overdue: {invoice_number} ({invoice_id})")

        except Exception as e:
            log.error(f"Failed to mark invoice {invoice_id} as overdue: {e}")
            errors += 1

    return {
        "overdue_count":          len(transitioned),
        "invoices_transitioned":  transitioned,
        "errors":                 errors,
    }


def _send_overdue_delivery(db: Client, company_id: str, inv: dict) -> None:
    """
    Fire-and-forget email/SMS for overdue invoices.
    Builds a minimal invoice dict — enough for the delivery service templates.
    Never raises — delivery failures must not block the overdue transition.
    """
    try:
        from app.services.notification_delivery_service import (
            send_invoice_email,
            send_invoice_sms,
        )
    except ImportError:
        log.warning("notification_delivery_service not available — skipping delivery")
        return

    invoice_type = inv.get("invoice_type", "payable")
    invoice_id   = inv["id"]

    # Build minimal invoice dict for the template
    invoice_for_template = {
        "id":             invoice_id,
        "invoice_number": inv.get("invoice_number", "Unknown"),
        "due_date":       inv.get("due_date"),
        "grand_total":    None,   # not fetched here for performance
        "currency":       None,
    }

    if invoice_type == "receivable" and inv.get("client_id"):
        # Send overdue notice to the client
        try:
            cr = (
                db.table("clients")
                .select("email, phone, name")
                .eq("id", inv["client_id"])
                .single()
                .execute()
            )
            if cr.data:
                client = cr.data
                if client.get("email"):
                    send_invoice_email(
                        invoice_for_template,
                        client["email"],
                        template_type="overdue_notice",
                    )
                if client.get("phone"):
                    send_invoice_sms(
                        invoice_for_template,
                        client["phone"],
                        template_type="overdue_notice",
                    )
        except Exception as e:
            log.error(f"Overdue delivery to client failed for {invoice_id}: {e}")

    elif invoice_type == "payable" and inv.get("vendor_id"):
        # Internal notice — you owe the vendor
        # No external recipient for payables; notification is internal only.
        # Future: send internal email to accounts payable team.
        log.info(
            f"Payable invoice {inv.get('invoice_number')} overdue — "
            f"internal notification created, no external email sent."
        )