"""
Test providers in isolation.
Run: python scripts/test_providers.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.core.config import get_settings
from app.providers import get_embedding_provider, get_llm_provider

settings = get_settings()
print(f"Provider: {settings.LLM_PROVIDER}")

# Test 1: Embedding — single text
print("\n--- Embedding test ---")
embedder = get_embedding_provider()
vectors = embedder.embed(["test invoice for server equipment"])
print(f"Vector count: {len(vectors)}")
print(f"Vector dimension: {len(vectors[0])}")
assert len(vectors[0]) == 1536, f"Expected 1536, got {len(vectors[0])}"
print("PASS: Single embedding")

# Test 2: Embedding — batch
vectors = embedder.embed([
    "Invoice 001 from Acme Corp",
    "VAT regulation article 14",
    "Payment received for consulting services",
])
print(f"Batch count: {len(vectors)}")
assert len(vectors) == 3
print("PASS: Batch embedding")

# Test 3: Chat completion
print("\n--- Chat test ---")
llm = get_llm_provider()
response = llm.chat(
    messages=[{"role": "user", "content": "Reply with only the word 'working'"}],
    temperature=0.0,
    max_tokens=10,
)
print(f"LLM response: '{response}'")
assert "working" in response.lower()
print("PASS: Chat completion")

# Test 4: Cohere reranking
print("\n--- Cohere rerank test ---")
from app.services.retrieval.base import RetrievedChunk
from app.providers.cohere_provider import rerank_chunks

chunks = [
    RetrievedChunk(chunk_id="1", source_type="invoice", source_id="a", source_name="INV-001",
                   chunk_text="Invoice for server rack equipment from Dell", similarity=0.8, citation="Invoice INV-001"),
    RetrievedChunk(chunk_id="2", source_type="invoice", source_id="b", source_name="INV-002",
                   chunk_text="Monthly office cleaning service fee", similarity=0.75, citation="Invoice INV-002"),
    RetrievedChunk(chunk_id="3", source_type="invoice", source_id="c", source_name="INV-003",
                   chunk_text="Annual software license renewal for accounting", similarity=0.7, citation="Invoice INV-003"),
]
reranked = rerank_chunks("server equipment purchase", chunks, top_n=2)
print(f"Reranked count: {len(reranked)}")
print(f"Top result: {reranked[0].source_name} — score: {reranked[0].similarity}")
assert reranked[0].chunk_text.lower().count("server") > 0, "Server chunk should rank first"
print("PASS: Cohere reranking")

# Test 5: Intent classifier
print("\n--- Intent classifier test ---")
from app.services.intent_classifier import classify_intent, _keyword_classify

# Keyword-level tests (no LLM call)
assert _keyword_classify("how many overdue invoices") == "sql_aggregation"
assert _keyword_classify("total spent on vendor X") == "sql_aggregation"
assert _keyword_classify("which invoices mention server equipment") == "rag_invoice"
assert _keyword_classify("what does article 14 say about VAT") == "rag_compliance"
assert _keyword_classify("are my invoices compliant with VAT regulation") == "hybrid"
print("PASS: Keyword classification (5/5)")

# Full classifier with LLM fallback
intent = classify_intent("what is the description on invoice 42")
print(f"LLM classified 'what is the description on invoice 42' as: {intent}")
assert intent in {"rag_invoice", "sql_aggregation", "rag_compliance", "hybrid"}
print("PASS: LLM intent classifier")

print("\n=== ALL PROVIDER TESTS PASSED ===")