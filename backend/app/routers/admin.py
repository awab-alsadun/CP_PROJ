"""
Admin router.
Manual triggers for background jobs — used for demo and testing.
No auth yet — MVP only. Add auth middleware before production.

Endpoints:
  POST /api/v1/admin/run-overdue-check     — mark overdue invoices
  POST /api/v1/admin/run-compliance-check  — re-validate all invoices
"""

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import DatabaseError, ValidationError
from app.services import compliance_service
from app.services import overdue_service as overdue_service

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except ValidationError as e:
        raise HTTPException(400, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


# ---------------------------------------------------------------------------
# Overdue check
# ---------------------------------------------------------------------------

@router.post("/run-overdue-check")
def run_overdue_check(db: Client = Depends(get_supabase)):
    """
    Find all invoices where due_date < today and status is still open
    (unpaid | sent | partially_paid), then transition them to 'overdue'.

    For each transitioned invoice:
      - Updates status in DB
      - Writes audit log
      - Creates internal notification
      - Sends email/SMS to client (receivables only)
      - Reruns compliance check
      - Refreshes header embedding

    Safe to call multiple times — already-overdue invoices are excluded.
    Returns count and list of transitioned invoices.
    """
    return _handle(
        overdue_service.check_and_mark_overdue,
        db,
        settings.MVP_COMPANY_ID,
    )


# ---------------------------------------------------------------------------
# Batch compliance check
# ---------------------------------------------------------------------------

@router.post("/run-compliance-check")
def run_compliance_check(db: Client = Depends(get_supabase)):
    """
    Re-validate every non-deleted invoice for the company.

    Runs all 6 compliance checks per invoice:
      tax_mismatch, missing_required_fields, low_confidence,
      duplicate_invoice, line_item_mismatch, overdue_no_action

    Auto-resolves flags that no longer apply.
    Creates notifications for new high-severity flags.

    Returns aggregate summary: invoices checked, flags inserted, flags resolved.
    """
    return _handle(
        compliance_service.run_compliance_check_all,
        db,
        settings.MVP_COMPANY_ID,
    )