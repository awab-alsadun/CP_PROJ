"""
Invoice Processing Pipeline (Payable-only)
------------------------------------------
Full ingestion flow: file bytes -> structured payable invoice in Supabase.

Vendor resolution: MATCH ONLY — never auto-creates vendors.
If no vendor match found (by name ilike OR tax_id exact):
  - Invoice inserted with vendor_id = NULL
  - compliance_flag: unmatched_vendor (high)
  - notification: vendor not found, with invoice_number so user can
    manually create the vendor then re-upload
"""

import logging
import re
import time

from supabase import Client

from app.services.ocr_service import extract_text_from_image, extract_text_from_pdf
from app.services.extraction_service import extract_structured_data
from app.services.embedding_service import generate_and_store_embeddings
from app.services.address_service import get_or_create_address
from app.services.storage_service import upload_invoice_pdf
from app.services.notification_service import create_notification

log = logging.getLogger(__name__)

_company_name_cache: dict[str, str] = {}


def _stage(tag: str, invoice_number: str, **kwargs) -> None:
    parts = [f"stage={tag}", f"invoice={invoice_number!r}"]
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    log.debug("  ".join(parts))


def _sanitize_for_path(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _fetch_company_name(db: Client, company_id: str) -> str:
    if company_id in _company_name_cache:
        return _company_name_cache[company_id]
    try:
        result = db.table("companies").select("name").eq("id", company_id).single().execute()
        name = (result.data or {}).get("name", "Company")
    except Exception:
        name = "Company"
    _company_name_cache[company_id] = name
    return name


def _build_storage_path(db: Client, company_id: str, invoice_number: str) -> str:
    company_name = _fetch_company_name(db, company_id)
    safe_company = _sanitize_for_path(company_name)
    safe_number  = _sanitize_for_path(invoice_number)
    return f"{company_id}/{safe_company} - {safe_number}.pdf"


def _match_vendor(db: Client, company_id: str, name: str, tax_id: str) -> dict | None:
    """
    Try to match an existing vendor by tax_id (exact) or name (ilike).
    Returns the vendor row or None — never creates.
    """
    # 1. Exact tax_id match (most reliable)
    if tax_id and tax_id != "N/A":
        try:
            result = (
                db.table("vendors")
                .select("*")
                .eq("company_id", company_id)
                .eq("tax_id", tax_id)
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            log.warning(f"vendor tax_id match failed: {e}")

    # 2. Name ilike match
    if name and name != "Unknown Vendor":
        try:
            result = (
                db.table("vendors")
                .select("*")
                .eq("company_id", company_id)
                .ilike("name", f"%{name}%")
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            log.warning(f"vendor name match failed: {e}")

    return None


def process_invoice(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
) -> dict:
    tag = filename

    # Stage 1: OCR
    _stage("ocr_start", tag, filename=filename, size_bytes=len(file_bytes))
    t0 = time.monotonic()

    lower = filename.lower()
    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
        raw_text, used_fallback = extract_text_from_image(file_bytes), False
    elif lower.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_bytes)
        used_fallback = False
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not raw_text.strip():
        raise ValueError(f"OCR extracted no text from {filename}")

    _stage("ocr_done", tag, duration_s=round(time.monotonic() - t0, 3), chars=len(raw_text))

    # Stage 1b: canonical PDF
    canonical_pdf_bytes: bytes | None = None
    if lower.endswith(".pdf"):
        canonical_pdf_bytes = file_bytes
    else:
        try:
            import img2pdf
            canonical_pdf_bytes = img2pdf.convert(file_bytes)
        except Exception as e:
            log.error(f"stage=pdf_conversion_failed  invoice={tag!r}  error={e}")

    # Stage 2: LLM extraction
    _stage("llm_extract_start", tag)
    t2 = time.monotonic()

    extraction = extract_structured_data(raw_text)

    all_signals = []
    if len(raw_text) < 400:
        all_signals.append({"flag_type": "ocr_low_quality", "severity": "high",
                        "reason": f"OCR text length {len(raw_text)} < 400 chars"})
    if used_fallback:
        all_signals.append({"flag_type": "ocr_fallback_used", "severity": "medium",
                        "reason": "Tesseract fallback used for PDF text extraction"})

    confidence = 0.85

    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number") or f"UPLOAD-{filename}"
    tag = invoice_number

    _stage("llm_extract_done", tag, duration_s=round(time.monotonic() - t2, 3), confidence=confidence)

    # Stage 3: Vendor resolution — MATCH ONLY, never auto-create
    vendor_data = extraction.get("vendor", {})
    vendor_name = vendor_data.get("name", "Unknown Vendor")
    vendor_tax_id = vendor_data.get("tax_id") or "N/A"

    vendor_row = _match_vendor(db, company_id, vendor_name, vendor_tax_id)
    vendor_id  = vendor_row["id"] if vendor_row else None

    vendor_address_id = None
    if vendor_row:
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

    # Stage 4: Duplicate check
    dup_query = (
        db.table("invoices").select("id")
        .eq("company_id", company_id)
        .eq("invoice_number", invoice_number)
        .eq("invoice_type", "payable")
    )
    if vendor_id:
        dup_query = dup_query.eq("vendor_id", vendor_id)

    existing = dup_query.execute()

    if existing.data:
        existing_id = existing.data[0]["id"]
        log.warning(f"stage=duplicate_detected  invoice={tag!r}  existing_id={existing_id}")
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": existing_id,
                "flag_type":  "duplicate_invoice_number",
                "severity":   "high",
                "reason":     f"Duplicate upload: payable invoice {invoice_number} already exists",
            }).execute()
        except Exception as e:
            log.error(f"stage=compliance_flag_failed  invoice={tag!r}  error={e}")

        try:
            create_notification(
                db, company_id,
                type="compliance",
                title="Duplicate invoice detected",
                message=f"Payable invoice {invoice_number} from {vendor_name} already exists.",
                related_invoice_id=existing_id,
            )
        except Exception as e:
            log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

        return {
            "invoice_id":        existing_id,
            "invoice_number":    invoice_number,
            "status":            "duplicate",
            "confidence_score":  confidence,
            "vendor":            vendor_name,
            "grand_total":       inv.get("grand_total", 0),
            "line_items_count":  0,
            "embeddings_stored": 0,
            "message":           f"Invoice {invoice_number} already exists",
        }

    # Stage 5: DB write
    _stage("db_write_start", tag, vendor=vendor_name)
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
        "vendor_id":          vendor_id,          # NULL if unmatched
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

    # Raw document
    raw_doc_result = db.table("invoice_raw_documents").insert({
        "company_id":      company_id,
        "invoice_id":      invoice_id,
        "raw_text":        raw_text,
        "extraction_json": extraction,
        "schema_version":  "1.0",
        "storage_path":    None,
    }).execute()
    raw_doc_id = raw_doc_result.data[0]["id"] if raw_doc_result.data else None

    _stage("db_write_done", tag, invoice_id=invoice_id,
           line_items=len(line_items), duration_s=round(time.monotonic() - t3, 3))

    # Stage 5b: Unmatched vendor flag + notification
    if vendor_id is None:
        log.warning(f"stage=unmatched_vendor  invoice={tag!r}  vendor_name={vendor_name!r}  tax_id={vendor_tax_id!r}")
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": invoice_id,
                "flag_type":  "unmatched_vendor",
                "severity":   "high",
                "reason":     (
                    f"Vendor '{vendor_name}' (tax_id: {vendor_tax_id}) not found in database. "
                    f"Create the vendor manually, then re-upload invoice {invoice_number}."
                ),
            }).execute()
        except Exception as e:
            log.error(f"unmatched_vendor compliance_flag failed: {e}")

        try:
            create_notification(
                db, company_id,
                type="compliance",
                title="Vendor not found",
                message=(
                    f"Invoice {invoice_number}: vendor '{vendor_name}' not found. "
                    f"Create this vendor first, then re-upload the invoice."
                ),
                related_invoice_id=invoice_id,
            )
        except Exception as e:
            log.error(f"unmatched_vendor notification failed: {e}")

    # Stage 6: PDF upload
    storage_path = None
    if canonical_pdf_bytes:
        _stage("storage_upload_start", tag, invoice_id=invoice_id, bucket="invoices")
        t4 = time.monotonic()
        try:
            target_path  = _build_storage_path(db, company_id, invoice_number)
            storage_path = upload_invoice_pdf(
                db, company_id, invoice_id, canonical_pdf_bytes,
                storage_path=target_path,
            )
            if raw_doc_id:
                db.table("invoice_raw_documents").update({
                    "storage_path": storage_path,
                }).eq("id", raw_doc_id).execute()
            _stage("storage_upload_done", tag, path=storage_path,
                   duration_s=round(time.monotonic() - t4, 3))
        except Exception as e:
            log.error(f"stage=storage_upload_failed  invoice={tag!r}  error={e}")
            try:
                db.table("compliance_flags").insert({
                    "company_id": company_id,
                    "invoice_id": invoice_id,
                    "flag_type":  "storage_upload_failed",
                    "severity":   "medium",
                    "reason":     f"PDF upload to private storage failed: {e}",
                }).execute()
            except Exception:
                pass
    else:
        log.warning(f"stage=storage_upload_skipped  invoice={tag!r}  reason=no_canonical_pdf_bytes")

    # Stage 7: Embeddings
    _stage("embedding_start", tag, invoice_id=invoice_id)
    t5 = time.monotonic()
    embed_count = 0
    try:
        embed_count = generate_and_store_embeddings(
            db, company_id, invoice_id, raw_text, extraction
        )
        _stage("embedding_done", tag, chunks=embed_count,
               duration_s=round(time.monotonic() - t5, 3))
    except Exception as e:
        log.error(f"stage=embedding_failed  invoice={tag!r}  invoice_id={invoice_id}  error={e}")

    # Stage 8: Compliance (Phase A + B)
    flag_count = 0
    try:
        from app.services.compliance_service import write_phase_a_flags, run_phase_b_checks
        write_phase_a_flags(db, company_id, invoice_id, all_signals, confidence)
        result = run_phase_b_checks(db, company_id, invoice_id)
        flag_count = result.get("inserted", 0) if isinstance(result, dict) else 0
        _stage("compliance_check_done", tag, flags_inserted=flag_count)
    except Exception as e:
        log.error(f"stage=compliance_failed  invoice={tag!r}  error={e}")

    # Stage 9: Upload notification (only if vendor matched)
    if vendor_id is not None:
        try:
            confidence_pct = int(float(confidence) * 100) if confidence else 0
            create_notification(
                db, company_id,
                type="upload",
                title="Invoice extracted",
                message=(
                    f"Payable invoice {invoice_number} from {vendor_name} "
                    f"extracted successfully (confidence: {confidence_pct}%)"
                ),
                related_invoice_id=invoice_id,
            )
        except Exception as e:
            log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

    log.info(
        f"pipeline_complete  invoice={tag!r}  invoice_id={invoice_id}  "
        f"vendor={vendor_name!r}  vendor_matched={vendor_id is not None}  "
        f"grand_total={inv.get('grand_total', 0)}  confidence={confidence}  "
        f"embeddings={embed_count}  flags={flag_count}  storage_path={storage_path!r}"
    )

    return {
        "invoice_id":        invoice_id,
        "invoice_number":    invoice_number,
        "status":            "unpaid",
        "confidence_score":  confidence,
        "vendor":            vendor_name,
        "vendor_matched":    vendor_id is not None,
        "grand_total":       inv.get("grand_total", 0),
        "line_items_count":  len(line_items),
        "embeddings_stored": embed_count,
        "storage_path":      storage_path,
        "unmatched_vendor":  vendor_id is None,
    }