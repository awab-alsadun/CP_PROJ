"""
Invoice Processing Pipeline (Payable + Receivable)
--------------------------------------------------
file bytes -> structured invoice in Supabase.

Stages:
  1.  OCR              -> raw_text + ocr_used_fallback
  1b. PDF prep         -> canonical_pdf_bytes
  2.  LLM extraction   -> (extraction, extraction_signals, had_retry)
  2b. Compose signals  -> OCR signals + extraction signals
  2c. Compute conf.    -> confidence in [0,1]
  3.  Entity normalize -> vendor upsert by name (payable) — with self-invoice guard
                         client upsert by name (receivable)
  4.  Duplicate guard  -> reject OCR duplicates
  5.  DB write         -> invoice (with confidence_score), line_items,
                          payments, raw_doc
  6.  PDF storage      -> {company_id}/{company_name} - {invoice_number}.pdf
  7.  Embeddings
  8a. Compliance Phase A (flags from signals)
  8b. Compliance Phase B (cross-row checks)
  9.  Notification
"""

import logging
import re
import time

from supabase import Client

from app.services.ocr_service import extract_text_from_image, extract_text_from_pdf
from app.services.extraction_service import (
    extract_structured_data,
    compute_confidence,
)
from app.services.embedding_service import generate_and_store_embeddings
from app.services.vendor_service import get_or_create_vendor_by_name
from app.services.client_service import get_or_create_client_by_name
from app.services.address_service import get_or_create_address
from app.services.storage_service import upload_invoice_pdf
from app.services.notification_service import create_notification
from app.services import compliance_service

log = logging.getLogger(__name__)

OCR_LOW_QUALITY_THRESHOLD = 400

_PATH_UNSAFE_RE = re.compile(r'[\\/:*?"<>|\x00-\x1F]')
_company_name_cache: dict[str, str] = {}


def _stage(tag: str, invoice_number: str, **kwargs) -> None:
    parts = [f"stage={tag}", f"invoice={invoice_number!r}"]
    for k, v in kwargs.items():
        parts.append(f"{k}={v}")
    log.debug("  ".join(parts))


def _fetch_company_name(db: Client, company_id: str) -> str:
    cached = _company_name_cache.get(company_id)
    if cached is not None:
        return cached
    try:
        r = (db.table("companies").select("name")
             .eq("id", company_id).single().execute())
        name = (r.data or {}).get("name") or "Company"
    except Exception as e:
        log.error(f"company_name_lookup_failed  company_id={company_id}  error={e}")
        name = "Company"
    _company_name_cache[company_id] = name
    return name


def _sanitize_for_path(text: str) -> str:
    cleaned = _PATH_UNSAFE_RE.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Untitled"


def _build_storage_path(db: Client, company_id: str, invoice_number: str) -> str:
    company_name = _sanitize_for_path(_fetch_company_name(db, company_id))
    inv_clean = _sanitize_for_path(invoice_number)
    return f"{company_id}/{company_name} - {inv_clean}.pdf"


def process_invoice(
    db: Client,
    company_id: str,
    file_bytes: bytes,
    filename: str,
    invoice_type: str = "payable",
) -> dict:
    if invoice_type not in ("payable", "receivable"):
        raise ValueError(
            f"invoice_type must be 'payable' or 'receivable', got {invoice_type!r}"
        )

    tag = filename

    # -------- Stage 1: OCR --------
    _stage("ocr_start", tag,
           filename=filename, invoice_type=invoice_type,
           size_bytes=len(file_bytes))
    t0 = time.monotonic()

    lower = filename.lower()
    ocr_used_fallback = False

    if lower.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff")):
        raw_text = extract_text_from_image(file_bytes)
    elif lower.endswith(".pdf"):
        raw_text, ocr_used_fallback = extract_text_from_pdf(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not raw_text.strip():
        raise ValueError(f"OCR extracted no text from {filename}")

    _stage("ocr_done", tag,
           duration_s=round(time.monotonic() - t0, 3),
           chars=len(raw_text),
           tesseract_fallback=ocr_used_fallback)

    # -------- Stage 1b: Canonical PDF --------
    canonical_pdf_bytes: bytes | None = None
    if lower.endswith(".pdf"):
        canonical_pdf_bytes = file_bytes
    else:
        try:
            import img2pdf
            canonical_pdf_bytes = img2pdf.convert(file_bytes)
        except Exception as e:
            log.error(f"stage=pdf_conversion_failed  invoice={tag!r}  error={e}")

    # -------- Stage 2: LLM extraction --------
    _stage("llm_extract_start", tag)
    t2 = time.monotonic()

    extraction, extraction_signals, had_retry = extract_structured_data(raw_text)

    _stage("llm_extract_done", tag,
           duration_s=round(time.monotonic() - t2, 3),
           extraction_signals=len(extraction_signals),
           had_retry=had_retry)

    inv = extraction.get("invoice", {})
    invoice_number = inv.get("invoice_number") or f"UPLOAD-{filename}"
    tag = invoice_number

    # -------- Stage 2b: OCR signals + combine --------
    all_signals: list[dict] = list(extraction_signals)

    if len(raw_text) < OCR_LOW_QUALITY_THRESHOLD:
        all_signals.append({
            "flag_type": "ocr_low_quality",
            "severity":  "high",
            "reason":    f"OCR returned only {len(raw_text)} characters — likely scan failure",
        })

    if ocr_used_fallback:
        all_signals.append({
            "flag_type": "ocr_fallback_used",
            "severity":  "medium",
            "reason":    "PyMuPDF failed, Tesseract fallback used",
        })

    # -------- Stage 2c: Confidence --------
    confidence = compute_confidence(all_signals)
    _stage("confidence_computed", tag,
           signals=len(all_signals), confidence=confidence)

    # -------- Stage 3: Entity normalization (name-based upsert) --------
    vendor_id = None
    vendor_address_id = None
    client_id = None
    client_address_id = None
    entity_name_for_log = None
    unmatched_client = False
    self_invoice_detected = False

    if invoice_type == "payable":
        vendor_data = extraction.get("vendor", {}) or {}
        vendor_addr = vendor_data.get("address", {}) or {}
        extracted_vendor_name = (vendor_data.get("name") or "").strip()

        # Self-invoice guard: if LLM extracted our own company name as the vendor,
        # it misread the "Bill To" section. Do not upsert — flag it after DB write.
        company_name = _fetch_company_name(db, company_id)
        if extracted_vendor_name.lower() == company_name.strip().lower():
            self_invoice_detected = True
            log.warning(
                f"stage=self_invoice_detected  invoice={tag!r}  "
                f"extracted_vendor={extracted_vendor_name!r}  "
                f"company_name={company_name!r}"
            )
        else:
            vendor_row = get_or_create_vendor_by_name(
                db, company_id,
                name=extracted_vendor_name or "Unknown Vendor",
                tax_id=vendor_data.get("tax_id") or "N/A",
                email=vendor_data.get("email"),
                phone=vendor_data.get("phone"),
            )
            vendor_id = vendor_row["id"]
            entity_name_for_log = vendor_row.get("name")

            vendor_address_row = get_or_create_address(
                db, company_id,
                street=vendor_addr.get("street"),
                city=vendor_addr.get("city"),
                state=vendor_addr.get("state"),
                postal_code=vendor_addr.get("postal_code"),
                country=vendor_addr.get("country"),
                vendor_id=vendor_id,
            )
            vendor_address_id = vendor_address_row["id"] if vendor_address_row else None

        status_default = "unpaid"

    else:  # receivable
        client_data = extraction.get("client", {}) or {}
        extracted_name = (client_data.get("name") or "").strip()

        if extracted_name:
            client_row = get_or_create_client_by_name(
                db, company_id,
                name=extracted_name,
                tax_id=client_data.get("tax_id") or "N/A",
                email=client_data.get("email"),
                phone=client_data.get("phone"),
            )
            client_id = client_row["id"]
            entity_name_for_log = client_row.get("name")
            _stage("client_upsert", tag,
                   client_id=client_id, name=entity_name_for_log)
        else:
            unmatched_client = True
            entity_name_for_log = "Unknown"
            _stage("client_name_missing", tag)

        status_default = "sent"

    # -------- Stage 4: Duplicate check --------
    dup_query = (db.table("invoices").select("id")
                 .eq("company_id", company_id)
                 .eq("invoice_number", invoice_number)
                 .eq("invoice_type", invoice_type))
    if invoice_type == "payable":
        dup_query = dup_query.eq("vendor_id", vendor_id)

    existing = dup_query.execute()

    if existing.data:
        existing_id = existing.data[0]["id"]
        log.warning(
            f"stage=duplicate_detected  invoice={tag!r}  "
            f"invoice_type={invoice_type}  existing_id={existing_id}"
        )
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": existing_id,
                "flag_type":  "duplicate_invoice_number",
                "severity":   "high",
                "reason":     f"Duplicate upload: {invoice_type} invoice "
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
                    f"{invoice_type.capitalize()} invoice {invoice_number} "
                    f"from {entity_name_for_log or 'Unknown'} already exists."
                ),
                related_invoice_id=existing_id,
            )
        except Exception as e:
            log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

        return {
            "invoice_id":        existing_id,
            "invoice_number":    invoice_number,
            "invoice_type":      invoice_type,
            "status":            "duplicate",
            "confidence_score":  confidence,
            "entity":            entity_name_for_log,
            "grand_total":       inv.get("grand_total", 0),
            "line_items_count":  0,
            "embeddings_stored": 0,
            "message":           f"Invoice {invoice_number} already exists",
        }

    # -------- Stage 5: DB write --------
    _stage("db_write_start", tag,
           invoice_type=invoice_type, entity=entity_name_for_log)
    t3 = time.monotonic()

    invoice_result = db.table("invoices").insert({
        "company_id":         company_id,
        "invoice_number":     invoice_number,
        "invoice_type":       invoice_type,
        "status":             status_default,
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
        "client_id":          client_id,
        "client_address_id":  client_address_id,
        "confidence_score":   confidence,
        "amount_paid_so_far": 0,
    }).execute()

    invoice_id = invoice_result.data[0]["id"]

    # Self-invoice flag (payable only — inserted here because invoice_id now exists)
    if self_invoice_detected:
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": invoice_id,
                "flag_type":  "self_invoice_vendor",
                "severity":   "medium",
                "reason":     "Extracted vendor name matches company name — likely OCR misread",
            }).execute()
        except Exception as e:
            log.error(f"stage=compliance_flag_failed  invoice={tag!r}  error={e}")

    # Unmatched client flag (receivable only — when extracted name was empty)
    if invoice_type == "receivable" and unmatched_client:
        try:
            db.table("compliance_flags").insert({
                "company_id": company_id,
                "invoice_id": invoice_id,
                "flag_type":  "unmatched_client",
                "severity":   "medium",
                "reason":     "No client name extracted from document. Invoice unlinked.",
            }).execute()
        except Exception as e:
            log.error(f"stage=compliance_flag_failed  invoice={tag!r}  error={e}")

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

    # Payments
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

    _stage("db_write_done", tag,
           invoice_id=invoice_id, line_items=len(line_items),
           duration_s=round(time.monotonic() - t3, 3))

    # -------- Stage 6: PDF upload --------
    storage_path = None
    if canonical_pdf_bytes:
        target_path = _build_storage_path(db, company_id, invoice_number)
        _stage("storage_upload_start", tag,
               invoice_id=invoice_id, bucket="invoices", path=target_path)
        t4 = time.monotonic()
        try:
            storage_path = upload_invoice_pdf(
                db, company_id, invoice_id, canonical_pdf_bytes,
                storage_path=target_path,
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
                    f"stage=compliance_flag_failed  invoice={tag!r}  error={flag_err}"
                )
    else:
        log.warning(
            f"stage=storage_upload_skipped  invoice={tag!r}  "
            f"reason=no_canonical_pdf_bytes"
        )

    # -------- Stage 7: Embeddings --------
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
        log.error(f"stage=embedding_failed  invoice={tag!r}  error={e}")

    # -------- Stage 8a: Compliance Phase A --------
    try:
        phase_a_result = compliance_service.write_phase_a_flags(
            db, company_id, invoice_id, all_signals, confidence,
        )
        _stage("compliance_phase_a_done", tag,
               flags=phase_a_result.get("phase_a_flags", 0))
    except Exception as e:
        log.error(f"stage=compliance_phase_a_failed  invoice={tag!r}  error={e}")

    # -------- Stage 8b: Compliance Phase B --------
    flag_count_b = 0
    try:
        phase_b_result = compliance_service.run_phase_b_checks(
            db, company_id, invoice_id,
        )
        flag_count_b = phase_b_result.get("phase_b_flags", 0)
        _stage("compliance_phase_b_done", tag, flags=flag_count_b)
    except Exception as e:
        log.error(f"stage=compliance_phase_b_failed  invoice={tag!r}  error={e}")

    # -------- Stage 9: Notification --------
    try:
        confidence_pct = int(confidence * 100)
        create_notification(
            db, company_id,
            type="upload",
            title="Invoice extracted",
            message=(
                f"{invoice_type.capitalize()} invoice {invoice_number} "
                f"from {entity_name_for_log or 'Unknown'} extracted successfully "
                f"(confidence: {confidence_pct}%)"
            ),
            related_invoice_id=invoice_id,
        )
    except Exception as e:
        log.error(f"stage=notification_failed  invoice={tag!r}  error={e}")

    log.info(
        f"pipeline_complete  invoice={tag!r}  invoice_id={invoice_id}  "
        f"invoice_type={invoice_type}  entity={entity_name_for_log!r}  "
        f"grand_total={inv.get('grand_total', 0)}  "
        f"confidence={confidence}  embeddings={embed_count}  "
        f"phase_b_flags={flag_count_b}  storage_path={storage_path!r}"
    )

    return {
        "invoice_id":        invoice_id,
        "invoice_number":    invoice_number,
        "invoice_type":      invoice_type,
        "status":            status_default,
        "confidence_score":  confidence,
        "entity":            entity_name_for_log,
        "grand_total":       inv.get("grand_total", 0),
        "line_items_count":  len(line_items),
        "embeddings_stored": embed_count,
        "storage_path":      storage_path,
    }