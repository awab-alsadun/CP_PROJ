"""
Query Service (v3)
------------------
Full RAG pipeline with:
  - LLM-based intent classification (with keyword pre-filter)
  - Soft pre-filtering: boosts chunks from relevant document types
    without excluding other types (scale-ready, no tunnel vision)
  - Multi-query rewriting (3 query variants for broader recall)
  - Source registry retrieval (invoices + regulations, extensible)
  - Cohere cross-encoder reranking
  - Contextual compression (extract only relevant sentences)
  - Provider-agnostic (OpenAI / Ollama toggle via .env)

Query paths:
  - sql_aggregation  → template SQL → LLM formatting
  - rag_invoice      → retrieve from invoices only
  - rag_compliance   → retrieve from regulations only (with soft doc type boost)
  - hybrid           → retrieve from both, merge context (with soft doc type boost)

Soft pre-filtering strategy:
  - Retrieve from ALL document types (no hard exclusion)
  - If the classifier detected relevant_doc_types, boost similarity scores
    of matching chunks by a configurable factor
  - Cohere reranking runs on the full set, so genuinely relevant chunks
    from other types still surface if they matter
  - At 5 documents: negligible difference
  - At 100+ documents: reduces noise significantly without missing cross-type answers
"""

import json
import logging
from dataclasses import dataclass, field

from supabase import Client

from app.core.config import get_settings
from app.providers import get_embedding_provider, get_llm_provider
from app.providers.cohere_provider import rerank_chunks
from app.services.intent_classifier import classify_intent, ClassificationResult
from app.services.retrieval import get_all_sources, get_source, RetrievedChunk

log = logging.getLogger(__name__)

# ── Soft boost config ─────────────────────────────────────────────────────────
# Chunks from relevant doc types get their similarity multiplied by this factor
# before reranking. 1.15 = 15% boost. Enough to prefer them in close calls,
# not enough to override a genuinely more relevant chunk from another type.
_DOC_TYPE_BOOST_FACTOR = 1.15


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class QuerySource:
    invoice_id: str           # or document_id for regulations
    invoice_number: str       # or document_name for regulations
    chunk_text: str
    similarity: float
    source_type: str          # "invoice" or "regulation"
    citation: str             # human-readable citation
    metadata: dict = field(default_factory=dict)


@dataclass
class QueryResult:
    answer: str
    sources: list[QuerySource]
    query_type: str           # "sql" | "rag_invoice" | "rag_compliance" | "hybrid"


# ── Multi-query rewriting ────────────────────────────────────────────────────

_MULTI_QUERY_PROMPT = """You are a query rewriter for a financial invoicing system.

Given the user's question, generate 3 alternative phrasings that capture the same intent
but use different vocabulary. This helps retrieve documents that use different terminology.

Rules:
- Keep the same meaning and scope
- Use different financial/business terms where possible
- Each variant should be a complete, standalone question
- Return ONLY a JSON array of 3 strings
- No explanation, no markdown

Example:
Input: "Which invoices mention server equipment?"
Output: ["What invoices reference IT hardware?", "Find invoices containing server or computing purchases", "Which bills include data center equipment?"]"""


def _generate_query_variants(question: str) -> list[str]:
    """
    Generate 3 alternative phrasings of the question for broader recall.
    Always includes the original question as the first variant.
    """
    try:
        llm = get_llm_provider()
        response = llm.chat(
            messages=[
                {"role": "system", "content": _MULTI_QUERY_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        cleaned = response.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        variants = json.loads(cleaned)
        if isinstance(variants, list) and len(variants) >= 2:
            return [question] + [v for v in variants[:2]]

    except Exception as e:
        log.warning(f"Multi-query generation failed: {e}. Using original question only.")

    return [question]


# ── Soft pre-filtering ────────────────────────────────────────────────────────

def _apply_doc_type_boost(
    chunks: list[RetrievedChunk],
    relevant_doc_types: list[str],
) -> list[RetrievedChunk]:
    """
    Boost similarity scores of chunks whose document_type matches
    the classifier's detected relevant types.

    This is SOFT pre-filtering:
    - Matching chunks get a 15% similarity boost
    - Non-matching chunks keep their original score
    - Nothing is excluded — Cohere reranking makes the final call

    Only applies to regulation/document chunks (source_type != "invoice").
    Invoice chunks are never boosted or penalized by doc type.
    """
    if not relevant_doc_types:
        return chunks

    boosted_types = set(relevant_doc_types)
    boosted_count = 0

    for chunk in chunks:
        if chunk.source_type == "invoice":
            continue

        chunk_doc_type = chunk.metadata.get("document_type", "")
        if chunk_doc_type in boosted_types:
            original = chunk.similarity
            chunk.similarity = min(chunk.similarity * _DOC_TYPE_BOOST_FACTOR, 1.0)
            chunk.metadata["soft_boost_applied"] = True
            chunk.metadata["original_similarity"] = round(original, 4)
            boosted_count += 1

    if boosted_count > 0:
        log.info(f"Soft boost applied to {boosted_count} chunks matching types: {relevant_doc_types}")

    return chunks


# ── Contextual compression ────────────────────────────────────────────────────

_COMPRESSION_PROMPT = """You are a precision text extractor. Given a user question and retrieved document chunks,
extract ONLY the sentences that are directly relevant to answering the question.

Rules:
- Remove irrelevant sentences entirely
- Keep relevant sentences verbatim — do not paraphrase
- Maintain the source labels [Source N] so citations still work
- If a chunk has no relevant content, omit it entirely
- IMPORTANT: Invoice data chunks (containing invoice numbers, amounts, dates, vendor names,
  line items) are ALWAYS relevant when the question asks about invoice compliance,
  verification, or cross-referencing against regulations. Keep them.
- Return the compressed text only, no explanation"""

def _compress_context(question: str, chunks: list[RetrievedChunk]) -> str:
    """
    Contextual compression: extract only relevant sentences from retrieved chunks.
    Single LLM call with all chunks concatenated.
    """
    if not chunks:
        return ""

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i} — {chunk.citation}]:\n{chunk.chunk_text}"
        )
    raw_context = "\n\n".join(context_parts)

    try:
        llm = get_llm_provider()
        compressed = llm.chat(
            messages=[
                {"role": "system", "content": _COMPRESSION_PROMPT},
                {"role": "user", "content": (
                    f"Question: {question}\n\n"
                    f"Chunks:\n{raw_context}\n\n"
                    "Extract only relevant sentences."
                )},
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        return compressed.strip()

    except Exception as e:
        log.warning(f"Contextual compression failed: {e}. Using raw context.")
        return raw_context


# ── SQL path ─────────────────────────────────────────────────────────────────

def _run_sql_query(db: Client, company_id: str, question: str) -> tuple[list[dict], str]:
    """Match question to SQL template and execute."""
    q = question.lower()

    if any(k in q for k in ["vendor", "supplier", "spent on"]):
        rows = (
            db.table("invoices")
            .select("vendors(name), grand_total, status, issue_date")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "vendor_spending"

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

    if any(k in q for k in ["total", "sum", "how much", "spent"]):
        rows = (
            db.table("invoices")
            .select("grand_total, currency, status, issue_date")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "total_spending"

    if any(k in q for k in ["how many", "count", "number of"]):
        rows = (
            db.table("invoices")
            .select("id, status")
            .eq("company_id", company_id)
            .execute()
            .data
        )
        return rows, "invoice_count"

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
    """Format SQL results into natural language via LLM."""
    llm = get_llm_provider()

    return llm.chat(
        messages=[
            {"role": "system", "content": (
                "You are a financial analyst assistant. "
                "Answer the user's question based ONLY on the provided data. "
                "Be concise and precise. Use numbers. "
                "If data is empty, say so clearly."
            )},
            {"role": "user", "content": (
                f"Question: {question}\n\n"
                f"Query intent: {intent}\n"
                f"Data ({len(rows)} rows):\n{rows}\n\n"
                "Answer based on this data."
            )},
        ],
        temperature=0.0,
        max_tokens=512,
    )


# ── RAG answer generation ────────────────────────────────────────────────────

def _generate_answer(question: str, compressed_context: str, query_type: str) -> str:
    """Generate final answer from compressed context."""
    if not compressed_context.strip():
        return (
            "I could not find relevant information to answer your question. "
            "Try rephrasing or providing more specific details."
        )

    llm = get_llm_provider()

    system_prompts = {
        "rag_invoice": (
            "You are a financial document analyst. "
            "Answer using ONLY the invoice excerpts provided. "
            "Cite invoice numbers when referencing specific invoices. "
            "Do not hallucinate or assume information not in the context."
        ),
        "rag_compliance": (
            "You are a regulatory compliance analyst. "
            "Answer using ONLY the regulation excerpts provided. "
            "Cite the document name, section number, and page when referencing specific rules. "
            "Do not give legal advice — present the regulations as written."
        ),
        "hybrid": (
    "You are a financial compliance analyst. "
    "You are given REAL invoice data and regulatory document excerpts. "
    "Answer the question by cross-referencing the invoices against the regulations. "
    "CRITICAL: Only reference invoice numbers that appear in the context below. "
    "Never invent or fabricate invoice numbers, amounts, or details. "
    "If the context contains invoice data, list the ACTUAL invoice numbers and their details. "
    "If the context does not contain enough invoice data to answer, say so explicitly. "
    "Cite both invoice numbers and regulation sections with page numbers. "
    "Flag any potential compliance issues you detect based on the actual data."
),
    }

    system = system_prompts.get(query_type, system_prompts["rag_invoice"])

    return llm.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": (
                f"Question: {question}\n\n"
                f"Context:\n{compressed_context}\n\n"
                "Answer based on the above context only."
            )},
        ],
        temperature=0.0,
        max_tokens=768,
    )


# ── Main entry point ─────────────────────────────────────────────────────────

def handle_query(db: Client, company_id: str, question: str) -> QueryResult:
    """
    Full query pipeline:
    1. Classify intent + extract relevant doc types
    2. Route to SQL or RAG
    3. (RAG) Multi-query rewrite → embed → retrieve → soft boost → rerank → compress → answer
    """
    question = question.strip()
    if not question:
        return QueryResult(answer="Please provide a question.", sources=[], query_type="none")

    # ── Step 1: Classify intent ───────────────────────────────────────────────
    classification = classify_intent(question)
    intent = classification.intent
    relevant_doc_types = classification.relevant_doc_types
    log.info(f"Intent: {intent}, relevant_doc_types: {relevant_doc_types}")

    # ── Step 2: SQL path ──────────────────────────────────────────────────────
    if intent == "sql_aggregation":
        try:
            rows, sql_intent = _run_sql_query(db, company_id, question)
            answer = _answer_sql(question, rows, sql_intent)
            return QueryResult(answer=answer, sources=[], query_type="sql")
        except Exception as e:
            log.error(f"SQL path failed: {e}. Falling back to RAG.")
            intent = "rag_invoice"

    # ── Step 3: Multi-query rewrite ───────────────────────────────────────────
    variants = _generate_query_variants(question)
    log.info(f"Query variants: {variants}")

    # ── Step 4: Embed all variants ────────────────────────────────────────────
    embedder = get_embedding_provider()
    query_vectors = embedder.embed(variants)

    # ── Step 5: Retrieve from relevant sources ────────────────────────────────
    all_chunks: list[RetrievedChunk] = []

    if intent == "rag_invoice":
        source_names = ["invoices"]
    elif intent == "rag_compliance":
        source_names = ["regulations"]
    elif intent == "hybrid":
        source_names = ["invoices", "regulations"]
    else:
        source_names = ["invoices", "regulations"]

    for source_name in source_names:
        source = get_source(source_name)
        if source is None:
            log.warning(f"Source '{source_name}' not found in registry")
            continue

        chunks = source.retrieve(
            db=db,
            company_id=company_id,
            query_vectors=query_vectors,
            match_count=10,
            match_threshold=0.40,
        )
        chunks = source.enrich(db, company_id, chunks)
        all_chunks.extend(chunks)
        log.info(f"Retrieved {len(chunks)} chunks from {source.display_name}")

    log.info(f"Total chunks before boosting: {len(all_chunks)}")

    # ── Step 6: Soft pre-filtering (doc type boost) ───────────────────────────
    all_chunks = _apply_doc_type_boost(all_chunks, relevant_doc_types)

    # Re-sort by boosted similarity before reranking
    all_chunks.sort(key=lambda c: c.similarity, reverse=True)

    # ── Step 7: Rerank with Cohere ────────────────────────────────────────────
    # ── Step 7: Rerank with Cohere ────────────────────────────────────────────
    if intent == "hybrid" and len(source_names) > 1:
        # Hybrid: rerank each source separately, then merge
        # Guarantees both invoice and regulation chunks appear in context
        invoice_chunks = [c for c in all_chunks if c.source_type == "invoice"]
        regulation_chunks = [c for c in all_chunks if c.source_type != "invoice"]

        slots_per_source = max(2, 6 // len(source_names))  # 3 each for 2 sources

        reranked_invoices = rerank_chunks(question, invoice_chunks, top_n=slots_per_source)
        reranked_regulations = rerank_chunks(question, regulation_chunks, top_n=slots_per_source)

        reranked = reranked_invoices + reranked_regulations
        reranked.sort(key=lambda c: c.similarity, reverse=True)
        log.info(f"Hybrid rerank: {len(reranked_invoices)} invoice + {len(reranked_regulations)} regulation chunks")
    else:
        reranked = rerank_chunks(question, all_chunks, top_n=6)

    log.info(f"Chunks after reranking: {len(reranked)}")

    # ── Step 8: Contextual compression ────────────────────────────────────────
    compressed = _compress_context(question, reranked)

    # ── Step 9: Generate answer ───────────────────────────────────────────────
    answer = _generate_answer(question, compressed, intent)

    # ── Build sources for frontend ────────────────────────────────────────────
    sources = [
        QuerySource(
            invoice_id=c.source_id,
            invoice_number=c.source_name,
            chunk_text=c.chunk_text,
            similarity=round(c.similarity, 4),
            source_type=c.source_type,
            citation=c.citation,
            metadata=c.metadata,
        )
        for c in reranked
    ]

    return QueryResult(answer=answer, sources=sources, query_type=intent)