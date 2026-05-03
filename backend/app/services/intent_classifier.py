"""
Intent Classifier
-----------------
LLM-based query intent detection with keyword pre-filter.

Two-stage approach:
1. Fast keyword scan catches obvious cases (70% of queries)
2. LLM classifier handles ambiguous cases (30%)

Returns:
    ClassificationResult with intent + relevant_doc_types for soft pre-filtering.

Intent categories:
- sql_aggregation  : totals, counts, averages, rankings
- rag_invoice      : semantic questions about invoice content
- rag_compliance   : questions about regulations, compliance, tax rules
- hybrid           : needs both invoice data and regulatory context

Provider-agnostic: uses get_llm_provider().
"""

import json
import logging
import re
from dataclasses import dataclass, field

from app.providers import get_llm_provider

log = logging.getLogger(__name__)


# ── Classification result ─────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    intent: str                              # "sql_aggregation" | "rag_invoice" | "rag_compliance" | "hybrid"
    relevant_doc_types: list[str] = field(default_factory=list)  # e.g. ["vat_rules", "tax_regulation"], empty = search all


# ── Keyword pre-filter ────────────────────────────────────────────────────────

_SQL_KEYWORDS = re.compile(
    r"\b("
    r"total|sum|average|avg|count|how many|how much|"
    r"highest|lowest|top\s+\d|bottom\s+\d|"
    r"per month|per week|per year|monthly|yearly|weekly|"
    r"most expensive|cheapest|"
    r"breakdown|aggregate|"
    r"number of invoices|number of payments"
    r")\b",
    re.IGNORECASE,
)

_COMPLIANCE_KEYWORDS = re.compile(
    r"\b("
    r"complian|regulat|tax law|tax rule|vat|"
    r"legal|article\s+\d|section\s+\d|"
    r"policy|guideline|requirement|obligation|"
    r"penalty|violation|exempt|deduction|"
    r"customs|duty|tariff|e-invoice|e-invoicing"
    r")\b",
    re.IGNORECASE,
)

_INVOICE_CONTENT_KEYWORDS = re.compile(
    r"\b("
    r"mention|describe|about|contain|include|"
    r"which invoice|find invoice|show invoice|"
    r"what did|what does|charged for|billed for|"
    r"details of|specifics"
    r")\b",
    re.IGNORECASE,
)

# Maps keyword patterns to document types for soft pre-filtering
_DOC_TYPE_HINTS = [
    (re.compile(r"\bvat\b", re.IGNORECASE), "vat_rules"),
    (re.compile(r"\b(tax|taxation|tax law|tax rule|irs|revenue)\b", re.IGNORECASE), "tax_regulation"),
    (re.compile(r"\b(customs|tariff|duty|import|export)\b", re.IGNORECASE), "customs"),
    (re.compile(r"\b(compliance|compliant|guideline|requirement)\b", re.IGNORECASE), "compliance_guide"),
    (re.compile(r"\b(company policy|internal policy|our policy)\b", re.IGNORECASE), "company_policy"),
    (re.compile(r"\b(e-invoice|e-invoicing|electronic invoice)\b", re.IGNORECASE), "tax_regulation"),
]


def _extract_doc_type_hints(question: str) -> list[str]:
    """Extract likely document types from question keywords."""
    hits = []
    for pattern, doc_type in _DOC_TYPE_HINTS:
        if pattern.search(question) and doc_type not in hits:
            hits.append(doc_type)
    return hits[:3]  # Cap at 3 types


def _keyword_classify(question: str) -> ClassificationResult | None:
    """
    Fast keyword-based classification.
    Returns ClassificationResult or None if ambiguous.
    """
    has_sql = bool(_SQL_KEYWORDS.search(question))
    has_compliance = bool(_COMPLIANCE_KEYWORDS.search(question))
    has_invoice_content = bool(_INVOICE_CONTENT_KEYWORDS.search(question))

    doc_type_hints = _extract_doc_type_hints(question)

    if has_sql and not has_compliance and not has_invoice_content:
        return ClassificationResult(intent="sql_aggregation")

    if has_compliance and not has_sql:
        if has_invoice_content:
            return ClassificationResult(intent="hybrid", relevant_doc_types=doc_type_hints)
        return ClassificationResult(intent="rag_compliance", relevant_doc_types=doc_type_hints)

    if has_invoice_content and not has_sql and not has_compliance:
        return ClassificationResult(intent="rag_invoice")

    return None


# ── LLM classifier ───────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM_PROMPT = """You are a query intent classifier for a financial invoicing system.

Classify the user's question into EXACTLY ONE intent category AND list the most relevant document types.

Intent categories:
- "sql_aggregation": numerical aggregation, counts, totals, averages, rankings, date filtering
- "rag_invoice": questions about invoice content, descriptions, or details
- "rag_compliance": questions about regulations, tax rules, compliance requirements
- "hybrid": needs BOTH invoice data AND regulatory context

Document types (pick up to 3 most relevant, or empty list if not a compliance/hybrid query):
- "tax_regulation": tax laws, IRS publications, tax codes
- "vat_rules": value added tax rules and requirements
- "compliance_guide": general compliance guidelines and standards
- "customs": customs, tariffs, import/export duties
- "company_policy": internal company billing/invoicing policies
- "general": documents that don't fit other categories

Respond with ONLY a JSON object:
{"intent": "one_of_four", "relevant_doc_types": ["type1", "type2"]}

For sql_aggregation or rag_invoice intents, return empty relevant_doc_types: []
No explanation. No markdown. Just the JSON."""


def classify_intent(question: str) -> ClassificationResult:
    """
    Classify query intent and extract relevant document types.

    Tries keyword pre-filter first, falls back to LLM for ambiguous cases.

    Returns:
        ClassificationResult with intent and relevant_doc_types.
    """
    # Stage 1: Keyword pre-filter
    keyword_result = _keyword_classify(question)
    if keyword_result:
        log.info(f"Intent classified by keywords: {keyword_result.intent}, doc_types: {keyword_result.relevant_doc_types}")
        return keyword_result

    # Stage 2: LLM classifier
    log.info("Intent ambiguous — using LLM classifier")
    try:
        llm = get_llm_provider()
        response = llm.chat(
            messages=[
                {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=100,
        )

        cleaned = response.strip().strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        parsed = json.loads(cleaned)
        intent = parsed.get("intent", "rag_invoice")
        doc_types = parsed.get("relevant_doc_types", [])

        valid_intents = {"sql_aggregation", "rag_invoice", "rag_compliance", "hybrid"}
        if intent not in valid_intents:
            log.warning(f"LLM returned invalid intent '{intent}', defaulting to rag_invoice")
            intent = "rag_invoice"

        valid_doc_types = {"tax_regulation", "vat_rules", "compliance_guide", "customs", "company_policy", "general"}
        doc_types = [dt for dt in doc_types if dt in valid_doc_types][:3]

        log.info(f"Intent classified by LLM: {intent}, doc_types: {doc_types}")
        return ClassificationResult(intent=intent, relevant_doc_types=doc_types)

    except Exception as e:
        log.error(f"LLM intent classification failed: {e}. Defaulting to rag_invoice.")
        return ClassificationResult(intent="rag_invoice")