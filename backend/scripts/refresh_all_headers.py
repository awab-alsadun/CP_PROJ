"""
Refresh all header embeddings.

Run after any bulk status change (fix_stat_rec.py, fix_stat_pay.py).
Fixes stale "Status: draft" in invoice_embeddings header chunks.

Usage:
    cd CP_PROJ/backend
    python -m scripts.refresh_all_headers
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.services.embedding_service import refresh_header_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def main():
    settings = get_settings()
    db       = get_supabase()
    company_id = settings.MVP_COMPANY_ID

    result = (
        db.table("invoices")
        .select("id, status, invoice_number")
        .eq("company_id", company_id)
        .is_("deleted_at", "null")
        .execute()
    )
    invoices = result.data or []
    log.info(f"Found {len(invoices)} invoices to refresh")

    success = 0
    failed  = 0
    for inv in invoices:
        ok = refresh_header_embedding(
            db, company_id, inv["id"], new_status=inv["status"]
        )
        if ok:
            success += 1
        else:
            failed += 1
            log.warning(f"Failed: {inv['invoice_number']} ({inv['id']})")

        if (success + failed) % 50 == 0:
            log.info(f"Progress: {success + failed}/{len(invoices)}")

    log.info(f"Done. {success} refreshed, {failed} failed out of {len(invoices)}")


if __name__ == "__main__":
    main()