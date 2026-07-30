"""
Reset and Backfill Invoice Embeddings
-------------------------------------
Deletes existing invoice_embeddings for the configured company and regenerates
them from invoice_raw_documents using the configured embedding provider/model.

Typical bge-m3 setup in backend/.env:
    EMBEDDING_PROVIDER=ollama
    OLLAMA_EMBEDDING_MODEL=bge-m3
    EMBEDDING_DIMENSION=1024

Before running, make sure Supabase vector columns/RPCs use the same dimension
as EMBEDDING_DIMENSION and Ollama has the model:
    ollama pull bge-m3

Run from backend/:
    python scripts/reset_and_backfill_embeddings.py --yes
"""

import argparse
import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from supabase import create_client

from app.core.config import get_settings
from app.services.embedding_service import generate_and_store_embeddings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CHECKPOINT_FILE = BACKEND_DIR / "backfill_checkpoint.json"


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Delete and regenerate invoice embeddings for MVP_COMPANY_ID."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of existing invoice_embeddings for the configured company.",
    )
    return parser.parse_args()


def _decode_extraction(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return raw or {}


def main():
    args = _parse_args()
    if not args.yes:
        raise SystemExit("Refusing to delete embeddings without --yes.")

    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    log.info(f"Company ID: {company_id}")
    log.info(f"Embedding provider: {settings.EMBEDDING_PROVIDER}")
    log.info(f"Ollama embedding model: {settings.OLLAMA_EMBEDDING_MODEL}")
    log.info(f"Embedding dimension: {settings.EMBEDDING_DIMENSION}")

    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    log.warning("Deleting existing invoice_embeddings for configured company...")
    delete_result = (
        db.table("invoice_embeddings")
        .delete()
        .eq("company_id", company_id)
        .execute()
    )
    deleted = len(delete_result.data or [])
    log.info(f"Deleted {deleted} existing invoice embedding rows")

    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        log.info(f"Deleted checkpoint file: {CHECKPOINT_FILE}")

    result = (
        db.table("invoice_raw_documents")
        .select("invoice_id, raw_text, extraction_json")
        .eq("company_id", company_id)
        .execute()
    )
    records = result.data or []
    if not records:
        log.warning("No invoice_raw_documents found. Nothing to backfill.")
        return

    success = 0
    failed = 0
    for idx, record in enumerate(records, 1):
        invoice_id = record["invoice_id"]
        log.info(f"[{idx}/{len(records)}] Re-embedding invoice {invoice_id}")
        try:
            stored = generate_and_store_embeddings(
                db=db,
                company_id=company_id,
                invoice_id=invoice_id,
                raw_text=record.get("raw_text") or "",
                extraction=_decode_extraction(record.get("extraction_json")),
            )
            log.info(f"  Stored {stored} chunks")
            success += 1
        except Exception as e:
            log.error(f"  Failed: {e}")
            failed += 1

    log.info("Backfill complete")
    log.info(f"  Success: {success}")
    log.info(f"  Failed : {failed}")


if __name__ == "__main__":
    main()
