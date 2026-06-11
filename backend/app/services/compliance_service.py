"""
Compliance Service
------------------
Validates invoices against business rules and maintains compliance_flags.

Upsert logic (per flag_type per invoice):
  - Violation found, no existing flag → INSERT
  - Violation found, flag exists      → leave (no duplicate)
  - No violation, flag exists         → DELETE (auto-resolve)
  - No violation, no flag             → nothing

High severity flags create notifications.

Trigger points:
  - After ingestion (invoice_processor.py)
  - After status transition
  - After payment recorded
  - After manual invoice edit
  - Batch: POST /api/v1/admin/run-compliance-check
"""

import logging
from datetime import date, datetime

from supabase import Client

from app.core.exceptions import DatabaseError, NotFoundError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual checks — each returns (violated: bool, reason: str | None)
# ---------------------------------------------------------------------------

def _check_tax_mismatch(invoice: dict, line_items: list[dict]) -> tuple[bool, str | None]:
    subtotal    = float(invoice.get("subtotal") or 0)
    total_tax   = float(invoice.get("total_tax") or 0)
    grand_total = float(invoice.get("grand_total") or 0)

    if grand_total == 0:
        return False, None

    expected = subtotal + total_tax
    if abs(expected - grand_total) > 0.01:
        return True, (
            f"Tax calculation mismatch: {subtotal:.2f} + {total_tax:.2f} "
            f"= {expected:.2f} ≠ grand_total {grand_total:.2f}"
        )
    return False, None


def _check_missing_fields(invoice: dict) -> tuple[bool, list[str]]:
    missing = []

    if not invoice.get("due_date"):
        missing.append("due_date")
    if not invoice.get("invoice_number"):
        missing.append("invoice_number")

    invoice_type = invoice.get("invoice_type", "payable")
    if invoice_type == "payable" and not invoice.get("vendor_id"):
        missing.append("vendor_id")
    if invoice_type == "receivable" and not invoice.get("client_id"):
        missing.append("client_id")

    return bool(missing), missing


def _check_missing_fields(invoice: dict) -> tuple[bool, list[str]]:
    missing = []

    if not invoice.get("due_date"):
        missing.append("due_date")
    if not invoice.get("invoice_number"):
        missing.append("invoice_number")

    invoice_type = invoice.get("invoice_type", "payable")
    if invoice_type == "payable" and not invoice.get("vendor_id"):
        missing.append("vendor_id")
    # Receivable client_id absence is handled by invoice_processor's
    # 'unmatched_client' flag during ingestion. Do not duplicate here.

    return bool(missing), missing


def _check_duplicate(
    db: Client, company_id: str, invoice: dict
) -> tuple[bool, str | None]:
    invoice_id   = invoice.get("id")
    inv_number   = invoice.get("invoice_number")
    invoice_type = invoice.get("invoice_type", "payable")

    if not inv_number:
        return False, None

    try:
        q = (
            db.table("invoices")
            .select("id")
            .eq("company_id", company_id)
            .eq("invoice_number", inv_number)
            .neq("id", invoice_id)               # exclude self
            .is_("deleted_at", "null")
        )
        if invoice_type == "payable" and invoice.get("vendor_id"):
            q = q.eq("vendor_id", invoice["vendor_id"])
        elif invoice_type == "receivable" and invoice.get("client_id"):
            q = q.eq("client_id", invoice["client_id"])

        result = q.execute()
        if result.data:
            return True, (
                f"Duplicate invoice number '{inv_number}' "
                f"already exists (id: {result.data[0]['id']})"
            )
    except Exception as e:
        log.error(f"Duplicate check DB error for invoice {invoice_id}: {e}")

    return False, None


def _check_line_item_mismatch(invoice: dict, line_items: list[dict]) -> tuple[bool, str | None]:
    if not line_items:
        return False, None

    subtotal = float(invoice.get("subtotal") or 0)
    if subtotal == 0:
        return False, None

    items_sum = sum(float(item.get("line_subtotal") or 0) for item in line_items)
    if abs(items_sum - subtotal) > 0.01:
        return True, (
            f"Line items sum {items_sum:.2f} ≠ invoice subtotal {subtotal:.2f}"
        )
    return False, None


def _check_overdue_no_action(invoice: dict) -> tuple[bool, str | None]:
    if invoice.get("status") != "overdue":
        return False, None

    updated_at = invoice.get("updated_at") or invoice.get("created_at")
    if not updated_at:
        return False, None

    try:
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        days_overdue = (datetime.now(updated_at.tzinfo) - updated_at).days
        if days_overdue > 30:
            amount_paid = float(invoice.get("amount_paid_so_far") or 0)
            if amount_paid == 0:
                return True, (
                    f"Invoice overdue for {days_overdue} days with no payment recorded"
                )
    except Exception as e:
        log.warning(f"overdue_no_action date parse failed: {e}")

    return False, None


# ---------------------------------------------------------------------------
# Flag upsert helpers
# ---------------------------------------------------------------------------

def _get_existing_flags(
    db: Client, company_id: str, invoice_id: str
) -> dict[str, dict]:
    """Returns {flag_type: flag_row} for all existing flags on this invoice."""
    try:
        result = (
            db.table("compliance_flags")
            .select("*")
            .eq("company_id", company_id)
            .eq("invoice_id", invoice_id)
            .execute()
        )
        return {row["flag_type"]: row for row in (result.data or [])}
    except Exception as e:
        log.error(f"Failed to fetch compliance flags for {invoice_id}: {e}")
        return {}


def _insert_flag(
    db: Client, company_id: str, invoice_id: str,
    flag_type: str, severity: str, reason: str,
) -> None:
    try:
        db.table("compliance_flags").insert({
            "company_id": company_id,
            "invoice_id": invoice_id,
            "flag_type":  flag_type,
            "severity":   severity,
            "reason":     reason,
        }).execute()
        log.info(f"Compliance flag inserted: {flag_type} ({severity}) on {invoice_id}")
    except Exception as e:
        log.error(f"Failed to insert compliance flag {flag_type} for {invoice_id}: {e}")


def _delete_flag(db: Client, flag_id: str) -> None:
    try:
        db.table("compliance_flags").delete().eq("id", flag_id).execute()
        log.info(f"Compliance flag auto-resolved: {flag_id}")
    except Exception as e:
        log.error(f"Failed to delete compliance flag {flag_id}: {e}")


def _notify_high_severity(
    db: Client, company_id: str, invoice_id: str,
    flag_type: str, reason: str,
) -> None:
    try:
        from app.services.notification_service import create_notification
        create_notification(
            db, company_id,
            type="compliance",
            title=f"Compliance issue: {flag_type.replace('_', ' ').title()}",
            message=reason,
            related_invoice_id=invoice_id,
        )
    except Exception as e:
        log.error(f"Compliance notification failed for {invoice_id}: {e}")


# ---------------------------------------------------------------------------
# Process a single check result
# ---------------------------------------------------------------------------

def _process_check(
    db: Client,
    company_id: str,
    invoice_id: str,
    flag_type: str,
    severity: str,
    violated: bool,
    reason: str | None,
    existing_flags: dict[str, dict],
) -> None:
    existing = existing_flags.get(flag_type)

    if violated and reason:
        if not existing:
            _insert_flag(db, company_id, invoice_id, flag_type, severity, reason)
            if severity == "high":
                _notify_high_severity(db, company_id, invoice_id, flag_type, reason)
        # If flag already exists, leave it — no duplicate
    else:
        if existing:
            _delete_flag(db, existing["id"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_invoice_compliance(
    db: Client, company_id: str, invoice_id: str,
) -> dict:
    """
    Run all compliance checks on a single invoice.
    Inserts new flags, auto-resolves cleared flags.

    Returns summary: { checked, inserted, resolved }
    """
    # Fetch invoice
    try:
        inv_result = (
            db.table("invoices").select("*")
            .eq("id", invoice_id)
            .eq("company_id", company_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise DatabaseError(f"Failed to fetch invoice {invoice_id}", detail=str(e))

    if not inv_result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice = inv_result.data

    # Fetch line items
    try:
        li_result = (
            db.table("line_items").select("*")
            .eq("invoice_id", invoice_id)
            .execute()
        )
        line_items = li_result.data or []
    except Exception:
        line_items = []

    # Fetch existing flags
    existing_flags = _get_existing_flags(db, company_id, invoice_id)

    inserted = 0
    resolved = 0
    checks_run = 0

    def run(flag_type, severity, violated, reason):
        nonlocal inserted, resolved, checks_run
        checks_run += 1
        had_flag = flag_type in existing_flags
        _process_check(
            db, company_id, invoice_id,
            flag_type, severity, violated, reason, existing_flags,
        )
        now_has = violated and bool(reason) and not had_flag
        now_resolved = not violated and had_flag
        if now_has:
            inserted += 1
        if now_resolved:
            resolved += 1

    # --- TAX_MISMATCH ---
    v, r = _check_tax_mismatch(invoice, line_items)
    run("tax_mismatch", "high", v, r)

    # --- MISSING_REQUIRED_FIELDS ---
    v, missing = _check_missing_fields(invoice)
    r = f"Missing required fields: {', '.join(missing)}" if missing else None
    run("missing_required_fields", "medium", v, r)

    # --- LOW_CONFIDENCE ---
    v, r = _check_low_confidence(invoice)
    run("low_confidence", "medium", v, r)

    # --- DUPLICATE_INVOICE ---
    v, r = _check_duplicate(db, company_id, invoice)
    run("duplicate_invoice", "high", v, r)

    # --- LINE_ITEM_MISMATCH ---
    v, r = _check_line_item_mismatch(invoice, line_items)
    run("line_item_mismatch", "medium", v, r)

    # --- OVERDUE_NO_ACTION ---
    v, r = _check_overdue_no_action(invoice)
    run("overdue_no_action", "low", v, r)

    log.info(
        f"Compliance check complete for {invoice_id}: "
        f"{checks_run} checks, {inserted} inserted, {resolved} resolved"
    )

    return {
        "invoice_id": invoice_id,
        "checks_run": checks_run,
        "inserted":   inserted,
        "resolved":   resolved,
    }


# ---------------------------------------------------------------------------
# Batch validation (for admin endpoint)
# ---------------------------------------------------------------------------

def run_compliance_check_all(db: Client, company_id: str) -> dict:
    """
    Re-validate every non-deleted invoice for the company.
    Returns aggregate summary.
    """
    try:
        result = (
            db.table("invoices").select("id")
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .execute()
        )
        invoice_ids = [row["id"] for row in (result.data or [])]
    except Exception as e:
        raise DatabaseError("Failed to fetch invoices for batch compliance", detail=str(e))

    total_inserted = 0
    total_resolved = 0
    errors         = 0

    for invoice_id in invoice_ids:
        try:
            summary = validate_invoice_compliance(db, company_id, invoice_id)
            total_inserted += summary["inserted"]
            total_resolved += summary["resolved"]
        except Exception as e:
            log.error(f"Batch compliance failed for invoice {invoice_id}: {e}")
            errors += 1

    return {
        "invoices_checked": len(invoice_ids),
        "flags_inserted":   total_inserted,
        "flags_resolved":   total_resolved,
        "errors":           errors,
    }


# ---------------------------------------------------------------------------
# Read helpers (for router)
# ---------------------------------------------------------------------------

def get_invoice_flags(
    db: Client, company_id: str, invoice_id: str,
) -> list[dict]:
    try:
        result = (
            db.table("compliance_flags").select("*")
            .eq("company_id", company_id)
            .eq("invoice_id", invoice_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        raise DatabaseError("Failed to fetch compliance flags", detail=str(e))


def get_compliance_summary(db: Client, company_id: str) -> dict:
    try:
        result = (
            db.table("compliance_flags").select("severity, flag_type")
            .eq("company_id", company_id)
            .execute()
        )
        flags = result.data or []
    except Exception as e:
        raise DatabaseError("Failed to fetch compliance summary", detail=str(e))

    high   = sum(1 for f in flags if f["severity"] == "high")
    medium = sum(1 for f in flags if f["severity"] == "medium")
    low    = sum(1 for f in flags if f["severity"] == "low")

    by_type: dict[str, int] = {}
    for f in flags:
        ft = f.get("flag_type", "unknown")
        by_type[ft] = by_type.get(ft, 0) + 1

    return {
        "total_flags": len(flags),
        "high":        high,
        "medium":      medium,
        "low":         low,
        "by_type":     by_type,
    }