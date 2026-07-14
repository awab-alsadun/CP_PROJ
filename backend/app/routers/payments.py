"""
Payments router.
FIFO allocation removed — payments are recorded directly on invoices
via POST /api/v1/invoices/{id}/payments (invoice_service.record_payment).

Remaining endpoints:
  - /webhook         — future bank integration stub
  - /invoices/{id}/credit-note
  - /invoices/{id}/refund
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.services import credit_service

router = APIRouter(prefix="/payments", tags=["payments"])
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

class WebhookRequest(BaseModel):
    payer_reference: str
    amount:          Decimal
    currency:        str
    reference:       str
    timestamp:       str


class CreditNoteRequest(BaseModel):
    amount: Decimal
    reason: str | None = None


class RefundRequest(BaseModel):
    payment_id: uuid.UUID
    amount:     Decimal




# ---------------------------------------------------------------------------
# Credit notes and refunds
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/credit-note")
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


@router.post("/invoices/{invoice_id}/refund")
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