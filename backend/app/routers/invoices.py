"""
Invoice endpoints.
Thin routing layer — all logic lives in services/invoice_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client
from decimal import Decimal
from datetime import date

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.models.schemas import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    LineItemRead,
    PaymentRead,
    InvoiceRawDocumentRead,
)
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _handle(func, *args, **kwargs):
    """Map service exceptions to HTTP responses."""
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except ValidationError as e:
        raise HTTPException(400, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


# ---------------------------------------------------------------------------
# Request models for new endpoints
# ---------------------------------------------------------------------------

class TransitionRequest(BaseModel):
    new_status: str


class PaymentRequest(BaseModel):
    amount: Decimal
    method: str | None = None
    reference: str | None = None
    payment_date: date = Field(default_factory=date.today)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.create_invoice, db, payload)


@router.get("/", response_model=list[InvoiceRead])
def list_invoices(
    company_id: uuid.UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Client = Depends(get_supabase),
):
    return _handle(invoice_service.list_invoices, db, company_id, limit, offset)


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.get_invoice, db, invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    db: Client = Depends(get_supabase),
):
    return _handle(invoice_service.update_invoice, db, invoice_id, payload)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    _handle(invoice_service.soft_delete_invoice, db, invoice_id)


# ---------------------------------------------------------------------------
# Sub-resources
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}/line-items", response_model=list[LineItemRead])
def get_line_items(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.get_line_items, db, invoice_id)


@router.get("/{invoice_id}/payments", response_model=list[PaymentRead])
def get_payments(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.get_payments, db, invoice_id)


@router.get("/{invoice_id}/raw-document", response_model=InvoiceRawDocumentRead | None)
def get_raw_document(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.get_raw_document, db, invoice_id)


# ---------------------------------------------------------------------------
# New endpoints — Lifecycle + Payments + Raw
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/transition")
def transition_status(
    invoice_id: uuid.UUID,
    body: TransitionRequest,
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID
    return _handle(
        invoice_service.transition_invoice_status,
        db, company_id, invoice_id, body.new_status,
    )


@router.post("/{invoice_id}/payments")
def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentRequest,
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID
    return _handle(
        invoice_service.record_payment,
        db, company_id, invoice_id,
        {
            "amount": float(body.amount),
            "method": body.method,
            "reference": body.reference,
            "payment_date": body.payment_date.isoformat(),
        },
    )


@router.get("/{invoice_id}/raw")
def get_raw(
    invoice_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID
    return _handle(
        invoice_service.get_raw_document_for_company,
        db, company_id, invoice_id,
    )