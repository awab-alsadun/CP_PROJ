"""
Payments router.
Handles FIFO payment allocation, credit notes, and refunds.
All logic lives in services — this is thin HTTP only.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError, ValidationError
from app.services import payment_allocation_service, credit_service

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

class AllocateRequest(BaseModel):
    entity_id:    uuid.UUID
    entity_type:  str          # 'client' | 'vendor'
    amount:       Decimal
    currency:     str
    method:       str | None = None
    reference:    str | None = None
    payment_date: date


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
# FIFO allocation
# ---------------------------------------------------------------------------

 
"""
Patch for backend/app/routers/payments.py

In the allocate_payment endpoint, replace:

    return _handle(
        payment_allocation_service.allocate_payment,
        ...
    )

With the code below. The FIFO allocator can touch multiple invoices,
so we refresh headers for each one.
"""

# --- Replace the allocate_payment endpoint body with: ---

@router.post("/allocate")
def allocate_payment(
    body: AllocateRequest,
    db: Client = Depends(get_supabase),
):
    result = _handle(
        payment_allocation_service.allocate_payment,
        db,
        settings.MVP_COMPANY_ID,
        str(body.entity_id),
        body.entity_type,
        body.amount,
        body.currency,
        body.method,
        body.reference,
        body.payment_date.isoformat(),
    )

    # Refresh header embeddings for all invoices touched by FIFO allocation
    try:
        from app.services.embedding_service import refresh_header_embedding
        allocations = result.get("allocations", []) if isinstance(result, dict) else []
        for alloc in allocations:
            inv_id = alloc.get("invoice_id")
            new_status = alloc.get("new_status") or alloc.get("status")
            if inv_id and new_status:
                refresh_header_embedding(
                    db, settings.MVP_COMPANY_ID, str(inv_id), new_status
                )
    except Exception:
        pass  # embedding refresh never blocks payment response

    return result

# ---------------------------------------------------------------------------
# Webhook (future bank integration)
# ---------------------------------------------------------------------------

@router.post("/webhook")
def payment_webhook(body: WebhookRequest):
    """
    Future bank integration endpoint.
    Not implemented yet — returns 501 with explanation.
    When implemented: look up entity by payer_reference, then call allocate_payment.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Webhook payment matching not yet implemented. "
            "Use POST /api/v1/payments/allocate with a known entity_id instead."
        ),
    )


# ---------------------------------------------------------------------------
# Credit notes and refunds (mounted under /invoices/{id} in invoices router)
# These are also accessible here for direct access
# ---------------------------------------------------------------------------

@router.post("/invoices/{invoice_id}/credit-note")
def apply_credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteRequest,
    db: Client = Depends(get_supabase),
):
    """
    Apply a credit note to an invoice.
    Amount must not exceed amount_paid_so_far.
    Credited amount is added to the entity's credit_balance.
    """
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
    """
    Process a refund against a specific payment on an invoice.
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