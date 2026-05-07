"""
Notification endpoints.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.core.exceptions import NotFoundError, DatabaseError
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except DatabaseError as e:
        raise HTTPException(502, f"{e.message}: {e.detail}")


@router.get("")
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=50),
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    return _handle(
        notification_service.list_notifications,
        db, settings.MVP_COMPANY_ID, unread_only, limit,
    )


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID,
    db: Client = Depends(get_supabase),
):
    settings = get_settings()
    return _handle(
        notification_service.mark_read,
        db, settings.MVP_COMPANY_ID, notification_id,
    )


@router.post("/read-all")
def mark_all_read(db: Client = Depends(get_supabase)):
    settings = get_settings()
    count = _handle(
        notification_service.mark_all_read,
        db, settings.MVP_COMPANY_ID,
    )
    return {"marked_read": count}