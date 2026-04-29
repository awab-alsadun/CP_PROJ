"""
Query Service
-------------
Hybrid query router: routes natural language questions to either
a SQL path (aggregations) or a RAG path (semantic search).

SQL path  : keyword detection → SQL template → format with LLM
RAG path  : embed query → vector search → answer with LLM + citations

Provider-agnostic: uses get_embedding_provider() and get_llm_provider().
Changing LLM_PROVIDER in .env switches both paths without code changes.
"""

import logging
import re
from dataclasses import dataclass

from supabase import Client

from app.core.config import get_settings
from app.providers import get_embedding_provider, get_llm_provider

log = logging.getLogger(__name__)

# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class QuerySource:
    invoice_id: str
    invoice_number: str
    chunk_text: str
    similarity: float


@dataclass
class QueryResult:
    answer: str
    sources: list[QuerySource]
    query_type: str  # "sql" | "rag"


# ── SQL keyword detection ────────────────────────────────────────────────────

_SQL_KEYWORDS = re.compile(
    r"\b("
    r"total|sum|average|avg|count|how many|how much|"
    r"highest|lowest|top|bottom|"
    r"between|from \d|since|before|after|"
    r"overdue|unpaid|paid|"
    r"per month|per week|per year|monthly|yearly|"
    r"most expensive|cheapest|"
    r"breakdown|report|summary of amounts|aggregate"
    r")\b",
    re.IGNORECASE,
)


def _is_sql_query(question: str) -> bool:
    return bool(_SQL_KEYWORDS.search(question))


# ── SQL path ─────────────────────────────────────────────────────────────────

# Known SQL templates keyed by intent keyword.
# Each returns rows from Supabase. Add more templates as needed.

def _run_sql_query(db: Client, company_id: str, question: str) -> tuple[list[dict], str]:
    """
    Match question to a SQL template and execute it.

    Returns:
        (rows, intent_label)
    """
    q = question.lower()

    # Intent: vendor spending
    if any(k in q for k in ["vendor", "supplier", "spent on"]):
        rows = (
            db.table("invoices")
            .select("vendors(name), grand_total, status, issue_date")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "vendor_spending"

    # Intent: overdue invoices
    if "overdue" in q:
        rows = (
            db.table("invoices")
            .select("invoice_number, grand_total, due_date, vendors(name)")
            .eq("company_id", company_id)
            .eq("status", "overdue")
            .execute()
            .data
        )
        return rows, "overdue_invoices"

    # Intent: unpaid invoices
    if "unpaid" in q or "not paid" in q:
        rows = (
            db.table("invoices")
            .select("invoice_number, grand_total, due_date, vendors(name)")
            .eq("company_id", company_id)
            .in_("status", ["draft", "sent", "overdue"])
            .execute()
            .data
        )
        return rows, "unpaid_invoices"

    # Intent: payment totals / overall spending
    if any(k in q for k in ["total", "sum", "how much", "spent"]):
        rows = (
            db.table("invoices")
            .select("grand_total, currency, status, issue_date")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "total_spending"

    # Intent: count
    if any(k in q for k in ["how many", "count", "number of"]):
        rows = (
            db.table("invoices")
            .select("id, status")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "invoice_count"

    # Fallback: return all invoices summary
    rows = (
        db.table("invoices")
        .select("invoice_number, grand_total, currency, status, issue_date, vendors(name)")
        .eq("company_id", company_id)
        .limit(50)
        .execute()
        .data
    )
    return rows, "general"


def _answer_sql(question: str, rows: list[dict], intent: str) -> str:
    """Format SQL results into a natural language answer using LLM."""
    llm = get_llm_provider()

    system = (
        "You are a financial analyst assistant. "
        "You are given structured invoice data from a database query. "
        "Answer the user's question based ONLY on the provided data. "
        "Be concise and precise. Use numbers where relevant. "
        "If the data is empty, say so clearly."
    )

    user = (
        f"User question: {question}\n\n"
        f"Query intent: {intent}\n\n"
        f"Data ({len(rows)} rows):\n{rows}\n\n"
        "Answer the question based on this data."
    )

    return llm.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=512,
    )


# ── RAG path ─────────────────────────────────────────────────────────────────

_RAG_MATCH_THRESHOLD = 0.45
_RAG_MATCH_COUNT = 8


def _retrieve_chunks(
    db: Client,
    company_id: str,
    query_vector: list[float],
) -> list[dict]:
    """Call the match_invoice_chunks RPC and return raw rows."""
    result = db.rpc(
        "match_invoice_chunks",
        {
            "query_embedding": query_vector,
            "match_threshold": _RAG_MATCH_THRESHOLD,
            "match_count": _RAG_MATCH_COUNT,
            "filter_company_id": company_id,
        },
    ).execute()
    return result.data or []


def _enrich_with_invoice_numbers(
    db: Client,
    company_id: str,
    chunks: list[dict],
) -> list[dict]:
    """Add invoice_number to each chunk row for citation display."""
    invoice_ids = list({c["invoice_id"] for c in chunks})
    if not invoice_ids:
        return chunks

    result = (
        db.table("invoices")
        .select("id, invoice_number")
        .eq("company_id", company_id)
        .in_("id", invoice_ids)
        .execute()
    )
    id_to_number = {row["id"]: row["invoice_number"] for row in result.data}

    for chunk in chunks:
        chunk["invoice_number"] = id_to_number.get(chunk["invoice_id"], "N/A")

    return chunks


def _answer_rag(question: str, chunks: list[dict]) -> str:
    """Generate answer from retrieved invoice chunks using LLM."""
    if not chunks:
        return (
            "I could not find any relevant invoices matching your question. "
            "Try rephrasing or ask a more specific question."
        )

    llm = get_llm_provider()

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i} — Invoice {chunk.get('invoice_number', 'N/A')} "
            f"({chunk.get('chunk_type', 'unknown')} section)]:\n"
            f"{chunk['chunk_text']}"
        )
    context = "\n\n".join(context_parts)

    system = (
        "You are a financial document analyst. "
        "Answer the user's question using ONLY the invoice excerpts provided. "
        "Cite the invoice numbers when referencing specific invoices. "
        "Do not hallucinate or assume information not present in the context. "
        "If the answer is not in the context, say so clearly."
    )

    user = (
        f"Question: {question}\n\n"
        f"Invoice context:\n{context}\n\n"
        "Answer based on the above invoice data only."
    )

    return llm.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=768,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def handle_query(db: Client, company_id: str, question: str) -> QueryResult:
    """
    Route a natural language question and return a structured answer.

    Args:
        db: Supabase client.
        company_id: Tenant UUID for data isolation.
        question: User's natural language question.

    Returns:
        QueryResult with answer, sources, and query_type.
    """
    question = question.strip()
    if not question:
        return QueryResult(
            answer="Please provide a question.",
            sources=[],
            query_type="none",
        )

    # ── SQL path ──────────────────────────────────────────────────────────────
    if _is_sql_query(question):
        log.info(f"Query routed to SQL path: {question[:80]}")
        try:
            rows, intent = _run_sql_query(db, company_id, question)
            answer = _answer_sql(question, rows, intent)
            return QueryResult(answer=answer, sources=[], query_type="sql")
        except Exception as e:
            log.error(f"SQL path failed: {e}")
            # Fall through to RAG as fallback
            log.info("Falling back to RAG path after SQL failure")

    # ── RAG path ──────────────────────────────────────────────────────────────
    log.info(f"Query routed to RAG path: {question[:80]}")

    embedder = get_embedding_provider()
    query_vector = embedder.embed_one(question)

    raw_chunks = _retrieve_chunks(db, company_id, query_vector)
    chunks = _enrich_with_invoice_numbers(db, company_id, raw_chunks)

    answer = _answer_rag(question, chunks)

    sources = [
        QuerySource(
            invoice_id=c["invoice_id"],
            invoice_number=c.get("invoice_number", "N/A"),
            chunk_text=c["chunk_text"],
            similarity=round(c.get("similarity", 0.0), 4),
        )
        for c in chunks
    ]

    return QueryResult(answer=answer, sources=sources, query_type="rag")