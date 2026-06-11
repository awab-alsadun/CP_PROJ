"""
Invoice Processing Pipeline (Payable-only)
------------------------------------------
Full ingestion flow: file bytes -> structured payable invoice in Supabase.

Pipeline stages (all logged at DEBUG under app.services.invoice_processor):
  1. OCR         - extract text from image or PDF
  2. LLM         - raw text -> structured JSON extraction
  3. Vendor      - resolve / auto-create vendor + address
  4. Duplicate   - guard before DB insert
  5. DB write    - invoice / line_items / payments / raw_doc
  6. PDF storage - upload canonical PDF to private "invoices" bucket
  7. Embeddings  - generate and store pgvector chunks
  8. Compliance  - run validation checks
  9. Notify      - upload notification

Receivables are NOT created here. They are created via
POST /api/v1/invoices (structured form input).
"""

import logging
import time

from supabase import Client

from app.services.ocr_service import extract_text_from_image, extract_text_from_pdf
from app.services.extraction_service import extract_structured_data
from app.services.embedding_service import generate_and_store_embeddings
from app.services.vendor_service import get_or_create_vendor
from app.services.address_service import get_or_create_address
from app.services.storage_service import upload_invoice_pdf
from app.services.notification_service import create_notification

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stage(tag: str, invoice_number: str, **kwargs) -> None:
    """Emit a structured DEBUG line with a stage tag and invoice context."""
    parts = [f"stage={tag}", f"invoice={invoice_number!r}"]
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    log.debug("  ".join(parts))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_invoice(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Full pipeline: file bytes -> payable invoice in Supabase.

    Returns dict with invoice_id, summary fields, and status.
    Raises ValueError on OCR failure or unsupported file type.
    """
    tag = filename   # replaced with invoice_number after LLM extraction

    # ------------------------------------------------------------------
    # Stage 1: OCR
    # ------------------------------------------------------------------
    _stage("ocr_start", tag, filename=filename, size_bytes=len(file_bytes))
    t0 = time.monotonic()

    lower = filename.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
        raw_text = extract_text_from_image(file_bytes)
    elif lower.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not raw_text.strip():
        raise ValueError(f"OCR extracted no text from {filename}")

    _stage("ocr_done", tag,
           duration_s=round(time.monotonic() - t0, 3),
           chars=len(raw_text))

    # ------------------------------------------------------------------
    # Stage 1b: Prepare canonical PDF bytes for storage
    # PDFs go as-is. Images are converted once here.
    # ------------------------------------------------------------------
    canonical_pdf_bytes: bytes | None = None
    if lower.endswith(".pdf"):
        canonical_pdf_bytes = file_bytes
    else:
        try:
            import img2pdf
            canonical_pdf_bytes = img2pdf.convert(file_bytes)
        except Exception as e:
            log.error(f"stage=pdf_conversion_failed  invoice={tag!r}  error={e}")

    # ------------------------------------------------------------------
    # Stage 2: LLM extraction
    # ------------------------------------------------------------------
    _stage("llm_extract_start", tag)
    t2 = time.monotonic()

    extraction = extract_structured_data(raw_text)
    confidence = extraction.get("document_metadata", {}).get("confidence_score", 0.0)

    _stage("llm_extract_done", tag,
           duration_s=round(time.monotonic() - t2, 3),
           confidence=confidence)

    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number") or f"UPLOAD-{filename}"
    tag = invoice_number

    # ------------------------------------------------------------------
    # Stage 3: Vendor normalization
    # ------------------------------------------------------------------
    vendor_data = extraction.get("vendor", {})

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
    # Stage 4: Duplicate check
    # Key: (company_id, invoice_number, vendor_id).
    # Two different vendors can legitimately use the same invoice_number.
    # ------------------------------------------------------------------
    existing = (
        db.table("invoices").select("id")
        .eq("company_id", company_id)
        .eq("invoice_number", invoice_number)
        .eq("vendor_id", vendor_id)
        .execute()
    )

    if existing.data:
        existing_id = existing.data[0]["id"]
        log.warning(
            f"stage=duplicate_detected  invoice={tag!r}  existing_id={existing_id}"
        )
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": existing_id,
                "flag_type":  "duplicate_invoice",
                "severity":   "high",
                "reason":     f"Duplicate upload: payable invoice "
                              f"{invoice_number} already exists",
            }).execute()
        except Exception as e:
            log.error(f"stage=compliance_flag_failed  invoice={tag!r}  error={e}")

        try:
            create_notification(
                db, company_id,
                type="compliance",
                title="Duplicate invoice detected",
                message=(
                    f"Payable invoice {invoice_number} "
                    f"from {vendor_data.get('name') or 'Unknown'} already exists."
                ),
                related_invoice_id=existing_id,
            )
        except Exception as e:
            log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

        return {
            "invoice_id":        existing_id,
            "invoice_number":    invoice_number,
            "status":            "duplicate",
            "confidence_score":  confidence,
            "vendor":            vendor_data.get("name"),
            "grand_total":       inv.get("grand_total", 0),
            "line_items_count":  0,
            "embeddings_stored": 0,
            "message":           f"Invoice {invoice_number} already exists",
        }

    # ------------------------------------------------------------------
    # Stage 5: DB write
    # ------------------------------------------------------------------
    _stage("db_write_start", tag, vendor=vendor_data.get("name"))
    t3 = time.monotonic()

    invoice_result = db.table("invoices").insert({
        "company_id":         company_id,
        "invoice_number":     invoice_number,
        "invoice_type":       "payable",
        "status":             "unpaid",
        "issue_date":         inv.get("issue_date") or "1900-01-01",
        "due_date":           inv.get("due_date"),
        "currency":           inv.get("currency", "USD"),
        "tax_percent":        inv.get("tax_percent", 0),
        "subtotal":           inv.get("subtotal", 0),
        "total_tax":          inv.get("total_tax", 0),
        "grand_total":        inv.get("grand_total", 0),
        "payment_method":     inv.get("payment_method"),
        "description":        inv.get("description"),
        "discount":           inv.get("discount", 0),
        "vendor_id":          vendor_id,
        "vendor_address_id":  vendor_address_id,
        "confidence_score":   confidence,
        "amount_paid_so_far": 0,
    }).execute()

    invoice_id = invoice_result.data[0]["id"]

    # Line items
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

    # Payments from document
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

    # Raw document — storage_path filled in after upload
    raw_doc_result = db.table("invoice_raw_documents").insert({
        "company_id":      company_id,
        "invoice_id":      invoice_id,
        "raw_text":        raw_text,
        "extraction_json": extraction,
        "schema_version":  "1.0",
        "storage_path":    None,
    }).execute()

    raw_doc_id = raw_doc_result.data[0]["id"] if raw_doc_result.data else None

    _stage("db_write_done", tag,
           invoice_id=invoice_id,
           line_items=len(line_items),
           duration_s=round(time.monotonic() - t3, 3))

    # ------------------------------------------------------------------
    # Stage 6: PDF upload to private "invoices" bucket
    # Storage path: {company_id}/{invoice_id}.pdf
    # ------------------------------------------------------------------
    storage_path = None
    if canonical_pdf_bytes:
        _stage("storage_upload_start", tag, invoice_id=invoice_id, bucket="invoices")
        t4 = time.monotonic()
        try:
            storage_path = upload_invoice_pdf(
                db, company_id, invoice_id, canonical_pdf_bytes
            )
            if raw_doc_id:
                db.table("invoice_raw_documents").update({
                    "storage_path": storage_path,
                }).eq("id", raw_doc_id).execute()
            _stage("storage_upload_done", tag,
                   path=storage_path,
                   duration_s=round(time.monotonic() - t4, 3))
        except Exception as e:
            log.error(
                f"stage=storage_upload_failed  invoice={tag!r}  "
                f"invoice_id={invoice_id}  error={e}"
            )
            try:
                db.table("compliance_flags").insert({
                    "company_id": company_id,
                    "invoice_id": invoice_id,
                    "flag_type":  "storage_upload_failed",
                    "severity":   "medium",
                    "reason":     f"PDF upload to private storage failed: {e}",
                }).execute()
            except Exception as flag_err:
                log.error(
                    f"stage=compliance_flag_failed  invoice={tag!r}  "
                    f"error={flag_err}"
                )
    else:
        log.warning(
            f"stage=storage_upload_skipped  invoice={tag!r}  "
            f"reason=no_canonical_pdf_bytes"
        )

    # ------------------------------------------------------------------
    # Stage 7: Embeddings
    # ------------------------------------------------------------------
    _stage("embedding_start", tag, invoice_id=invoice_id)
    t5 = time.monotonic()
    embed_count = 0
    try:
        embed_count = generate_and_store_embeddings(
            db, company_id, invoice_id, raw_text, extraction
        )
        _stage("embedding_done", tag,
               chunks=embed_count,
               duration_s=round(time.monotonic() - t5, 3))
    except Exception as e:
        log.error(
            f"stage=embedding_failed  invoice={tag!r}  "
            f"invoice_id={invoice_id}  error={e}"
        )

    # ------------------------------------------------------------------
    # Stage 8: Compliance
    # ------------------------------------------------------------------
    flag_count = 0
    try:
        from app.services.compliance_service import validate_invoice_compliance
        result = validate_invoice_compliance(db, company_id, invoice_id)
        flag_count = result.get("inserted", 0)
        _stage("compliance_check_done", tag,
               flags_inserted=flag_count,
               flags_resolved=result.get("resolved", 0))
    except Exception as e:
        log.error(
            f"stage=compliance_failed  invoice={tag!r}  "
            f"invoice_id={invoice_id}  error={e}"
        )

    # ------------------------------------------------------------------
    # Stage 9: Notification
    # ------------------------------------------------------------------
    try:
        confidence_pct = int(float(confidence) * 100) if confidence else 0
        create_notification(
            db, company_id,
            type="upload",
            title="Invoice extracted",
            message=(
                f"Payable invoice {invoice_number} "
                f"from {vendor_data.get('name', 'Unknown')} extracted successfully "
                f"(confidence: {confidence_pct}%)"
            ),
            related_invoice_id=invoice_id,
        )
    except Exception as e:
        log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

    log.info(
        f"pipeline_complete  invoice={tag!r}  invoice_id={invoice_id}  "
        f"vendor={vendor_data.get('name')!r}  "
        f"grand_total={inv.get('grand_total', 0)}  "
        f"confidence={confidence}  embeddings={embed_count}  "
        f"flags={flag_count}  storage_path={storage_path!r}"
    )

    return {
        "invoice_id":        invoice_id,
        "invoice_number":    invoice_number,
        "status":            "unpaid",
        "confidence_score":  confidence,
        "vendor":            vendor_data.get("name"),
        "grand_total":       inv.get("grand_total", 0),
        "line_items_count":  len(line_items),
        "embeddings_stored": embed_count,
        "storage_path":      storage_path,
    }