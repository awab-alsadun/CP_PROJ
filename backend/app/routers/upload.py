"""
Upload Router
-------------
Handles invoice file uploads and triggers the processing pipeline.

POST /api/v1/upload
  - Accepts a single file (PDF, JPG, PNG)
  - Runs: OCR → LLM extraction → DB insert → embedding
  - Returns extraction summary with invoice_id

The company_id is hardcoded for MVP. When auth is added,
it comes from the JWT token.
"""

import logging

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from supabase import Client

from app.core.supabase import get_supabase
from app.services.invoice_processor import process_invoice

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# Hardcoded for MVP — replace with auth-derived company_id later
MVP_COMPANY_ID = None  # Set after first request via get_or_create


def _get_company_id(db: Client) -> str:
    """Get or create the test company. Cached after first call."""
    global MVP_COMPANY_ID
    if MVP_COMPANY_ID:
        return MVP_COMPANY_ID

    result = db.table("companies").select("id").eq("name", "Test Company").execute()
    if result.data:
        MVP_COMPANY_ID = result.data[0]["id"]
    else:
        insert = db.table("companies").insert({"name": "Test Company"}).execute()
        MVP_COMPANY_ID = insert.data[0]["id"]

    return MVP_COMPANY_ID


ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("")
async def upload_invoice(
    file: UploadFile = File(...),
    db: Client = Depends(get_supabase),
):
    """
    Upload an invoice file for OCR extraction and storage.

    Accepts: PDF, JPG, JPEG, PNG, BMP, TIFF
    Max size: 20 MB

    Returns extraction summary with invoice_id.
    """
    # Validate file type
    filename = file.filename or "unknown"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read file bytes
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {len(file_bytes)} bytes. Max: {MAX_FILE_SIZE}"
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Get company ID
    company_id = _get_company_id(db)

    # Run the pipeline
    try:
        result = process_invoice(db, company_id, file_bytes, filename)
        return {
            "status": "success",
            "message": f"Invoice processed: {result['invoice_number']}",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.error(f"Upload pipeline failed for {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )