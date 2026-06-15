"""
Compliance Service — two-phase engine.

Phase A: extraction-derived. Computed during ingestion only.

Phase B: cross-row / DB-state checks. Runs at the end of each ingestion
         AND on demand via POST /api/v1/admin/run-compliance-check.

Idempotency: each phase clears its own flags for the invoice before
re-inserting. Phase B never touches Phase A flags and vice versa.

# Phase A — extraction-derived, ingestion only:
#   required_field_null      high    missing invoice_number / issue_date / grand_total / vendor.name / client.name
#   line_item_sum_mismatch   medium  line items sum != subtotal
#   ocr_low_quality          high    OCR returned < 400 chars
#   ocr_fallback_used        medium  PyMuPDF failed, Tesseract used
#   llm_retry                high    LLM needed retry to produce valid JSON
#   date_fallback_used       high    issue_date or due_date fell back to 1900-01-01
#   tax_id_fallback_used     low     vendor or client tax_id could not be extracted
#   currency_invalid         medium  currency missing or not a 3-letter ISO code
#   missing_due_date         medium  invoice has no due_date
#
# Phase B — cross-row/DB-state, runs per ingestion + admin endpoint:
#   missing_client_email     low     receivable client has no email on file
#   missing_vendor_tax_id    low     payable vendor tax_id is NULL in DB
#   negative_line_item       high    line item has negative quantity or unit_price
#   future_issue_date        high    issue_date is ahead of today
#   due_before_issue         high    due_date is before issue_date
#
# Pipeline-only — inserted inline during ingestion, not managed by phases:
#   duplicate_invoice_number high    same invoice_number + vendor already exists
#   self_invoice_vendor      medium  extracted vendor name matches own company name
#   unmatched_client         medium  receivable with no extractable client name
#   storage_upload_failed    medium  PDF upload to Supabase Storage failed
"""

import logging
from datetime import date

from supabase import Client

from app.core.exceptions import DatabaseError, NotFoundError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PHASE_A_FLAG_TYPES = {
    "required_field_null",
    "line_item_sum_mismatch",
    "ocr_low_quality",
    "ocr_fallback_used",
    "llm_retry",
    "date_fallback_used",
    "tax_id_fallback_used",
    "currency_invalid",
    "missing_due_date",
}

PHASE_B_FLAG_TYPES = {
    "missing_client_email",
    "missing_vendor_tax_id",
    "negative_line_item",
    "future_issue_date",
    "due_before_issue",
}


# ---------------------------------------------------------------------------
# Flag I/O helpers
# ---------------------------------------------------------------------------

def _delete_flags_by_type(
    db: Client, company_id: str, invoice_id: str, flag_types: set[str],
) -> None:
    if not flag_types:
        return
    try:
        (db.table("compliance_flags").delete()
         .eq("company_id", company_id)
         .eq("invoice_id", invoice_id)
         .in_("flag_type", list(flag_types))
         .execute())
    except Exception as e:
        log.error(f"Clear flags failed for {invoice_id}: {e}")


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
        log.info(f"flag_inserted  invoice={invoice_id}  type={flag_type}  sev={severity}")
    except Exception as e:
        log.error(f"Insert flag {flag_type} failed for {invoice_id}: {e}")


def _notify_high(
    db: Client, company_id: str, invoice_id: str, flag_type: str, reason: str,
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
# Phase A — write extraction-derived signals
# ---------------------------------------------------------------------------

def write_phase_a_flags(
    db: Client, company_id: str, invoice_id: str,
    signals: list[dict], confidence_score: float,
) -> dict:
    """
    Persist Phase A signals as compliance_flags rows. Idempotent: clears
    all Phase A flag types for this invoice first.
    """
    _delete_flags_by_type(db, company_id, invoice_id, PHASE_A_FLAG_TYPES)

    inserted = 0
    for sig in signals:
        ft = sig.get("flag_type")
        sev = sig.get("severity")
        reason = sig.get("reason")
        if not (ft and sev and reason):
            continue
        _insert_flag(db, company_id, invoice_id, ft, sev, reason)
        inserted += 1
        if sev == "high":
            _notify_high(db, company_id, invoice_id, ft, reason)

    return {"phase_a_flags": inserted}


# ---------------------------------------------------------------------------
# Phase B — cross-row / DB-state checks (per invoice)
# ---------------------------------------------------------------------------

def run_phase_b_checks(
    db: Client, company_id: str, invoice_id: str,
) -> dict:
    """
    Run Phase B checks on a single invoice. Idempotent.
    Returns {phase_b_flags: count_inserted}.

    Checks:
      #4  missing_client_email
      #8  missing_vendor_tax_id
      #9  negative_line_item
      #10 future_issue_date
      #11 due_before_issue
    """
    try:
        inv_res = (db.table("invoices").select("*")
                   .eq("id", invoice_id).eq("company_id", company_id)
                   .single().execute())
        inv = inv_res.data
    except Exception as e:
        raise NotFoundError(f"Invoice {invoice_id} not found: {e}")

    if not inv:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    try:
        line_items = (db.table("line_items").select("*")
                      .eq("invoice_id", invoice_id).execute()).data or []
    except Exception:
        line_items = []

    _delete_flags_by_type(db, company_id, invoice_id, PHASE_B_FLAG_TYPES)

    inserted = 0
    today = date.today()

    invoice_type = inv.get("invoice_type", "payable")
    vendor_id    = inv.get("vendor_id")
    client_id    = inv.get("client_id")

    def write(ft: str, sev: str, reason: str):
        nonlocal inserted
        _insert_flag(db, company_id, invoice_id, ft, sev, reason)
        inserted += 1
        if sev == "high":
            _notify_high(db, company_id, invoice_id, ft, reason)

    # Check #4: missing_client_email (receivable only)
    if invoice_type == "receivable" and client_id:
        try:
            client = (db.table("clients").select("email")
                      .eq("id", client_id).single().execute()).data
            if client and not client.get("email"):
                write("missing_client_email", "low", "Client has no email on file")
        except Exception as e:
            log.error(f"check#4 failed: {e}")

    # Check #8: missing_vendor_tax_id (payable only)
    if invoice_type == "payable" and vendor_id:
        try:
            vendor = (db.table("vendors").select("tax_id")
                      .eq("id", vendor_id).single().execute()).data
            tax_id = vendor.get("tax_id") if vendor else None
            if not tax_id or tax_id.strip() == "":
                write("missing_vendor_tax_id", "low", "Vendor has no tax_id on file")
        except Exception as e:
            log.error(f"check#8 failed: {e}")

    # Check #9: negative_line_item
    for item in line_items:
        try:
            qty   = float(item.get("quantity") or 0)
            price = float(item.get("unit_price") or 0)
            desc  = item.get("description", "<no desc>")
            if qty < 0:
                write("negative_line_item", "high",
                      f"Line item '{desc}' has negative quantity")
                break
            if price < 0:
                write("negative_line_item", "high",
                      f"Line item '{desc}' has negative unit_price")
                break
        except (TypeError, ValueError):
            continue

    # Check #10: future_issue_date
    try:
        issue_str = inv.get("issue_date")
        if issue_str:
            issue_dt = date.fromisoformat(str(issue_str)[:10])
            if issue_dt > today:
                write("future_issue_date", "high",
                      f"Invoice issued in the future ({(issue_dt - today).days} days ahead)")
    except (ValueError, TypeError):
        pass

    # Check #11: due_before_issue
    try:
        issue_str = inv.get("issue_date")
        due_str   = inv.get("due_date")
        if issue_str and due_str:
            issue_dt = date.fromisoformat(str(issue_str)[:10])
            due_dt   = date.fromisoformat(str(due_str)[:10])
            if due_dt < issue_dt:
                write("due_before_issue", "high", "Due date is before issue date")
    except (ValueError, TypeError):
        pass

    return {"phase_b_flags": inserted}


# ---------------------------------------------------------------------------
# Per-invoice entry point
# ---------------------------------------------------------------------------

def validate_invoice_compliance(
    db: Client, company_id: str, invoice_id: str,
) -> dict:
    """
    Runs Phase B only. Returns {invoice_id, inserted, resolved}.
    """
    try:
        prior = (db.table("compliance_flags").select("id")
                 .eq("company_id", company_id)
                 .eq("invoice_id", invoice_id)
                 .in_("flag_type", list(PHASE_B_FLAG_TYPES))
                 .execute()).data or []
        prior_count = len(prior)
    except Exception:
        prior_count = 0

    result = run_phase_b_checks(db, company_id, invoice_id)
    inserted = result["phase_b_flags"]
    resolved = max(0, prior_count - inserted)

    return {"invoice_id": invoice_id, "inserted": inserted, "resolved": resolved}


# ---------------------------------------------------------------------------
# Batch entry point — admin endpoint
# ---------------------------------------------------------------------------

def run_compliance_check_all(db: Client, company_id: str) -> dict:
    """
    Re-run Phase B for every non-deleted invoice in the company.
    Phase A is NOT re-run (requires re-ingestion).
    """
    try:
        result = (db.table("invoices").select("id")
                  .eq("company_id", company_id)
                  .is_("deleted_at", "null")
                  .execute())
        invoice_ids = [r["id"] for r in (result.data or [])]
    except Exception as e:
        raise DatabaseError("Failed to fetch invoices for batch compliance", detail=str(e))

    total_inserted = 0
    total_resolved = 0
    errors = 0

    for invoice_id in invoice_ids:
        try:
            summary = validate_invoice_compliance(db, company_id, invoice_id)
            total_inserted += summary["inserted"]
            total_resolved += summary["resolved"]
        except Exception as e:
            log.error(f"Batch compliance failed on {invoice_id}: {e}")
            errors += 1

    return {
        "invoices_checked": len(invoice_ids),
        "flags_inserted":   total_inserted,
        "flags_resolved":   total_resolved,
        "errors":           errors,
    }


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_invoice_flags(
    db: Client, company_id: str, invoice_id: str,
) -> list[dict]:
    try:
        result = (db.table("compliance_flags").select("*")
                  .eq("company_id", company_id)
                  .eq("invoice_id", invoice_id)
                  .order("created_at", desc=True)
                  .execute())
        return result.data or []
    except Exception as e:
        raise DatabaseError("Failed to fetch compliance flags", detail=str(e))


def get_compliance_summary(db: Client, company_id: str) -> dict:
    try:
        result = (db.table("compliance_flags").select("severity, flag_type")
                  .eq("company_id", company_id)
                  .execute())
        flags = result.data or []
    except Exception as e:
        raise DatabaseError("Failed to fetch compliance summary", detail=str(e))

    high   = sum(1 for f in flags if f.get("severity") == "high")
    medium = sum(1 for f in flags if f.get("severity") == "medium")
    low    = sum(1 for f in flags if f.get("severity") == "low")

    by_type: dict[str, int] = {}
    for f in flags:
        ft = f.get("flag_type", "unknown")
        by_type[ft] = by_type.get(ft, 0) + 1

    return {
        "total_flags": len(flags),
        "high":   high,
        "medium": medium,
        "low":    low,
        "by_type": by_type,
    }