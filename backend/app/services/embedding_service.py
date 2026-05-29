"""Invoice Embedding Service
--------------------------
Generates and stores pgvector embeddings for invoice data.

Used by:
- Invoice upload pipeline (`invoice_processor.py`)
- Backfill script (`scripts/backfill_embeddings.py`)
- Status transitions / payment updates (`refresh_header_embedding`)

Storage:
  Table: `invoice_embeddings`

Chunking strategy (small + predictable):
  0) header     — invoice number, parties, totals, status, dates
  1) line_items — line items + extracted payments (structured)
  2) full_text  — raw OCR text excerpt (captures details extraction may miss)

Both chunk_index (int) and chunk_type (str) are stored.
chunk_type is used by the RAG retrieval pipeline for filtering.
chunk_index is used by refresh_header_embedding for targeted updates.

Notes:
- Keep import-time light: FastAPI imports this module on startup.
- Callers treat embeddings as best-effort; errors should be non-fatal.
"""

from __future__ import annotations

import logging
import re

from supabase import Client

from app.core.config import get_settings
from app.providers import get_embedding_provider

log = logging.getLogger(__name__)

_MAX_RAW_EXCERPT_CHARS = 8000
_MAX_LINE_ITEMS = 40

_CHUNK_TYPE_MAP: dict[int, str] = {
    0: "header",
    1: "line_items",
    2: "full_text",
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _raw_excerpt(text: str | None, max_chars: int = _MAX_RAW_EXCERPT_CHARS) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw
    head_len = int(max_chars * 0.65)
    tail_len = max_chars - head_len
    return raw[:head_len].rstrip() + "\n...\n" + raw[-tail_len:].lstrip()


def _embedding_model_name() -> str:
    settings = get_settings()
    return (
        settings.OPENAI_EMBEDDING_MODEL
        if settings.LLM_PROVIDER == "openai"
        else settings.OLLAMA_EMBEDDING_MODEL
    )


# ---------------------------------------------------------------------------
# DB fetch
# ---------------------------------------------------------------------------

def _fetch_invoice_snapshot(db: Client, company_id: str, invoice_id: str) -> dict:
    """Fetch minimal invoice fields used for the header chunk.
    Returns an empty dict on failure.
    """
    try:
        inv_res = (
            db.table("invoices")
            .select(
                "id, company_id, invoice_number, invoice_type, status, "
                "issue_date, due_date, currency, tax_percent, subtotal, total_tax, "
                "grand_total, discount, payment_method, description, amount_paid_so_far, "
                "vendor_id, client_id"
            )
            .eq("id", invoice_id)
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
        invoice = inv_res.data or {}
    except Exception as e:
        log.warning(f"Failed to fetch invoice snapshot for {invoice_id}: {e}")
        return {}

    # Attach vendor/client name based on invoice type
    vendor_id = invoice.get("vendor_id")
    if vendor_id:
        try:
            vr = db.table("vendors").select("name").eq("id", vendor_id).single().execute()
            invoice["vendor_name"] = (vr.data or {}).get("name")
        except Exception:
            invoice["vendor_name"] = None
    else:
        invoice["vendor_name"] = None

    client_id = invoice.get("client_id")
    if client_id:
        try:
            cr = db.table("clients").select("name").eq("id", client_id).single().execute()
            invoice["client_name"] = (cr.data or {}).get("name")
        except Exception:
            invoice["client_name"] = None
    else:
        invoice["client_name"] = None

    return invoice


# ---------------------------------------------------------------------------
# Chunk builders
# ---------------------------------------------------------------------------

def _build_header_chunk(
    *,
    invoice_id: str,
    invoice: dict,
    extraction: dict | None,
    override_status: str | None = None,
) -> str:
    ext_invoice = (extraction or {}).get("invoice") or {}
    vendor      = (extraction or {}).get("vendor") or {}
    client      = (extraction or {}).get("client") or {}

    invoice_number = invoice.get("invoice_number") or ext_invoice.get("invoice_number") or "N/A"
    invoice_type   = invoice.get("invoice_type") or "payable"
    status         = override_status or invoice.get("status") or ext_invoice.get("status") or "unpaid"

    issue_date  = invoice.get("issue_date") or ext_invoice.get("issue_date")
    due_date    = invoice.get("due_date")   or ext_invoice.get("due_date")
    currency    = invoice.get("currency")   or ext_invoice.get("currency")

    subtotal    = invoice.get("subtotal")    if invoice.get("subtotal")    is not None else ext_invoice.get("subtotal")
    total_tax   = invoice.get("total_tax")   if invoice.get("total_tax")   is not None else ext_invoice.get("total_tax")
    grand_total = invoice.get("grand_total") if invoice.get("grand_total") is not None else ext_invoice.get("grand_total")
    tax_percent = invoice.get("tax_percent") if invoice.get("tax_percent") is not None else ext_invoice.get("tax_percent")
    discount    = invoice.get("discount")    if invoice.get("discount")    is not None else ext_invoice.get("discount")

    payment_method = invoice.get("payment_method") or ext_invoice.get("payment_method")
    description    = invoice.get("description")    or ext_invoice.get("description")

    amount_paid = invoice.get("amount_paid_so_far")
    remaining   = None
    try:
        remaining = float(grand_total or 0) - float(amount_paid or 0)
    except Exception:
        remaining = None

    vendor_name = invoice.get("vendor_name") or vendor.get("name")
    client_name = invoice.get("client_name") or client.get("name")

    lines: list[str] = []
    lines.append(f"Invoice: {invoice_number}")
    lines.append(f"Invoice ID: {invoice_id}")
    lines.append(f"Type: {invoice_type}")
    lines.append(f"Status: {status}")

    if vendor_name:
        lines.append(f"Vendor: {vendor_name}")
    if client_name:
        lines.append(f"Client: {client_name}")
    if issue_date:
        lines.append(f"Issue date: {issue_date}")
    if due_date:
        lines.append(f"Due date: {due_date}")
    if currency:
        lines.append(f"Currency: {currency}")
    if subtotal is not None:
        lines.append(f"Subtotal: {subtotal}")
    if total_tax is not None:
        lines.append(f"Total tax: {total_tax}")
    if tax_percent is not None:
        lines.append(f"Tax percent: {tax_percent}")
    if discount is not None:
        lines.append(f"Discount: {discount}")
    if grand_total is not None:
        lines.append(f"Grand total: {grand_total}")
    if amount_paid is not None:
        lines.append(f"Amount paid so far: {amount_paid}")
    if remaining is not None:
        lines.append(f"Remaining balance: {round(remaining, 2)}")
    if payment_method:
        lines.append(f"Payment method: {payment_method}")
    if description:
        lines.append(f"Description: {_normalize_text(str(description))}")

    return "\n".join(lines).strip()


def _build_line_items_chunk(extraction: dict | None) -> str:
    if not extraction:
        return ""

    items    = extraction.get("line_items") or []
    payments = extraction.get("payments")   or []
    vendor   = extraction.get("vendor")     or {}
    client   = extraction.get("client")     or {}

    lines: list[str] = []
    if vendor.get("name"):
        lines.append(f"Vendor: {vendor['name']}")
    if client.get("name"):
        lines.append(f"Client: {client['name']}")

    lines.append(f"Line items ({len(items)}):")
    for idx, item in enumerate(items[:_MAX_LINE_ITEMS], 1):
        desc          = _normalize_text(str(item.get("description") or "")) or "(no description)"
        qty           = item.get("quantity")
        unit_price    = item.get("unit_price")
        line_subtotal = item.get("line_subtotal")
        discount      = item.get("discount")
        lines.append(
            f"{idx}. {desc} | qty={qty} | unit_price={unit_price} | "
            f"subtotal={line_subtotal} | discount={discount}"
        )
    if len(items) > _MAX_LINE_ITEMS:
        lines.append(f"(+{len(items) - _MAX_LINE_ITEMS} more items)")

    if payments:
        lines.append("")
        lines.append(f"Payments extracted ({len(payments)}):")
        for p in payments[:10]:
            lines.append(
                f"- {p.get('payment_date')} | amount={p.get('amount')} | "
                f"method={p.get('method')} | ref={p.get('reference')}"
            )

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Generate and store (initial ingestion + backfill)
# ---------------------------------------------------------------------------

def generate_and_store_embeddings(
    db: Client,
    company_id: str,
    invoice_id: str,
    raw_text: str,
    extraction: dict,
) -> int:
    """Generate embeddings for an invoice and store in invoice_embeddings.
    Returns number of chunks successfully stored.
    Deletes existing chunks first to prevent duplicates on re-ingestion.
    """
    extraction = extraction or {}

    # Clear existing chunks (idempotent — safe to re-run)
    try:
        (
            db.table("invoice_embeddings")
            .delete()
            .eq("company_id", company_id)
            .eq("invoice_id", invoice_id)
            .execute()
        )
    except Exception as e:
        log.warning(f"Failed to clear existing invoice_embeddings for {invoice_id}: {e}")

    invoice_snapshot = _fetch_invoice_snapshot(db, company_id, invoice_id)

    chunk_map: dict[int, str] = {
        0: _build_header_chunk(
            invoice_id=invoice_id,
            invoice=invoice_snapshot,
            extraction=extraction,
        ),
        1: _build_line_items_chunk(extraction),
        2: ("Raw OCR text excerpt:\n" + _raw_excerpt(raw_text))
           if (raw_text or "").strip() else "",
    }

    chunk_indexes: list[int] = []
    chunk_texts:   list[str] = []
    for idx in sorted(chunk_map.keys()):
        txt = (chunk_map[idx] or "").strip()
        if not txt:
            continue
        chunk_indexes.append(idx)
        chunk_texts.append(txt)

    if not chunk_texts:
        return 0

    embedder   = get_embedding_provider()
    vectors    = embedder.embed(chunk_texts)
    model_name = _embedding_model_name()

    rows = []
    for idx, txt, vec in zip(chunk_indexes, chunk_texts, vectors):
        rows.append({
            "company_id":  company_id,
            "invoice_id":  invoice_id,
            "chunk_index": idx,
            "chunk_type":  _CHUNK_TYPE_MAP.get(idx, "unknown"),
            "chunk_text":  txt,
            "embedding":   vec,
            "model_name":  model_name,
        })

    try:
        db.table("invoice_embeddings").insert(rows).execute()
        return len(rows)
    except Exception as e:
        log.error(f"Failed to insert invoice embeddings for {invoice_id}: {e}")
        return 0


# ---------------------------------------------------------------------------
# Refresh header chunk after status/payment change
# ---------------------------------------------------------------------------

def refresh_header_embedding(
    db: Client,
    company_id: str,
    invoice_id: str,
    new_status: str | None = None,
) -> bool:
    """Refresh only the header chunk (chunk_index=0, chunk_type='header').

    Called after every status transition or payment to keep RAG accurate.
    Returns True if update/insert succeeded, False otherwise (non-fatal).
    """
    invoice_snapshot = _fetch_invoice_snapshot(db, company_id, invoice_id)
    if not invoice_snapshot:
        return False

    header_text = _build_header_chunk(
        invoice_id=invoice_id,
        invoice=invoice_snapshot,
        extraction=None,
        override_status=new_status,
    )
    if not header_text.strip():
        return False

    embedder   = get_embedding_provider()
    vector     = embedder.embed_one(header_text)
    model_name = _embedding_model_name()

    payload = {
        "chunk_text": header_text,
        "chunk_type": "header",
        "embedding":  vector,
        "model_name": model_name,
    }

    # Try update first
    try:
        upd = (
            db.table("invoice_embeddings")
            .update(payload)
            .eq("company_id", company_id)
            .eq("invoice_id", invoice_id)
            .eq("chunk_index", 0)
            .execute()
        )
        if upd.data:
            return True
    except Exception as e:
        log.warning(f"Header embedding update failed for {invoice_id}: {e}")

    # Fallback: insert if no row existed
    try:
        db.table("invoice_embeddings").insert({
            "company_id":  company_id,
            "invoice_id":  invoice_id,
            "chunk_index": 0,
            "chunk_type":  "header",
            "chunk_text":  header_text,
            "embedding":   vector,
            "model_name":  model_name,
        }).execute()
        return True
    except Exception as e:
        log.warning(f"Header embedding insert failed for {invoice_id}: {e}")
        return False