"""
Embedding Service
-----------------
Generates vector embeddings for invoice text and stores them
in the invoice_embeddings table (Supabase pgvector).

Chunking strategy:
  - Split invoice text into semantic chunks (header, line items, payment info)
  - Each chunk gets its own embedding
  - chunk_type field enables filtered retrieval later

This replaces ChromaDB entirely. Vectors live alongside relational data
in the same Supabase database.
"""

import logging
from typing import Optional

from openai import OpenAI
from supabase import Client

from app.core.config import get_settings

log = logging.getLogger(__name__)


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _generate_embedding(text: str) -> list[float]:
    """
    Generate a 1536-dimension embedding vector using OpenAI.

    Args:
        text: The text to embed.

    Returns:
        List of floats (1536 dimensions for text-embedding-3-small).
    """
    settings = get_settings()
    client = _get_openai_client()

    response = client.embeddings.create(
        input=text,
        model=settings.OPENAI_EMBEDDING_MODEL,
    )

    return response.data[0].embedding


def _chunk_invoice_text(raw_text: str, extraction: dict) -> list[dict]:
    """
    Split invoice data into semantic chunks for embedding.

    Three chunk types:
      1. 'header' — vendor, client, dates, totals (structured summary)
      2. 'line_items' — all line item descriptions concatenated
      3. 'full_text' — the complete raw OCR text

    Returns:
        List of dicts with 'chunk_text' and 'chunk_type'.
    """
    chunks = []

    # Chunk 1: Structured header summary
    inv = extraction.get("invoice", {})
    vendor = extraction.get("vendor", {})
    client = extraction.get("client", {})

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

    # Chunk 3: Full raw text
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
    Generate embeddings for invoice chunks and store in pgvector.

    Args:
        db: Supabase client.
        company_id: Tenant ID.
        invoice_id: The invoice these embeddings belong to.
        raw_text: Raw OCR text.
        extraction: The structured JSON extraction dict.

    Returns:
        Number of chunks embedded and stored.
    """
    chunks = _chunk_invoice_text(raw_text, extraction)
    stored = 0

    for chunk in chunks:
        try:
            embedding = _generate_embedding(chunk["chunk_text"])

            db.table("invoice_embeddings").insert({
                "company_id": company_id,
                "invoice_id": invoice_id,
                "chunk_text": chunk["chunk_text"],
                "chunk_type": chunk["chunk_type"],
                "embedding": embedding,
                "metadata": {
                    "invoice_id": invoice_id,
                    "chunk_type": chunk["chunk_type"],
                },
            }).execute()

            stored += 1

        except Exception as e:
            log.error(
                f"Failed to embed chunk ({chunk['chunk_type']}) "
                f"for invoice {invoice_id}: {e}"
            )

    log.info(f"Stored {stored}/{len(chunks)} embeddings for invoice {invoice_id}")
    return stored