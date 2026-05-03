"""
Documents Router
----------------
Endpoints for managing regulatory/compliance documents.

POST   /api/v1/documents/upload   — upload and embed a regulation PDF
GET    /api/v1/documents          — list all documents for the company
DELETE /api/v1/documents/{id}     — delete a document and its embeddings
PATCH  /api/v1/documents/{id}     — update document type or country tag

company_id: hardcoded MVP_COMPANY_ID from settings.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.services.document_service import (
    upload_and_embed_document,
    list_documents,
    delete_document,
    update_document_metadata,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ── Response models ───────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    status: str
    message: str
    data: dict


class DocumentListResponse(BaseModel):
    documents: list[dict]
    count: int


class DocumentUpdateRequest(BaseModel):
    document_type: str | None = None
    country: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="general"),
    country: str = Form(default=None),
    db: Client = Depends(get_supabase),
):
    """
    Upload a regulation/compliance PDF for embedding and retrieval.

    Form fields:
      - file: PDF file (max 100 pages)
      - document_type: 'tax_regulation', 'compliance_guide', 'vat_rules',
                       'customs', 'company_policy', 'general'
      - country: ISO country code ('TR', 'SA', 'AE', etc.)
    """
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    # Validate file type
    filename = file.filename or "unknown.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for document uploads."
        )

    # Read file
    file_bytes = await file.read()
    max_size = 50 * 1024 * 1024  # 50 MB
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=400, detail=f"File too large. Max: {max_size // (1024*1024)} MB")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Validate document_type
    valid_types = {
        "tax_regulation", "compliance_guide", "vat_rules",
        "customs", "company_policy", "general",
    }
    if document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Must be one of: {', '.join(sorted(valid_types))}"
        )

    try:
        result = upload_and_embed_document(
            db=db,
            company_id=company_id,
            file_bytes=file_bytes,
            filename=filename,
            document_type=document_type,
            country=country,
        )
        return DocumentUploadResponse(
            status="success",
            message=f"Document '{filename}' processed: {result['chunk_count']} chunks embedded",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.error(f"Document upload failed for {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.get("", response_model=DocumentListResponse)
async def list_company_documents(
    db: Client = Depends(get_supabase),
):
    """List all active documents for the company."""
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    docs = list_documents(db, company_id)
    return DocumentListResponse(documents=docs, count=len(docs))


@router.delete("/{document_id}")
async def delete_company_document(
    document_id: str,
    db: Client = Depends(get_supabase),
):
    """Delete a document and all its embedded chunks."""
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    deleted = delete_document(db, company_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "success", "message": f"Document {document_id} deleted"}


@router.patch("/{document_id}")
async def update_company_document(
    document_id: str,
    body: DocumentUpdateRequest,
    db: Client = Depends(get_supabase),
):
    """Update document_type and/or country for a document."""
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    if body.document_type:
        valid_types = {
            "tax_regulation", "compliance_guide", "vat_rules",
            "customs", "company_policy", "general",
        }
        if body.document_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid document_type. Must be one of: {', '.join(sorted(valid_types))}"
            )

    updated = update_document_metadata(
        db=db,
        company_id=company_id,
        document_id=document_id,
        document_type=body.document_type,
        country=body.country,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found or no changes made")

    return {"status": "success", "message": f"Document {document_id} updated"}