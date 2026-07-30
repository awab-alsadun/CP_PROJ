"""
Backfill Embeddings Script
--------------------------
Generates and stores embeddings for all existing invoices that have
no entries in invoice_embeddings yet.

Run from the backend/ directory:
    python scripts/backfill_embeddings.py

Requirements:
    - venv activated: backend/venv/Scripts/activate  (Windows)
    - .env present in backend/ with SUPABASE_URL and SUPABASE_SERVICE_KEY
    - EMBEDDING_PROVIDER set in .env (default: openai)

Checkpoint file: backfill_checkpoint.json (in backend/ directory)
    - Stores successfully processed invoice_ids
    - Re-running skips already-processed invoices
    - Delete the file to restart from scratch

Batching:
    - Embeddings are generated per invoice (3 chunks per invoice)
    - OpenAI: script includes 60s backoff on 429.
    - Ollama: no API rate limits, runs as fast as local hardware allows.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
# Run from backend/ so that app.* imports resolve correctly
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ── Env loading ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

# ── App imports (after path + env setup) ────────────────────────────────────
from supabase import create_client
from app.core.config import get_settings
from app.services.embedding_service import generate_and_store_embeddings

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Checkpoint ───────────────────────────────────────────────────────────────
CHECKPOINT_FILE = BACKEND_DIR / "backfill_checkpoint.json"


def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        return set(data.get("completed", []))
    return set()


def save_checkpoint(completed: set[str]) -> None:
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"completed": list(completed)}, f)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    log.info(f"Embedding provider: {settings.EMBEDDING_PROVIDER}")
    log.info(f"Company ID: {company_id}")

    # Connect to Supabase
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    # Load checkpoint
    completed = load_checkpoint()
    log.info(f"Checkpoint: {len(completed)} invoices already processed")

    # Fetch all invoice_raw_documents for this company
    log.info("Fetching invoice_raw_documents from Supabase...")
    result = (
        db.table("invoice_raw_documents")
        .select("id, invoice_id, raw_text, extraction_json")
        .eq("company_id", company_id)
        .execute()
    )

    records = result.data
    if not records:
        log.warning("No records found in invoice_raw_documents. Nothing to backfill.")
        return

    total = len(records)
    log.info(f"Found {total} raw documents to process")

    # Filter out already completed
    pending = [r for r in records if r["invoice_id"] not in completed]
    log.info(f"Pending: {len(pending)} (skipping {total - len(pending)} already done)")

    if not pending:
        log.info("All invoices already embedded. Nothing to do.")
        return

    # Fetch existing invoice_ids in embeddings table to avoid duplicates
    # (catches cases where checkpoint was lost but embeddings exist)
    log.info("Checking existing embeddings in invoice_embeddings table...")
    existing_result = (
        db.table("invoice_embeddings")
        .select("invoice_id")
        .eq("company_id", company_id)
        .execute()
    )
    existing_ids = {row["invoice_id"] for row in existing_result.data}
    if existing_ids:
        before = len(pending)
        pending = [r for r in pending if r["invoice_id"] not in existing_ids]
        log.info(f"Skipping {before - len(pending)} invoices with existing embeddings")

    log.info(f"Starting backfill for {len(pending)} invoices...")
    success = 0
    failed = 0

    for i, record in enumerate(pending, 1):
        invoice_id = record["invoice_id"]
        raw_text = record.get("raw_text") or ""
        extraction_raw = record.get("extraction_json") or {}
        if isinstance(extraction_raw, str):
            try:
                extraction = json.loads(extraction_raw)
            except Exception:
                extraction = {}
        else:
            extraction = extraction_raw

        log.info(f"[{i}/{len(pending)}] Embedding invoice {invoice_id}...")

        retry_count = 0
        max_retries = 3

        while retry_count < max_retries:
            try:
                chunks_stored = generate_and_store_embeddings(
                    db=db,
                    company_id=company_id,
                    invoice_id=invoice_id,
                    raw_text=raw_text,
                    extraction=extraction,
                )
                log.info(f"  ✓ {chunks_stored} chunks stored")
                completed.add(invoice_id)
                success += 1
                break

            except Exception as e:
                err_str = str(e).lower()
                if "rate" in err_str or "429" in err_str:
                    wait = 60 * (retry_count + 1)
                    log.warning(f"  Rate limit hit. Waiting {wait}s before retry...")
                    time.sleep(wait)
                    retry_count += 1
                else:
                    log.error(f"  ✗ Failed: {e}")
                    failed += 1
                    break

        # Save checkpoint every 10 invoices
        if i % 10 == 0:
            save_checkpoint(completed)
            log.info(f"  Checkpoint saved ({len(completed)} completed so far)")

    # Final checkpoint save
    save_checkpoint(completed)

    log.info("─" * 50)
    log.info(f"Backfill complete.")
    log.info(f"  Success : {success}")
    log.info(f"  Failed  : {failed}")
    log.info(f"  Total   : {len(pending)}")
    if failed > 0:
        log.warning(f"  {failed} invoices failed. Re-run the script to retry (checkpoint will skip successes).")


if __name__ == "__main__":
    main()
