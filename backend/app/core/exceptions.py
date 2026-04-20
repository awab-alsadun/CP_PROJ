"""
Application exceptions.

Service layer raises these. Routers catch and map to HTTP responses.
This keeps HTTP concerns out of business logic.
"""


class AppError(Exception):
    """Base for all application errors."""

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppError):
    """Requested resource does not exist or is soft-deleted."""
    pass


class ValidationError(AppError):
    """Business rule violation (not schema validation — Pydantic handles that)."""
    pass


class DatabaseError(AppError):
    """Supabase/Postgres operation failed."""
    pass