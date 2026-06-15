"""
Upload Router
-------------
POST /api/v1/upload       — single file
POST /api/v1/upload/batch — multiple files (sequential, not concurrent)

TESTING MODE: invoice_type form field re-enabled. Receivables uploaded
this way bypass the canonical receivable form flow. Do not merge.

Logs every incoming request and every batch failure with full context.
"""

import logging
import time

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.services.invoice_processor import process_invoice

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
ALLOWED_INVOICE_TYPES = {"payable", "receivable"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

async def _process_single_upload(
    file: UploadFile,
    company_id: str,
    db: Client,
    invoice_type: str,
) -> dict:
    """
    Validate and process one UploadFile through the full pipeline.

    Returns a result dict: filename, status, invoice_id, invoice_number,
    error. Never raises — all exceptions caught and returned as failed
    results.
    """
    filename = file.filename or "unknown"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    # --- Validation ---
    if ext not in ALLOWED_EXTENSIONS:
        error = f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        log.warning(
            f"upload_rejected  filename={filename!r}  reason=unsupported_type  ext={ext}"
        )
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": error,
        }

    try:
        file_bytes = await file.read()
    except Exception as e:
        log.exception(
            f"upload_failed  stage=file_read  filename={filename!r}  "
            f"error_type={type(e).__name__}"
        )
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": f"Failed to read file: {e}",
        }

    if len(file_bytes) > MAX_FILE_SIZE:
        error = f"File too large: {len(file_bytes)} bytes. Max: {MAX_FILE_SIZE}"
        log.warning(
            f"upload_rejected  filename={filename!r}  reason=file_too_large  "
            f"size_bytes={len(file_bytes)}"
        )
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": error,
        }

    if len(file_bytes) == 0:
        log.warning(f"upload_rejected  filename={filename!r}  reason=empty_file")
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": "Empty file",
        }

    log.info(
        f"upload_received  filename={filename!r}  "
        f"size_bytes={len(file_bytes)}  invoice_type={invoice_type}  "
        f"company_id={company_id}"
    )

    # --- Pipeline ---
    stage = "pipeline_init"
    try:
        stage = "process_invoice"
        result = process_invoice(
            db, company_id, file_bytes, filename, invoice_type=invoice_type
        )
        log.info(
            f"upload_success  filename={filename!r}  "
            f"invoice_type={invoice_type}  "
            f"invoice_id={result.get('invoice_id')}  "
            f"invoice_number={result.get('invoice_number')!r}"
        )
        return {
            "filename": filename, "status": "success",
            "invoice_id": result.get("invoice_id"),
            "invoice_number": result.get("invoice_number"),
            "error": None,
        }
    except ValueError as e:
        log.error(
            f"upload_failed  stage={stage}  filename={filename!r}  "
            f"error_type=ValueError  error={e}"
        )
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": str(e),
        }
    except Exception as e:
        log.exception(
            f"upload_failed  stage={stage}  filename={filename!r}  "
            f"error_type={type(e).__name__}"
        )
        return {
            "filename": filename, "status": "failed",
            "invoice_id": None, "invoice_number": None,
            "error": f"Processing failed: {e}",
        }


# ---------------------------------------------------------------------------
# Single upload
# ---------------------------------------------------------------------------

@router.post("")
async def upload_invoice(
    invoice_type: str = Form(...),
    file: UploadFile = File(...),
    db: Client = Depends(get_supabase),
):
    """
    Upload a single invoice file.
    Accepts: PDF, JPG, JPEG, PNG, BMP, TIFF — max 20 MB.
    invoice_type must be 'payable' or 'receivable'.
    """
    if invoice_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"invoice_type must be 'payable' or 'receivable', got {invoice_type!r}",
        )

    settings   = get_settings()
    company_id = settings.MVP_COMPANY_ID

    result = await _process_single_upload(file, company_id, db, invoice_type)

    if result["status"] == "failed":
        error = result["error"] or ""
        if any(k in error for k in ("Unsupported file type", "too large", "Empty file")):
            raise HTTPException(status_code=400, detail=error)
        if "OCR extracted no text" in error:
            raise HTTPException(status_code=422, detail=error)
        raise HTTPException(status_code=500, detail=error)

    return {
        "status":  "success",
        "message": f"{invoice_type.capitalize()} invoice processed: {result['invoice_number']}",
        "data":    result,
    }


# ---------------------------------------------------------------------------
# Batch upload
# ---------------------------------------------------------------------------

@router.post("/batch")
async def upload_invoice_batch(
    invoice_type: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Client = Depends(get_supabase),
):
    """
    Upload multiple invoice files sequentially. All files in a batch must
    share the same invoice_type. One bad file does not abort the batch.
    Returns aggregate summary + per-file results.
    """
    if invoice_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"invoice_type must be 'payable' or 'receivable', got {invoice_type!r}",
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    settings   = get_settings()
    company_id = settings.MVP_COMPANY_ID

    log.info(
        f"batch_start  file_count={len(files)}  invoice_type={invoice_type}  "
        f"company_id={company_id}"
    )
    t_batch = time.monotonic()

    results = []
    for i, file in enumerate(files, 1):
        filename = file.filename or "unknown"
        log.debug(f"batch_item_start  index={i}/{len(files)}  filename={filename!r}")

        result = await _process_single_upload(file, company_id, db, invoice_type)
        results.append(result)

        if result["status"] == "failed":
            log.error(
                f"batch_item_failed  index={i}/{len(files)}  "
                f"filename={filename!r}  error={result['error']!r}"
            )
        else:
            log.info(
                f"batch_item_success  index={i}/{len(files)}  "
                f"filename={filename!r}  "
                f"invoice_number={result.get('invoice_number')!r}  "
                f"invoice_id={result.get('invoice_id')}"
            )

    success = sum(1 for r in results if r["status"] == "success")
    failed  = sum(1 for r in results if r["status"] == "failed")
    duration = round(time.monotonic() - t_batch, 3)

    log.info(
        f"batch_complete  invoice_type={invoice_type}  total={len(results)}  "
        f"success={success}  failed={failed}  duration_s={duration}"
    )

    return {
        "total":   len(results),
        "success": success,
        "failed":  failed,
        "results": results,
    } 