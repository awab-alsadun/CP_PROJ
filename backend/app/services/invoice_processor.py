"""
Invoice Processing Pipeline
----------------------------
Full ingestion flow: file bytes → structured data in Supabase.

Pipeline:
  1. OCR         — extract text from image or PDF
  2. Storage     — upload original file to Supabase Storage
  3. LLM         — raw text → structured JSON extraction
  4. Duplicate   — check before inserting
  5. DB insert   — vendor / client / address / invoice / line_items / payments / raw_doc
  6. Embeddings  — generate and store pgvector chunks
  7. Compliance  — run validation checks, insert flags
  8. Notify      — upload notification

All uploaded invoices are treated as PAYABLE (inbound from vendor).
Receivable invoices are created manually via the API, not uploaded.
"""

import logging

from supabase import Client

from app.services.ocr_service import extract_text_from_image, extract_text_from_pdf
from app.services.extraction_service import extract_structured_data
from app.services.embedding_service import generate_and_store_embeddings
from app.services.vendor_service import get_or_create_vendor
from app.services.address_service import get_or_create_address
from app.services.storage_service import upload_to_storage
from app.services.notification_service import create_notification

log = logging.getLogger(__name__)


def process_invoice(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Full pipeline: file bytes → structured data in Supabase.

    Returns dict with invoice_id, summary fields, and status.
    Raises ValueError on OCR failure or unsupported file type.
    """

    # ------------------------------------------------------------------
    # Step 1: OCR
    # ------------------------------------------------------------------
    lower = filename.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
        raw_text = extract_text_from_image(file_bytes)
    elif lower.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not raw_text.strip():
        raise ValueError(f"OCR extracted no text from {filename}")

    log.info(f"OCR complete: {len(raw_text)} chars from {filename}")

    # ------------------------------------------------------------------
    # Step 2: Storage upload
    # ------------------------------------------------------------------
    storage_path = None
    try:
        storage_path = upload_to_storage(
            db, company_id, file_bytes, filename, invoice_number=None,
        )
        log.info(f"Storage: {storage_path}")
    except Exception as e:
        log.error(f"Storage upload failed for {filename}: {e}")

    # ------------------------------------------------------------------
    # Step 3: LLM extraction
    # ------------------------------------------------------------------
    extraction = extract_structured_data(raw_text)
    confidence = extraction.get("document_metadata", {}).get("confidence_score", 0.0)
    log.info(f"LLM extraction complete: confidence={confidence}")

    # ------------------------------------------------------------------
    # Step 4: Normalize entities
    # ------------------------------------------------------------------
    vendor_data = extraction.get("vendor", {})
    # client_data is present in the LLM output but ignored for payables —
    # the company itself is the implicit recipient, not stored as a client.

    vendor_addr = vendor_data.get("address", {})
    vendor_address_row = get_or_create_address(
        db, company_id,
        street=vendor_addr.get("street"),
        city=vendor_addr.get("city"),
        state=vendor_addr.get("state"),
        postal_code=vendor_addr.get("postal_code"),
        country=vendor_addr.get("country"),
    )
    vendor_address_id = vendor_address_row["id"] if vendor_address_row else None

    vendor_row = get_or_create_vendor(
        db, company_id,
        name=vendor_data.get("name", "Unknown Vendor"),
        tax_id=vendor_data.get("tax_id") or "N/A",
        email=vendor_data.get("email"),
        phone=vendor_data.get("phone"),
    )
    vendor_id = vendor_row["id"]

    # ------------------------------------------------------------------
    # Step 5: Duplicate check
    # ------------------------------------------------------------------
    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number") or f"UPLOAD-{filename}"

    existing = (
        db.table("invoices").select("id")
        .eq("company_id", company_id)
        .eq("invoice_number", invoice_number)
        .eq("vendor_id", vendor_id)
        .execute()
    )

    if existing.data:
        existing_id = existing.data[0]["id"]
        log.info(f"Duplicate invoice detected: {invoice_number} (existing: {existing_id})")

        # Insert compliance flag for duplicate
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": existing_id,
                "flag_type":  "duplicate_invoice",
                "severity":   "high",
                "reason":     f"Duplicate upload: invoice {invoice_number} already exists",
            }).execute()
        except Exception as e:
            log.error(f"Failed to insert duplicate compliance flag: {e}")

        try:
            create_notification(
                db, company_id,
                type="compliance",
                title="Duplicate invoice detected",
                message=f"Invoice {invoice_number} from {vendor_data.get('name', 'Unknown')} already exists in the system.",
                related_invoice_id=existing_id,
            )
        except Exception as e:
            log.error(f"Duplicate notification failed: {e}")

        return {
            "invoice_id":       existing_id,
            "invoice_number":   invoice_number,
            "confidence_score": confidence,
            "vendor":           vendor_data.get("name", "Unknown"),
            "client":           None,
            "grand_total":      inv.get("grand_total", 0),
            "line_items_count": 0,
            "embeddings_stored": 0,
            "status":           "duplicate",
            "message":          f"Invoice {invoice_number} already exists",
        }

    # ------------------------------------------------------------------
    # Step 6: Insert invoice — always payable, always unpaid, no client
    # ------------------------------------------------------------------
    invoice_result = db.table("invoices").insert({
        "company_id":        company_id,
        "invoice_number":    invoice_number,
        "invoice_type":      "payable",       # all uploads are payable
        "status":            "unpaid",         # payables start as unpaid
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
        "vendor_id":         vendor_id,
        "client_id":         None,            # payables have no client
        "vendor_address_id": vendor_address_id,
        "client_address_id": None,
        "confidence_score":  confidence,
        "amount_paid_so_far": 0,
    }).execute()

    invoice_id = invoice_result.data[0]["id"]
    log.info(f"Invoice inserted: {invoice_id} ({invoice_number})")

    # ------------------------------------------------------------------
    # Step 7: Line items
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Step 8: Payments extracted from document (rare but possible)
    # ------------------------------------------------------------------
    payments = extraction.get("payments", [])
    if payments:
        pay_rows = [{
            "company_id":   company_id,
            "invoice_id":   invoice_id,
            "payment_date": p.get("payment_date"),
            "amount":       p.get("amount", 0),
            "method":       p.get("method"),
            "reference":    p.get("reference"),
        } for p in payments if p.get("payment_date")]
        if pay_rows:
            db.table("payments").insert(pay_rows).execute()

    # ------------------------------------------------------------------
    # Step 9: Raw document (audit trail)
    # ------------------------------------------------------------------
    db.table("invoice_raw_documents").insert({
        "company_id":      company_id,
        "invoice_id":      invoice_id,
        "raw_text":        raw_text,
        "extraction_json": extraction,
        "schema_version":  "1.0",
        "storage_path":    storage_path,
    }).execute()

    # ------------------------------------------------------------------
    # Step 10: Embeddings
    # ------------------------------------------------------------------
    embed_count = 0
    try:
        embed_count = generate_and_store_embeddings(
            db, company_id, invoice_id, raw_text, extraction
        )
    except Exception as e:
        log.error(f"Embedding generation failed for {invoice_id}: {e}")

    # ------------------------------------------------------------------
    # Step 11: Compliance validation
    # ------------------------------------------------------------------
    try:
        from app.services.compliance_service import validate_invoice_compliance
        validate_invoice_compliance(db, company_id, invoice_id)
    except Exception as e:
        log.error(f"Compliance check failed for {invoice_id}: {e}")

    # ------------------------------------------------------------------
    # Step 12: Upload notification
    # ------------------------------------------------------------------
    try:
        confidence_pct = int(float(confidence) * 100) if confidence else 0
        create_notification(
            db, company_id,
            type="upload",
            title="Invoice extracted",
            message=(
                f"Invoice {invoice_number} from {vendor_data.get('name', 'Unknown')} "
                f"extracted successfully (confidence: {confidence_pct}%)"
            ),
            related_invoice_id=invoice_id,
        )
    except Exception as e:
        log.error(f"Upload notification failed: {e}")

    return {
        "invoice_id":        invoice_id,
        "invoice_number":    invoice_number,
        "invoice_type":      "payable",
        "status":            "unpaid",
        "confidence_score":  confidence,
        "vendor":            vendor_data.get("name", "Unknown"),
        "client":            None,
        "grand_total":       inv.get("grand_total", 0),
        "line_items_count":  len(line_items),
        "embeddings_stored": embed_count,
    }