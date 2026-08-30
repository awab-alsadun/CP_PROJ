"""
Pipeline Measurement Script
-----------------------------
Run this from backend/ to get real, citable metrics for the project.

Measures:
  1. Intent classification split (keyword vs LLM %)
  2. Tokens avoided per keyword-classified query
  3. Context compression token reduction (before vs after)
  4. End-to-end query latency per path type

Usage:
    cd backend
    python scripts/measure_pipeline.py

Output: prints a summary table + writes results/pipeline_metrics.json

Requirements:
    pip install tiktoken
"""

import json
import logging
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(level=logging.WARNING)  # suppress noise during measurement

from supabase import create_client
from app.core.config import get_settings
from app.services.token_metrics import (
    count_tokens,
    count_message_tokens,
    get_metrics_summary,
    _TIKTOKEN_AVAILABLE,
)
from app.services.intent_classifier import classify_intent, _CLASSIFIER_SYSTEM_PROMPT
from app.services.query_service import handle_query, _COMPRESSION_PROMPT

# ── Test query set ────────────────────────────────────────────────────────────
# Designed to hit all 3 paths: SQL (keyword), SQL (LLM), RAG, hybrid
TEST_QUERIES = [
    # SQL — keyword path (clear aggregation keywords)
    ("What is the total spending on payable invoices?",             "sql_keyword"),
    ("How many invoices do we have?",                               "sql_keyword"),
    ("Show me the top vendors by amount spent this year",           "sql_keyword"),
    ("Give me a monthly breakdown of invoices",                     "sql_keyword"),
    ("How many clients do we have?",                                "sql_keyword"),
    ("What is the total income from receivables?",                  "sql_keyword"),
    ("Show me overdue invoices",                                    "sql_keyword"),
    ("What is our net income?",                                     "sql_keyword"),
    ("Give me the compliance summary",                              "sql_keyword"),
    ("How many vendors do we have?",                                "sql_keyword"),
    ("What did we pay last month?",                    "sql_keyword"),  # 'last month' not obvious
    ("Show me vendor bills",                           "sql_keyword"),  # no aggregation keyword
    ("Which vendors are we behind on?",                "sql_keyword"),  # indirect overdue
    ("Tell me about our biggest expenses",             "sql_keyword"), 

    # RAG — invoice content (no aggregation, semantic)
    ("Which invoices mention cloud hosting or server infrastructure?", "rag_invoice"),
    ("Find invoices that contain software license charges",            "rag_invoice"),
    ("What services were billed on the most recent invoice?",          "rag_invoice"),

    # Hybrid — compliance + invoice cross-reference
    ("Do our invoices comply with VAT documentation requirements?",   "hybrid"),
    ("Are e-invoicing requirements being met by our current invoices?","hybrid"),
]


def measure_classification_tokens() -> list[dict]:
    """
    For each query, measure:
    - Which path was taken (keyword / LLM)
    - Tokens in the classifier prompt (what LLM path costs)
    - Tokens avoided if keyword path taken
    """
    classifier_prompt_tokens = count_message_tokens([
        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user",   "content": "placeholder"},  # will adjust per query
    ])

    results = []
    for query, expected_path in TEST_QUERIES:
        t0 = time.monotonic()
        result = classify_intent(query)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)

        # Real prompt tokens if LLM had been called
        prompt_tokens = count_message_tokens([
            {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user",   "content": query},
        ])

        # Determine actual path taken
        # keyword_classify returns non-None for keyword hits
        from app.services.intent_classifier import _keyword_classify
        keyword_result = _keyword_classify(query)
        actual_path = "keyword" if keyword_result is not None else "llm"

        results.append({
            "query":            query,
            "expected_path":    expected_path.split("_")[0],
            "actual_path":      actual_path,
            "intent":           result.intent,
            "prompt_tokens":    prompt_tokens,
            "tokens_avoided":   prompt_tokens if actual_path == "keyword" else 0,
            "latency_ms":       latency_ms,
        })

    return results


def measure_compression(db, company_id: str, rag_queries: list[str]) -> list[dict]:
    """
    For each RAG/hybrid query, measure context compression token reduction.
    Runs actual retrieval + compression pipeline.
    """
    from app.services.query_service import (
        _generate_query_variants,
        _apply_doc_type_boost,
        _compress_context,
        _generate_answer,
    )
    from app.providers import get_embedding_provider
    from app.providers import rerank_chunks
    from app.services.retrieval import get_source
    from app.services.intent_classifier import classify_intent

    results = []
    embedder = get_embedding_provider()

    for query in rag_queries:
        try:
            classification = classify_intent(query)
            intent = classification.intent
            relevant_doc_types = classification.relevant_doc_types

            variants = _generate_query_variants(query)
            query_vectors = embedder.embed(variants)

            source_names = {
                "rag_invoice":    ["invoices"],
                "rag_compliance": ["regulations"],
                "hybrid":         ["invoices", "regulations"],
            }.get(intent, ["invoices"])

            all_chunks = []
            for source_name in source_names:
                source = get_source(source_name)
                if source is None:
                    continue
                chunks = source.retrieve(
                    db=db, company_id=company_id,
                    query_vectors=query_vectors,
                    match_count=10, match_threshold=0.40,
                )
                chunks = source.enrich(db, company_id, chunks)
                all_chunks.extend(chunks)

            all_chunks = _apply_doc_type_boost(all_chunks, relevant_doc_types)
            all_chunks.sort(key=lambda c: c.similarity, reverse=True)
            reranked = rerank_chunks(query, all_chunks, top_n=6)

            # Measure compression
            raw_context = "\n\n".join(
                f"[Source {i} - {c.citation}]:\n{c.chunk_text}"
                for i, c in enumerate(reranked, 1)
            )
            tokens_before = count_tokens(raw_context)

            t0 = time.monotonic()
            compressed = _compress_context(query, reranked)
            compression_ms = round((time.monotonic() - t0) * 1000, 1)

            tokens_after = count_tokens(compressed)
            reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1) if tokens_before > 0 else 0

            results.append({
                "query":            query,
                "intent":           intent,
                "chunks_retrieved": len(reranked),
                "tokens_before":    tokens_before,
                "tokens_after":     tokens_after,
                "tokens_saved":     tokens_before - tokens_after,
                "reduction_pct":    reduction_pct,
                "compression_ms":   compression_ms,
            })

        except Exception as e:
            results.append({
                "query":  query,
                "error":  str(e),
            })

    return results


def print_table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    header = "  ".join(f"{label:<{width}}" for _, label, width in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        line = "  ".join(f"{str(row.get(key, '')):<{width}}" for key, _, width in columns)
        print(line)


def main():
    print(f"\n{'='*60}")
    print("InVox Pipeline Measurement")
    print(f"tiktoken available: {_TIKTOKEN_AVAILABLE}")
    print(f"{'='*60}\n")

    settings = get_settings()
    db = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    company_id = settings.MVP_COMPANY_ID

    # ── 1. Classification split ───────────────────────────────────────────────
    print("[ 1 / 2 ] Measuring intent classification...\n")
    classification_results = measure_classification_tokens()

    keyword_hits  = [r for r in classification_results if r["actual_path"] == "keyword"]
    llm_hits      = [r for r in classification_results if r["actual_path"] == "llm"]
    total_queries = len(classification_results)
    keyword_pct   = round(len(keyword_hits) / total_queries * 100, 1)
    avg_avoided   = round(
        sum(r["tokens_avoided"] for r in keyword_hits) / len(keyword_hits), 1
    ) if keyword_hits else 0

    print_table(classification_results, [
        ("query",         "Query",        45),
        ("actual_path",   "Path",          8),
        ("intent",        "Intent",       16),
        ("prompt_tokens", "Prompt Tok",   10),
        ("tokens_avoided","Avoided",       8),
        ("latency_ms",    "ms",            6),
    ])

    print(f"\n  Keyword path: {len(keyword_hits)}/{total_queries} ({keyword_pct}%)")
    print(f"  LLM path:     {len(llm_hits)}/{total_queries}")
    print(f"  Avg tokens avoided per keyword query: {avg_avoided}")
    print(f"  Total tokens avoided (classification): {sum(r['tokens_avoided'] for r in classification_results)}")

    # ── 2. Compression ────────────────────────────────────────────────────────
    print(f"\n[ 2 / 2 ] Measuring context compression (RAG queries)...\n")
    rag_queries = [q for q, path in TEST_QUERIES if "rag" in path or "hybrid" in path]
    compression_results = measure_compression(db, company_id, rag_queries)

    valid = [r for r in compression_results if "error" not in r]
    errors = [r for r in compression_results if "error" in r]

    if valid:
        print_table(valid, [
            ("query",           "Query",          45),
            ("intent",          "Intent",         16),
            ("chunks_retrieved","Chunks",           6),
            ("tokens_before",   "Before",          7),
            ("tokens_after",    "After",           6),
            ("tokens_saved",    "Saved",           6),
            ("reduction_pct",   "Reduction%",     10),
            ("compression_ms",  "ms",              6),
        ])

        avg_reduction = round(sum(r["reduction_pct"] for r in valid) / len(valid), 1)
        avg_saved     = round(sum(r["tokens_saved"]   for r in valid) / len(valid), 1)
        total_saved   = sum(r["tokens_saved"] for r in valid)

        print(f"\n  Avg context token reduction: {avg_reduction}%")
        print(f"  Avg tokens saved per RAG query: {avg_saved}")
        print(f"  Total tokens saved across {len(valid)} RAG queries: {total_saved}")

    if errors:
        print(f"\n  {len(errors)} queries failed:")
        for e in errors:
            print(f"    {e['query'][:50]}: {e['error']}")

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = {
        "tiktoken_available":                    _TIKTOKEN_AVAILABLE,
        "total_queries_measured":                total_queries,
        "keyword_pct":                           keyword_pct,
        "llm_pct":                               round(100 - keyword_pct, 1),
        "avg_tokens_avoided_per_keyword_query":  avg_avoided,
        "total_tokens_avoided_classification":   sum(r["tokens_avoided"] for r in classification_results),
        "rag_queries_measured":                  len(valid),
        "avg_context_compression_pct":           avg_reduction if valid else None,
        "avg_tokens_saved_per_rag_query":        avg_saved if valid else None,
        "total_tokens_saved_compression":        total_saved if valid else None,
        "classification_detail":                 classification_results,
        "compression_detail":                    compression_results,
    }

    output_dir = BACKEND_DIR / "results"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "pipeline_metrics.json"
    output_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print("SUMMARY (copy these into your CV)")
    print(f"{'='*60}")
    print(f"  Intent classifier keyword path:  {keyword_pct}% of queries")
    print(f"  Tokens avoided per keyword query: ~{avg_avoided}")
    if valid:
        print(f"  Context compression reduction:   ~{avg_reduction}% per RAG query")
        print(f"  Tokens saved per RAG query:      ~{avg_saved}")
    print(f"\n  Full results saved to: {output_file}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()