"""
Invoice Processing Pipeline
----------------------------
Orchestrates the full invoice ingestion flow for the FastAPI backend.

Called by the upload router when a user uploads a single invoice file.

Pipeline:
  1. OCR: Extract text from uploaded file (image or PDF)
  2. LLM: Send text to OpenAI, get structured JSON
  3. Store: Insert into relational tables via existing services
  4. Embed: Generate vector embeddings and store in pgvector

Each step is a separate service module — independently testable.
All database operations use the injected Supabase client (db parameter)
so auth context propagates when you add RLS later.

This file does NOT handle batch processing. For bulk ingestion of
500+ files, use rag_pipeline/ingest_invoices.py directly.
"""

import logging

from supabase import Client

from app.services.ocr_service import extract_text_from_image, extract_text_from_pdf
from app.services.extraction_service import extract_structured_data
from app.services.embedding_service import generate_and_store_embeddings
from app.services.vendor_service import get_or_create_vendor
from app.services.client_service import get_or_create_client
from app.services.address_service import get_or_create_address
from app.services.storage_service import upload_to_storage

log = logging.getLogger(__name__)


def process_invoice(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Full pipeline: file bytes -> structured data in Supabase.

    Args:
        db: Supabase client (injected via FastAPI Depends).
        company_id: The tenant company ID.
        file_bytes: Raw bytes of the uploaded file.
        filename: Original filename (used to determine file type).

    Returns:
        Dict with invoice_id, extraction summary, and embedding count.

    Raises:
        ValueError: If OCR returns empty text or LLM extraction fails.
    """

    # ------------------------------------------------------------------
    # Step 1: OCR - extract raw text from the file
    # ------------------------------------------------------------------
    lower_name = filename.lower()
    if lower_name.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
        raw_text = extract_text_from_image(file_bytes)
    elif lower_name.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not raw_text.strip():
        raise ValueError(f"OCR extracted no text from {filename}")

    log.info(f"OCR complete: {len(raw_text)} chars from {filename}")

    # ------------------------------------------------------------------
    # Step 1b: Store original file in Supabase Storage as PDF
    # ------------------------------------------------------------------
    try:
        storage_path = upload_to_storage(
            db, company_id, file_bytes, filename,
            invoice_number=None,
        )
        print(f"STORAGE SUCCESS: {storage_path}")
    except Exception as e:
        print(f"STORAGE FAILED: {e}")
        storage_path = None
    # ------------------------------------------------------------------
    # Step 2: LLM extraction - raw text -> structured JSON
    # ------------------------------------------------------------------
    extraction = extract_structured_data(raw_text)
    confidence = extraction.get("document_metadata", {}).get("confidence_score", 0.0)

    log.info(f"LLM extraction complete: confidence={confidence}")

    # ------------------------------------------------------------------
    # Step 3: Normalize and store - JSON -> relational tables
    # ------------------------------------------------------------------
    vendor_data = extraction.get("vendor", {})
    client_data = extraction.get("client", {})

    # --- Addresses ---
    vendor_addr = vendor_data.get("address", {})
    vendor_address_row = get_or_create_address(
        db,
        company_id,
        street=vendor_addr.get("street"),
        city=vendor_addr.get("city"),
        state=vendor_addr.get("state"),
        postal_code=vendor_addr.get("postal_code"),
        country=vendor_addr.get("country"),
    )
    vendor_address_id = vendor_address_row["id"] if vendor_address_row else None

    client_addr = client_data.get("address", {})
    client_address_row = get_or_create_address(
        db,
        company_id,
        street=client_addr.get("street"),
        city=client_addr.get("city"),
        state=client_addr.get("state"),
        postal_code=client_addr.get("postal_code"),
        country=client_addr.get("country"),
    )
    client_address_id = client_address_row["id"] if client_address_row else None

    # --- Vendor ---
    vendor_row = get_or_create_vendor(
        db,
        company_id,
        name=vendor_data.get("name", "Unknown Vendor"),
        tax_id=vendor_data.get("tax_id") or "N/A",
        email=vendor_data.get("email"),
        phone=vendor_data.get("phone"),
    )
    vendor_id = vendor_row["id"]

    # --- Client ---
    client_row = get_or_create_client(
        db,
        company_id,
        name=client_data.get("name", "Unknown Client"),
        tax_id=client_data.get("tax_id") or "N/A",
        email=client_data.get("email"),
        phone=client_data.get("phone"),
    )
    client_id = client_row["id"]

    # --- Invoice ---
    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number", f"UPLOAD-{filename}")

    # Check if already exists — return existing instead of crashing
    existing = db.table("invoices").select("id")\
        .eq("company_id", company_id)\
        .eq("invoice_number", invoice_number)\
        .execute()

    if existing.data:
        invoice_id = existing.data[0]["id"]
        log.info(f"Invoice already exists: {invoice_id} ({invoice_number})")
        return {
            "invoice_id":        invoice_id,
            "invoice_number":    invoice_number,
            "confidence_score":  confidence,
            "vendor":            vendor_data.get("name", "Unknown"),
            "client":            client_data.get("name", "Unknown"),
            "grand_total":       inv.get("grand_total", 0),
            "line_items_count":  0,
            "embeddings_stored": 0,
            "status":            "already_exists",
            "message":           f"Invoice {invoice_number} already in database",
        }

    invoice_result = db.table("invoices").insert({
        "company_id":        company_id,
        "invoice_number":    invoice_number,
        "issue_date":        inv.get("issue_date") or "1900-01-01",
        "due_date":          inv.get("due_date"),
        "currency":          inv.get("currency", "USD"),
        "tax_percent":       inv.get("tax_percent", 0),
        "subtotal":          inv.get("subtotal", 0),
        "total_tax":         inv.get("total_tax", 0),
        "grand_total":       inv.get("grand_total", 0),
        "payment_method":    inv.get("payment_method"),
        "description":       inv.get("description"),
        "discount":          inv.get("discount", 0),
        "status":            "draft",
        "vendor_id":         vendor_id,
        "client_id":         client_id,
        "vendor_address_id": vendor_address_id,
        "client_address_id": client_address_id,
        "confidence_score":  confidence,
    }).execute()

    invoice_id = invoice_result.data[0]["id"]

    # --- Line items ---
    line_items = extraction.get("line_items", [])
    if line_items:
        rows = [{
            "company_id":    company_id,
            "invoice_id":    invoice_id,
            "description":   item.get("description", ""),
            "quantity":      item.get("quantity", 1),
            "unit_price":    item.get("unit_price", 0),
            "line_subtotal": item.get("line_subtotal", 0),
            "discount":      item.get("discount", 0),
        } for item in line_items]
        db.table("line_items").insert(rows).execute()

    # --- Payments ---
    payments = extraction.get("payments", [])
    if payments:
        payment_rows = [{
            "company_id":   company_id,
            "invoice_id":   invoice_id,
            "payment_date": p.get("payment_date"),
            "amount":       p.get("amount", 0),
            "method":       p.get("method"),
            "reference":    p.get("reference"),
        } for p in payments if p.get("payment_date")]
        if payment_rows:
            db.table("payments").insert(payment_rows).execute()

    # --- Raw document (audit trail) ---
    db.table("invoice_raw_documents").insert({
        "company_id":      company_id,
        "invoice_id":      invoice_id,
        "raw_text":        raw_text,
        "extraction_json": extraction,
        "schema_version":  "1.0",
        "storage_path":    storage_path,

    }).execute()

    log.info(f"Invoice stored: {invoice_id} ({invoice_number})")

    # ------------------------------------------------------------------
    # Step 4: Generate embeddings - store in pgvector
    # ------------------------------------------------------------------
    try:
        embed_count = generate_and_store_embeddings(
            db, company_id, invoice_id, raw_text, extraction
        )
    except Exception as e:
        log.error(f"Embedding generation failed for {invoice_id}: {e}")
        embed_count = 0

    # ------------------------------------------------------------------
    # Return summary
    # ------------------------------------------------------------------
    return {
        "invoice_id":        invoice_id,
        "invoice_number":    invoice_number,
        "confidence_score":  confidence,
        "vendor":            vendor_data.get("name", "Unknown"),
        "client":            client_data.get("name", "Unknown"),
        "grand_total":       inv.get("grand_total", 0),
        "line_items_count":  len(line_items),
        "embeddings_stored": embed_count,
    }