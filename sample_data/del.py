"""
Sync receivable statuses + payments from dataset.json into Supabase.
====================================================================

Why this exists
---------------
When receivable PDFs are ingested via /upload, the OCR -> LLM pipeline
cannot recover the invoice's workflow status (draft / sent / paid /
partially_paid / overdue) because that information was never drawn on
the PDF page. Every receivable lands as 'draft' (LLM prompt default).

This script reconciles the DB with dataset.json:
  - paid           -> UPDATE status + amount_paid_so_far + INSERT payments
  - partially_paid -> UPDATE status + amount_paid_so_far + INSERT payments
  - overdue        -> UPDATE status only
  - sent           -> UPDATE status only
  - unpaid         -> UPDATE status only
  - draft          -> SKIP (DB default matches)

Idempotent: payments are only inserted if the invoice has zero existing
payment rows. Re-running is safe.

Usage
-----
  python sample_data/sync_receivable_statuses.py --dry-run   # preview
  python sample_data/sync_receivable_statuses.py             # execute

Environment
-----------
Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from the backend .env file.
Searches for .env at:
  1. CP_PROJ/backend/.env
  2. CP_PROJ/.env
  3. Current working directory .env
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sync_receivables")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
DATASET_PATH = SCRIPT_DIR / "dataset.json"

# Statuses that need DB action
STATUSES_NEEDING_UPDATE = {"paid", "partially_paid", "overdue", "sent", "unpaid"}
STATUSES_WITH_PAYMENTS = {"paid", "partially_paid"}


def find_env_file() -> Path | None:
    """Locate .env. Tries backend/, repo root, then cwd."""
    candidates = [
        SCRIPT_DIR.parent / "backend" / ".env",   # CP_PROJ/backend/.env
        SCRIPT_DIR.parent / ".env",               # CP_PROJ/.env
        Path.cwd() / ".env",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def get_supabase_client() -> Client:
    env_file = find_env_file()
    if env_file:
        log.info(f"Loading env from: {env_file}")
        load_dotenv(env_file)
    else:
        log.warning("No .env file found; relying on process environment")

    url = os.getenv("SUPABASE_URL")
    # backend uses SUPABASE_SERVICE_KEY; older scripts used SUPABASE_KEY
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not url or not key:
        log.error("SUPABASE_URL or SUPABASE_SERVICE_KEY missing from environment")
        sys.exit(1)

    return create_client(url, key)


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

def fetch_db_invoice(db: Client, invoice_number: str) -> dict | None:
    """Find the DB row for a receivable by invoice_number."""
    try:
        result = (
            db.table("invoices")
            .select("id, company_id, status, amount_paid_so_far")
            .eq("invoice_number", invoice_number)
            .eq("invoice_type", "receivable")
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        log.error(f"DB fetch failed for {invoice_number}: {e}")
        return None


def count_existing_payments(db: Client, invoice_id: str) -> int:
    try:
        result = (
            db.table("payments")
            .select("id", count="exact")
            .eq("invoice_id", invoice_id)
            .execute()
        )
        return result.count or 0
    except Exception as e:
        log.error(f"Payment count failed for invoice {invoice_id}: {e}")
        return -1  # treat as unknown; caller will skip insert


def update_invoice_status(
    db: Client,
    invoice_id: str,
    status: str,
    amount_paid_so_far: float,
    dry_run: bool,
) -> bool:
    if dry_run:
        return True
    try:
        db.table("invoices").update({
            "status": status,
            "amount_paid_so_far": amount_paid_so_far,
        }).eq("id", invoice_id).execute()
        return True
    except Exception as e:
        log.error(f"UPDATE failed for invoice {invoice_id}: {e}")
        return False


def insert_payments(
    db: Client,
    company_id: str,
    invoice_id: str,
    payments: list[dict],
    dry_run: bool,
) -> int:
    """Returns count of payments inserted (or would-be-inserted in dry-run)."""
    if not payments:
        return 0

    rows = []
    for p in payments:
        if not p.get("payment_date"):
            continue
        rows.append({
            "company_id":   company_id,
            "invoice_id":   invoice_id,
            "payment_date": p["payment_date"],
            "amount":       p.get("amount", 0),
            "method":       p.get("method"),
            "reference":    p.get("reference"),
        })

    if not rows:
        return 0

    if dry_run:
        return len(rows)

    try:
        db.table("payments").insert(rows).execute()
        return len(rows)
    except Exception as e:
        log.error(f"INSERT payments failed for invoice {invoice_id}: {e}")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync receivable statuses and payments from dataset.json"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing to DB",
    )
    args = parser.parse_args()

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    log.info(f"=== Mode: {mode} ===")

    if not DATASET_PATH.exists():
        log.error(f"dataset.json not found at {DATASET_PATH}")
        sys.exit(1)

    with open(DATASET_PATH) as f:
        data = json.load(f)

    receivables = data.get("receivables", [])
    log.info(f"Loaded {len(receivables)} receivables from dataset.json")

    db = get_supabase_client()

    # Counters
    stats = {
        "total":           len(receivables),
        "skipped_draft":   0,
        "not_in_db":       0,
        "status_updated":  0,
        "payments_added":  0,
        "payments_skipped_existing": 0,
        "errors":          0,
        "by_status":       {},
    }

    for rec in receivables:
        invoice_number = rec["invoice_number"]
        target_status  = rec["status"]
        target_paid    = rec.get("amount_paid_so_far", 0)
        payments       = rec.get("payments", [])

        stats["by_status"][target_status] = stats["by_status"].get(target_status, 0) + 1

        # Skip drafts: DB default already matches
        if target_status == "draft":
            stats["skipped_draft"] += 1
            log.debug(f"{invoice_number}: target=draft, skipping (DB default matches)")
            continue

        # Find DB row
        db_inv = fetch_db_invoice(db, invoice_number)
        if not db_inv:
            stats["not_in_db"] += 1
            log.warning(f"{invoice_number}: not found in DB, skipping")
            continue

        invoice_id = db_inv["id"]
        company_id = db_inv["company_id"]
        current_status = db_inv["status"]

        # Status update
        action = "WOULD UPDATE" if args.dry_run else "UPDATE"
        log.info(
            f"{invoice_number}: {action} status "
            f"{current_status!r} -> {target_status!r}  "
            f"amount_paid={target_paid}"
        )
        if update_invoice_status(db, invoice_id, target_status, target_paid, args.dry_run):
            stats["status_updated"] += 1
        else:
            stats["errors"] += 1
            continue

        # Payments — only for paid / partially_paid
        if target_status in STATUSES_WITH_PAYMENTS and payments:
            existing_count = count_existing_payments(db, invoice_id)
            if existing_count > 0:
                stats["payments_skipped_existing"] += 1
                log.info(
                    f"{invoice_number}: {existing_count} payment(s) already exist, "
                    f"skipping payment insert"
                )
            elif existing_count == 0:
                inserted = insert_payments(db, company_id, invoice_id, payments, args.dry_run)
                stats["payments_added"] += inserted
                verb = "WOULD INSERT" if args.dry_run else "INSERTED"
                log.info(f"{invoice_number}: {verb} {inserted} payment(s)")
            else:
                # existing_count == -1 (lookup failed)
                log.warning(f"{invoice_number}: payment count unknown, skipping insert")

    # Summary
    log.info("=" * 60)
    log.info(f"=== Summary ({mode}) ===")
    log.info(f"Total receivables in dataset: {stats['total']}")
    log.info(f"Skipped (target=draft):       {stats['skipped_draft']}")
    log.info(f"Not found in DB:              {stats['not_in_db']}")
    log.info(f"Status updates:               {stats['status_updated']}")
    log.info(f"Payments inserted:            {stats['payments_added']}")
    log.info(f"Payment inserts skipped:      {stats['payments_skipped_existing']}  (already had payments)")
    log.info(f"Errors:                       {stats['errors']}")
    log.info(f"Dataset status distribution:  {stats['by_status']}")
    if args.dry_run:
        log.info("DRY-RUN complete. No changes written. Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()