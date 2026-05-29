"""
Invoice endpoints.
Thin routing layer — all logic lives in services/invoice_service.py.
"""

import uuid
from decimal import Decimal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client
import io

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
from app.services import invoice_service, compliance_service, credit_service, pdf_service

router = APIRouter(prefix="/invoices", tags=["invoices"])
settings = get_settings()


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


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Client = Depends(get_supabase)):
    return _handle(invoice_service.create_invoice, db, payload)


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
    """List all compliance flags for a specific invoice."""
    return _handle(
        compliance_service.get_invoice_flags,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
    )


@router.post("/{invoice_id}/validate")
def validate_invoice(invoice_id: uuid.UUID, db: Client = Depends(get_supabase)):
    """
    Manually trigger compliance validation for a single invoice.
    Useful after manual edits.
    """
    return _handle(
        compliance_service.validate_invoice_compliance,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
    )


# ---------------------------------------------------------------------------
# Lifecycle — Status Transition
# Wires: embedding refresh after every successful transition
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
    Receivable: draft → sent → unpaid → partially_paid | paid | overdue → paid

    After transition:
      - Audit log written
      - Notification created
      - Header embedding refreshed (keeps RAG current)
      - Compliance re-validated
    """
    result = _handle(
        invoice_service.transition_invoice_status,
        db,
        settings.MVP_COMPANY_ID,
        invoice_id,
        body.new_status,
    )

    # Refresh header embedding — non-fatal, runs after successful transition
    try:
        from app.services.embedding_service import refresh_header_embedding
        refresh_header_embedding(
            db,
            settings.MVP_COMPANY_ID,
            str(invoice_id),
            body.new_status,
        )
    except Exception:
        pass  # embedding refresh failure never blocks the response

    # Re-run compliance after transition (e.g. overdue_no_action may apply)
    try:
        compliance_service.validate_invoice_compliance(
            db, settings.MVP_COMPANY_ID, str(invoice_id)
        )
    except Exception:
        pass

    # For receivable draft → sent: generate PDF + send email
    if body.new_status == "sent":
        try:
            invoice_data = invoice_service.get_invoice(db, invoice_id)
            if invoice_data.get("invoice_type") == "receivable":
                try:
                    pdf_service.generate_invoice_pdf(
                        db, settings.MVP_COMPANY_ID, str(invoice_id)
                    )
                except Exception as e:
                    log.error(f"PDF generation failed after transition to sent: {e}")
                # Fire email (non-fatal)
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
# PDF endpoint
# ---------------------------------------------------------------------------

import logging
log = logging.getLogger(__name__)


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    """
    Returns the invoice PDF as a downloadable file.

    Receivables: returns generated PDF (auto-creates if not yet stored).
    Payables:    400 — use GET /invoices/{id}/raw for the original upload.
    """
    invoice = _handle(invoice_service.get_invoice, db, invoice_id)
    if invoice.get("invoice_type") == "payable":
        raise HTTPException(
            status_code=400,
            detail="PDF download not available for payable invoices. "
                   "Use GET /invoices/{id}/raw for the original uploaded document.",
        )

    # Try stored PDF first
    pdf_bytes = None
    try:
        pdf_bytes = pdf_service.get_stored_pdf(
            db, settings.MVP_COMPANY_ID, str(invoice_id)
        )
    except Exception:
        pass

    # Generate on demand if not stored
    if not pdf_bytes:
        try:
            pdf_bytes = pdf_service.generate_invoice_pdf(
                db, settings.MVP_COMPANY_ID, str(invoice_id)
            )
        except ValidationError as e:
            raise HTTPException(400, e.message)
        except NotFoundError as e:
            raise HTTPException(404, e.message)
        except DatabaseError as e:
            raise HTTPException(502, f"{e.message}: {e.detail}")

    if not pdf_bytes:
        raise HTTPException(404, "No PDF available for this invoice.")

    inv_number = invoice.get("invoice_number", "invoice")
    filename   = f"invoice_{inv_number}.pdf".replace("/", "-").replace(" ", "_")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/{invoice_id}/payments")
def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentRequest,
    db: Client = Depends(get_supabase),
):
    """
    Record a manual payment against a specific invoice.
    Updates amount_paid_so_far and auto-transitions status if fully paid.
    For bulk FIFO allocation use POST /api/v1/payments/allocate instead.
    """
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

    # Refresh embedding after payment (status may have changed)
    try:
        from app.services.embedding_service import refresh_header_embedding
        new_status = result.get("invoice_status")
        if new_status:
            refresh_header_embedding(
                db,
                settings.MVP_COMPANY_ID,
                str(invoice_id),
                new_status,
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
    """
    Apply a credit note to an invoice.
    Amount must not exceed amount_paid_so_far.
    """
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
    """
    Process a refund against a specific payment on this invoice.
    Amount must not exceed the original payment amount.
    """
    return _handle(
        credit_service.process_refund,
        db,
        settings.MVP_COMPANY_ID,
        str(invoice_id),
        str(body.payment_id),
        body.amount,
    )


# ---------------------------------------------------------------------------
# Raw document
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}/raw")
def get_raw(
    invoice_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    return _handle(
        invoice_service.get_raw_document_for_company,
        db,
        settings.MVP_COMPANY_ID,
        invoice_id,
    )