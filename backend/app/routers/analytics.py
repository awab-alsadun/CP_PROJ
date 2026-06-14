"""
Analytics endpoints.
All filtered by MVP_COMPANY_ID.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import DatabaseError
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


@router.get("/dashboard")
def dashboard(db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_dashboard, db, settings.MVP_COMPANY_ID)


@router.get("/spending")
def spending(months: int = Query(6, ge=1, le=24), db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_spending, db, settings.MVP_COMPANY_ID, months)


@router.get("/revenue")
def revenue(months: int = Query(6, ge=1, le=24), db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_revenue, db, settings.MVP_COMPANY_ID, months)


@router.get("/trends")
def trends(
    months: int = Query(12, ge=1, le=36),
    invoice_type: str | None = Query(None),
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    return _handle(analytics_service.get_trends, db, settings.MVP_COMPANY_ID, months, invoice_type)


@router.get("/payment-timing")
def payment_timing(db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_payment_timing, db, settings.MVP_COMPANY_ID)


@router.get("/overdue")
def overdue(db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_overdue, db, settings.MVP_COMPANY_ID)


@router.get("/system-stats")
def system_stats(db: Client = Depends(get_supabase)):
    settings = get_settings()
    return _handle(analytics_service.get_system_stats, db, settings.MVP_COMPANY_ID)


@router.get("/page-metrics")
def page_metrics(
    invoice_type: str = Query(..., description="'payable' or 'receivable'"),
    db: Client = Depends(get_supabase),
):
    """Stable metric card values for Payables/Receivables list pages."""
    if invoice_type not in ("payable", "receivable"):
        raise HTTPException(400, "invoice_type must be 'payable' or 'receivable'")
    settings = get_settings()
    return _handle(analytics_service.get_page_metrics, db, settings.MVP_COMPANY_ID, invoice_type)