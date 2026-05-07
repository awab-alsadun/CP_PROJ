"""
Notification service.
Called from other services (invoice lifecycle, payments, uploads).
Simple insert + query — no complex logic.
"""

import uuid
from supabase import Client
from app.core.exceptions import NotFoundError, DatabaseError


def create_notification(
    db: Client,
    company_id: str,
    type: str,
    title: str,
    message: str,
    related_invoice_id: str | None = None,
) -> dict:
    """Insert a notification. Called by other services on events."""
    try:
        data = {
            "company_id": company_id,
            "type": type,
            "title": title,
            "message": message,
            "related_invoice_id": related_invoice_id,
        }
        result = db.table("notifications").insert(data).execute()
    except Exception as e:
        raise DatabaseError("Failed to create notification", detail=str(e))
    if not result.data:
        raise DatabaseError("Notification insert returned no data")
    return result.data[0]


def list_notifications(
    db: Client,
    company_id: str,
    unread_only: bool = False,
    limit: int = 20,
) -> dict:
    """
    Returns unread_count + notification list.
    unread_count is always returned regardless of filter.
    """
    try:
        # Always get unread count
        unread_result = (
            db.table("notifications")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .eq("is_read", False)
            .execute()
        )
        unread_count = unread_result.count or 0

        # Get notifications
        query = (
            db.table("notifications")
            .select("*")
            .eq("company_id", company_id)
        )
        if unread_only:
            query = query.eq("is_read", False)

        result = (
            query
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to list notifications", detail=str(e))

    return {
        "unread_count": unread_count,
        "notifications": result.data or [],
    }


def mark_read(db: Client, company_id: str, notification_id: uuid.UUID) -> dict:
    """Mark a single notification as read."""
    try:
        result = (
            db.table("notifications")
            .update({"is_read": True})
            .eq("id", str(notification_id))
            .eq("company_id", company_id)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to mark notification read", detail=str(e))
    if not result.data:
        raise NotFoundError(f"Notification {notification_id} not found")
    return result.data[0]


def mark_all_read(db: Client, company_id: str) -> int:
    """Mark all unread notifications as read. Returns count updated."""
    try:
        result = (
            db.table("notifications")
            .update({"is_read": True})
            .eq("company_id", company_id)
            .eq("is_read", False)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to mark all read", detail=str(e))
    return len(result.data) if result.data else 0