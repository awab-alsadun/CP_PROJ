"""
Query Router
------------
POST /api/v1/query

Accepts a natural language question and returns an AI-generated answer
with citations, routed through SQL / RAG / hybrid paths.

Request body:
    { "question": "string" }

Response:
    {
        "answer": "string",
        "sources": [ ... ],
        "query_type": "sql" | "rag_invoice" | "rag_compliance" | "hybrid"
    }
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from supabase import Client

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.services.query_service import handle_query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > 2000:
            raise ValueError("question must be 2000 characters or fewer")
        return v


class QuerySourceResponse(BaseModel):
    invoice_id: str
    invoice_number: str
    chunk_text: str
    similarity: float
    source_type: str
    citation: str
    metadata: dict = {}


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySourceResponse]
    query_type: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=QueryResponse)
async def query_invoices(
    body: QueryRequest,
    db: Client = Depends(get_supabase),
):
    """
    Ask a natural language question about your invoices and regulatory documents.

    Routes to:
    - SQL path for aggregation questions (totals, counts, averages)
    - RAG invoice path for semantic questions about invoice content
    - RAG compliance path for regulatory/tax questions
    - Hybrid path for cross-referencing invoices against regulations
    """
    settings = get_settings()
    company_id = settings.MVP_COMPANY_ID

    log.info(f"Query received: {body.question[:100]}")

    try:
        result = handle_query(db=db, company_id=company_id, question=body.question)
    except Exception as e:
        log.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

    return QueryResponse(
        answer=result.answer,
        sources=[
            QuerySourceResponse(
                invoice_id=s.invoice_id,
                invoice_number=s.invoice_number,
                chunk_text=s.chunk_text,
                similarity=s.similarity,
                source_type=s.source_type,
                citation=s.citation,
                metadata=s.metadata,
            )
            for s in result.sources
        ],
        query_type=result.query_type,
    )