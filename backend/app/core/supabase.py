"""
Supabase client dependency.

Phase 1 (now):  Returns a service_role client. Bypasses RLS.
                Tenant isolation enforced in service layer via company_id.

Phase 2 (auth): This file gets a second dependency `get_user_supabase()`
                that creates a per-request client using the user's JWT.
                RLS policies then enforce isolation at DB level.
                Service functions accept the client as a parameter,
                so the swap is transparent.
"""

from supabase import create_client, Client
from app.core.config import get_settings


def get_supabase() -> Client:
    """
    FastAPI dependency. Creates client per call.
    supabase-py is lightweight — no connection pooling concern at MVP scale.
    """
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)