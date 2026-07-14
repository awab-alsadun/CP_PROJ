"""
Invoice endpoints.
Thin routing layer — all logic lives in services/invoice_service.py.

Changes:
  - POST /api/v1/invoices accepts receivables only (returns 400 for payables).
    Renders K4Y-branded PDF, persists raw_doc, uploads to Storage, generates
    embeddings, and runs compliance — all delegated to
    invoice_service.create_receivable_invoice.
  - Payload now carries line_items inline; previously they were inserted
    separately by the frontend.
  - GET /{invoice_id}/pdf unchanged: 302 redirect to signed Supabase URL.
"""

import uuid
import logging
from decimal import Decimal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.models.schemas import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceType,
    LineItemRead,
    PaymentRead,
    InvoiceRawDocumentRead,
)
from app.services import invoice_service, compliance_service, credit_service

router = APIRouter(prefix="/invoices", tags=["invoices"])
settings = get_settings()
log = logging.getLogger(__name__)


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except ValidationError as e:
        raise HTTPException(400, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TransitionRequest(BaseModel):
    new_status: str


class PaymentRequest(BaseModel):
    amount:       Decimal
    method:       str | None = None
    reference:    str | None = None
    payment_date: date = Field(default_factory=date.today)


class CreditNoteRequest(BaseModel):
    amount: Decimal
    reason: str | None = None


class RefundRequest(BaseModel):
    payment_id: uuid.UUID
    amount:     Decimal


class ReceivableLineItemInput(BaseModel):
    """Line item shape accepted alongside InvoiceCreate fields on POST /invoices."""
    description:   str
    quantity:      Decimal
    unit_price:    Decimal
    line_subtotal: Decimal
    discount:      Decimal = Decimal("0")


class CreateInvoicePayload(InvoiceCreate):
    """InvoiceCreate + inline line_items. Receivables only."""
    line_items: list[ReceivableLineItemInput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(
    payload: CreateInvoicePayload,
    db: Client = Depends(get_supabase),
):
    if payload.invoice_type == InvoiceType.receivable:
        return _handle(invoice_service.create_receivable_invoice, db, payload)
    else:
        return _handle(invoice_service.create_payable_invoice, db, payload)


@router.get("/")
def list_invoices(
    company_id: uuid.UUID = Query(...),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    invoice_type: str | None = Query(None, description="'payable' or 'receivable'"),
    search: str | None = Query(None),
    db: Client = Depends(get_supabase),
):
    return _handle(
        invoice_service.list_invoices,
        db, company_id, limit, offset, status, invoice_type, search,
    )


@router.get("/{invoice_id}")
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
# Compliance flags
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}/compliance-flags")
def get_compliance_flags(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(
        compliance_service.get_invoice_flags,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
    )


@router.post("/{invoice_id}/validate")
def validate_invoice(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    return _handle(
        compliance_service.validate_invoice_compliance,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
    )


# ---------------------------------------------------------------------------
# Lifecycle — Status Transition
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/transition")
def transition_status(
    invoice_id: uuid.UUID,
    body: TransitionRequest,
    db: Client = Depends(get_supabase),
):
    """
    Transition invoice status according to type-aware state machine.

    Payable:    unpaid → partially_paid | paid | overdue → paid
    Receivable: draft → sent → unpaid | partially_paid | paid | overdue → paid

    After transition:
      - Audit log written
      - Notification created
      - Header embedding refreshed
      - Compliance re-validated
      - For receivable draft → sent: email send (PDF already in storage)
    """
    result = _handle(
        invoice_service.transition_invoice_status,
        db,
        settings.MVP_COMPANY_ID,
        invoice_id,
        body.new_status,
    )

    try:
        from app.services.embedding_service import refresh_header_embedding
        refresh_header_embedding(
            db, settings.MVP_COMPANY_ID, str(invoice_id), body.new_status,
        )
    except Exception:
        pass

    try:
        compliance_service.validate_invoice_compliance(
            db, settings.MVP_COMPANY_ID, str(invoice_id)
        )
    except Exception:
        pass

    if body.new_status == "sent":
        try:
            invoice_data = invoice_service.get_invoice(db, invoice_id)
            if invoice_data.get("invoice_type") == "receivable":
                try:
                    from app.services.notification_delivery_service import send_invoice_email
                    client = invoice_data.get("client") or {}
                    if client.get("email"):
                        send_invoice_email(
                            invoice_data,
                            client["email"],
                            template_type="invoice_sent",
                            db=db,
                            company_id=settings.MVP_COMPANY_ID,
                        )
                except Exception as e:
                    log.error(f"Email send failed after transition to sent: {e}")
        except Exception as e:
            log.error(f"Post-transition sent hook failed: {e}")

    return result


# ---------------------------------------------------------------------------
# PDF endpoint — unified signed-URL redirect
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    """
    Returns a 302 redirect to a 5-minute signed URL for the PDF in
    private Supabase Storage. Works for both payables (uploaded via
    /upload) and receivables (rendered + uploaded on create).

    Returns 404 if the invoice has no storage_path.
    """
    _handle(invoice_service.get_invoice, db, invoice_id)

    raw_doc = None
    try:
        raw_doc = invoice_service.get_raw_document(db, invoice_id)
    except Exception:
        pass

    if not raw_doc or not raw_doc.get("storage_path"):
        raise HTTPException(
            status_code=404,
            detail="PDF not available for this invoice. "
                   "The file may not have been uploaded.",
        )

    try:
        from app.services.storage_service import get_signed_url
        signed_url = get_signed_url(
            db, raw_doc["storage_path"], expires_in=300,
        )
    except Exception as e:
        log.error(f"Failed to generate signed URL for invoice {invoice_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to generate PDF download URL.",
        )

    return RedirectResponse(url=signed_url, status_code=302)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/payments")
def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentRequest,
    db: Client = Depends(get_supabase),
):
    result = _handle(
        invoice_service.record_payment,
        db,
        settings.MVP_COMPANY_ID,
        invoice_id,
        {
            "amount":       float(body.amount),
            "method":       body.method,
            "reference":    body.reference,
            "payment_date": body.payment_date.isoformat(),
        },
    )

    try:
        from app.services.embedding_service import refresh_header_embedding
        new_status = result.get("invoice_status")
        if new_status:
            refresh_header_embedding(
                db, settings.MVP_COMPANY_ID, str(invoice_id), new_status,
            )
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Credit notes and refunds
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/credit-note")
def apply_credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteRequest,
    db: Client = Depends(get_supabase),
):
    return _handle(
        credit_service.apply_credit_note,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
        body.amount,
        body.reason,
    )


@router.post("/{invoice_id}/refund")
def process_refund(
    invoice_id: uuid.UUID,
    body: RefundRequest,
    db: Client = Depends(get_supabase),
):
    return _handle(
        credit_service.process_refund,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
        str(body.payment_id),
        body.amount,
    )


@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(
    payload: CreateInvoicePayload,
    db: Client = Depends(get_supabase),
):
    if payload.invoice_type == InvoiceType.receivable:
        return _handle(invoice_service.create_receivable_invoice, db, payload)
    else:
        return _handle(invoice_service.create_payable_invoice, db, payload)