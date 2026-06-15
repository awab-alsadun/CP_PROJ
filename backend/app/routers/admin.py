"""
Admin router.
Manual triggers for background jobs — used for demo and testing.
No auth yet — MVP only.

Endpoints:
  POST /api/v1/admin/run-overdue-check     — mark overdue invoices
  POST /api/v1/admin/run-compliance-check  — re-run Phase B on all invoices
"""

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import DatabaseError, ValidationError
from app.services import compliance_service
from app.services import overdue_service

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except ValidationError as e:
        raise HTTPException(400, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


@router.post("/run-overdue-check")
def run_overdue_check(db: Client = Depends(get_supabase)):
    return _handle(
        overdue_service.check_and_mark_overdue,
        db, settings.MVP_COMPANY_ID,
    )


@router.post("/run-compliance-check")
def run_compliance_check(db: Client = Depends(get_supabase)):
    """
    Re-run Phase B compliance checks on every non-deleted invoice.

    Phase B includes:
      missing_client_email, duplicate_invoice_number, wrong_tax_applied,
      missing_vendor_tax_id, negative_line_item, future_issue_date,
      due_before_issue, overpayment.

    Phase A checks are NOT re-run by this endpoint — they require the
    original OCR text and LLM extraction, which only exist during ingestion.

    Each invoice's Phase B flags are cleared and re-written. Auto-resolves
    flags that no longer apply. Creates notifications for high-severity flags.
    """
    return _handle(
        compliance_service.run_compliance_check_all,
        db, settings.MVP_COMPANY_ID,
    )