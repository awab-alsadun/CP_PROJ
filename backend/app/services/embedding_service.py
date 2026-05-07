"""
Embedding Service
-----------------
Generates vector embeddings for invoice text and stores them
in the invoice_embeddings table (Supabase pgvector).

Chunking strategy:
  - 'header'     : structured summary — vendor, client, dates, totals
  - 'line_items' : concatenated line item descriptions with quantities/prices
  - 'full_text'  : complete raw OCR text

Provider-agnostic: calls get_embedding_provider() — never imports OpenAI directly.
Switching LLM_PROVIDER in .env is the only change needed to use a different backend.
"""

import logging
from supabase import Client

from app.providers import get_embedding_provider

log = logging.getLogger(__name__)


def _chunk_invoice_text(raw_text: str, extraction: dict) -> list[dict]:
    """
    Split invoice data into semantic chunks for embedding.

    Returns:
        List of dicts with 'chunk_text' and 'chunk_type'.
    """
    chunks = []

    inv = extraction.get("invoice", {})
    vendor = extraction.get("vendor", {})
    client = extraction.get("client", {})

    # Chunk 1: Structured header summary
    header = (
        f"Invoice {inv.get('invoice_number', 'N/A')} "
        f"from {vendor.get('name', 'Unknown')} "
        f"to {client.get('name', 'Unknown')}. "
        f"Date: {inv.get('issue_date', 'N/A')}. "
        f"Due: {inv.get('due_date', 'N/A')}. "
        f"Currency: {inv.get('currency', 'N/A')}. "
        f"Subtotal: {inv.get('subtotal', 0)}. "
        f"Tax: {inv.get('total_tax', 0)} ({inv.get('tax_percent', 0)}%). "
        f"Grand total: {inv.get('grand_total', 0)}. "
        f"Status: {inv.get('status', 'draft')}."
    )
    chunks.append({"chunk_text": header, "chunk_type": "header"})

    # Chunk 2: Line items
    line_items = extraction.get("line_items", [])
    if line_items:
        items_text = "Line items: " + " | ".join(
            f"{item.get('description', 'N/A')} "
            f"(qty: {item.get('quantity', 0)}, "
            f"unit: {item.get('unit_price', 0)}, "
            f"total: {item.get('line_subtotal', 0)})"
            for item in line_items
        )
        chunks.append({"chunk_text": items_text, "chunk_type": "line_items"})

    # Chunk 3: Full raw OCR text
    if raw_text.strip():
        chunks.append({"chunk_text": raw_text, "chunk_type": "full_text"})

    return chunks


def generate_and_store_embeddings(
    db: Client,
    company_id: str,
    invoice_id: str,
    raw_text: str,
    extraction: dict,
) -> int:
    """
    Generate embeddings for all chunks of an invoice and store in pgvector.

    Args:
        db: Supabase client.
        company_id: Tenant UUID.
        invoice_id: Invoice UUID these embeddings belong to.
        raw_text: Raw OCR text from invoice_raw_documents.
        extraction: Structured JSON extraction dict.

    Returns:
        Number of chunks successfully embedded and stored.
    """
    chunks = _chunk_invoice_text(raw_text, extraction)
    if not chunks:
        log.warning(f"No chunks generated for invoice {invoice_id}")
        return 0

    embedder = get_embedding_provider()
    texts = [c["chunk_text"] for c in chunks]

    try:
        vectors = embedder.embed(texts)
    except Exception as e:
        log.error(f"Embedding generation failed for invoice {invoice_id}: {e}")
        raise

    stored = 0
    for chunk, vector in zip(chunks, vectors):
        try:
            db.table("invoice_embeddings").insert({
                "company_id": company_id,
                "invoice_id": invoice_id,
                "chunk_text": chunk["chunk_text"],
                "chunk_type": chunk["chunk_type"],
                "embedding": vector,
                "metadata": {
                    "invoice_id": invoice_id,
                    "chunk_type": chunk["chunk_type"],
                },
            }).execute()
            stored += 1
        except Exception as e:
            log.error(
                f"Failed to store chunk ({chunk['chunk_type']}) "
                f"for invoice {invoice_id}: {e}"
            )

    log.info(f"Stored {stored}/{len(chunks)} embeddings for invoice {invoice_id}")
    return stored