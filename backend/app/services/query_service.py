"""
Query Service (v4)
------------------
Full RAG pipeline with Option C SQL routing:

  SQL path:
    - Intent classifier detects sql_aggregation (keyword pre-filter, no LLM call)
    - LLM template selector picks template + extracts parameters (dates, filters)
    - Template executor runs safe Supabase query builder calls — LLM never writes SQL
    - Python-side aggregation (Counter, sum) — LLM only formats the result
    - Fallback to RAG if no template matches

  RAG path (unchanged from v3):
    - Multi-query rewriting -> embed -> retrieve -> soft boost -> rerank -> compress -> answer
    - Hybrid split reranking for compliance queries
    - Provider-agnostic generation (OpenAI / Ollama / Grok / Gemini via LLM_PROVIDER)
    - Retrieval embeddings selected separately via EMBEDDING_PROVIDER

  Date awareness:
    - Today's date injected into LLM template selector prompt
    - LLM resolves "yesterday", "last month", "this quarter" -> ISO date strings

  Templates (18):
    Regular (Supabase query builder):
      invoice_count, invoice_list, total_spending, total_income, net_income,
      vendor_spending, client_spending, vendor_count, vendor_balances,
      client_count, client_balances, overdue_invoices, monthly_breakdown,
      payment_history, compliance_summary, top_vendors
    RPC (Supabase functions):
      avg_payment_delay, invoice_aging
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from supabase import Client

from app.core.config import get_settings
from app.providers import get_embedding_provider, get_llm_provider,rerank_chunks
from app.services.intent_classifier import classify_intent
from app.services.retrieval import get_source, RetrievedChunk

log = logging.getLogger(__name__)

_DOC_TYPE_BOOST_FACTOR = 1.15


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class QuerySource:
    invoice_id:     str
    invoice_number: str
    chunk_text:     str
    similarity:     float
    source_type:    str
    citation:       str
    metadata:       dict = field(default_factory=dict)


@dataclass
class QueryResult:
    answer:     str
    sources:    list[QuerySource]
    query_type: str


# ══════════════════════════════════════════════════════════════════════════════
# SQL PATH — Option C
# ══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_SELECTOR_PROMPT = """You are a query parameter extractor for a financial invoicing system.
Today's date is {today}.

Given a user question, return a JSON object with:
  "template"  : the best matching template name (string)
  "filters"   : extracted filter parameters (object)

Available templates and what they answer:
  invoice_count       - how many invoices exist, optionally by status/type/vendor/date
  invoice_list        - list invoices, optionally filtered
  total_spending      - total amount spent on PAYABLE invoices (money going out), optionally by vendor/date/status
  total_income        - total amount earned from RECEIVABLE invoices (money coming in), optionally by client/date/status
  total_revenue       - total of ALL invoices regardless of type (payable + receivable combined), optionally by date/status
  net_income          - net income = total receivable income minus total payable spending, optionally by date range
  vendor_spending     - spending broken down by vendor (payable only), optionally filtered by date
  client_spending     - income broken down by client (receivable only), optionally filtered by date
  vendor_count        - how many vendors exist
  vendor_balances     - outstanding (unpaid/overdue) balance per vendor
  client_count        - how many clients exist
  client_balances     - outstanding receivable balance per client
  overdue_invoices    - list overdue invoices, optionally filtered by date/vendor/client
  monthly_breakdown   - invoice count and spend per calendar month
  payment_history     - list payments, optionally filtered by date/vendor
  compliance_summary  - compliance flag counts by type and severity
  top_vendors         - vendors ranked by total spend, optionally filtered by date
  avg_payment_delay   - average days between due_date and payment per vendor
  invoice_aging       - outstanding invoices grouped into aging buckets (0-30, 31-60, 61-90, 90+ days)

Routing rules:
  - "income", "revenue from clients", "earned", "receivable total" -> total_income
  - "spending", "expenses", "spent", "payable total", "costs" -> total_spending
  - "total revenue", "all invoices total", "combined total", "everything invoiced" -> total_revenue
  - "net income", "net profit", "profit", "net earnings", "income minus expenses" -> net_income
  - "how much did [client] pay us", "revenue from [client]" -> client_spending
  - "how much did we pay [vendor]", "spending on [vendor]" -> vendor_spending

Filter parameters (all optional, use null if not applicable):
  date_from     : ISO date string (YYYY-MM-DD) - start of date range on issue_date
  date_to       : ISO date string (YYYY-MM-DD) - end of date range on issue_date
  vendor_name   : vendor name string (partial match ok)
  client_name   : client name string (partial match ok)
  status        : one of: draft, sent, unpaid, partially_paid, paid, overdue
  invoice_type  : "payable" or "receivable"
  currency      : ISO currency code e.g. "USD"
  limit         : integer, max rows to return (default null = all)

IMPORTANT: Do NOT add date filters unless the user explicitly mentions a time period.
"current income" or "total spending" without a date reference means ALL TIME — use null for date_from and date_to.
Only add date filters for explicit references like "this month", "in 2026", "last quarter", "yesterday", etc.

Date resolution rules (today is {today}):
  "yesterday"       -> date_from and date_to = yesterday's date
  "last week"       -> Monday to Sunday of last week
  "this week"       -> Monday of current week to today
  "last month"      -> first to last day of previous calendar month
  "this month"      -> first day of current month to today
  "last quarter"    -> first to last day of previous calendar quarter
  "this quarter"    -> first day of current quarter to today
  "this year"       -> January 1 of current year to today
  "last year"       -> January 1 to December 31 of previous year
  Month name only ("in March", "March 2026") -> first to last day of that month
  "recent", "recently", "latest" for payment_history -> date_from = 30 days ago, date_to = today
  No date specified for payment_history -> date_from = 30 days ago, date_to = today

If no template matches, return: {{"template": "none", "filters": {{}}}}
Return ONLY the JSON object. No explanation. No markdown. No extra text."""


def _select_template(question: str) -> dict:
    today  = date.today().isoformat()
    prompt = _TEMPLATE_SELECTOR_PROMPT.format(today=today)

    try:
        llm      = get_llm_provider()
        response = llm.chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": question},
            ],
            temperature=0.0,
            max_tokens=200,
        )

        cleaned = response.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        

        log.info(f"Template selector raw response: {repr(cleaned)}")

        parsed = json.loads(cleaned)
        parsed = {k.strip('"').strip("'"): v for k, v in parsed.items()}

        valid_templates = {
            "invoice_count", "invoice_list", "total_spending", "total_income",
            "total_revenue", "net_income", "vendor_spending", "client_spending",
            "vendor_count", "vendor_balances", "client_count", "client_balances",
            "overdue_invoices", "monthly_breakdown", "payment_history",
            "compliance_summary", "top_vendors", "avg_payment_delay",
            "invoice_aging", "none",
        }
        if parsed.get("template") not in valid_templates:
            log.warning(f"LLM returned unknown template '{parsed.get('template')}', defaulting to none")
            return {"template": "none", "filters": {}}

        log.info(f"Template: {parsed.get('template')}, filters: {parsed.get('filters')}")
        return parsed

    except Exception as e:
        log.error(f"Template selector failed: {e}")
        return {"template": "none", "filters": {}}


# ── Filter helpers ────────────────────────────────────────────────────────────

def _apply_date_filters(query, filters: dict, date_column: str = "issue_date"):
    if filters.get("date_from"):
        query = query.gte(date_column, filters["date_from"])
    if filters.get("date_to"):
        query = query.lte(date_column, filters["date_to"])
    return query


def _resolve_vendor_ids(db: Client, company_id: str, vendor_name: str) -> list[str]:
    try:
        result = (
            db.table("vendors")
            .select("id")
            .eq("company_id", company_id)
            .ilike("name", f"%{vendor_name}%")
            .execute()
        )
        return [r["id"] for r in (result.data or [])]
    except Exception:
        return []


def _resolve_client_ids(db: Client, company_id: str, client_name: str) -> list[str]:
    try:
        result = (
            db.table("clients")
            .select("id")
            .eq("company_id", company_id)
            .ilike("name", f"%{client_name}%")
            .execute()
        )
        return [r["id"] for r in (result.data or [])]
    except Exception:
        return []


# ── Template executors ────────────────────────────────────────────────────────

def _exec_invoice_count(db: Client, company_id: str, filters: dict) -> dict:
    q = (
        db.table("invoices")
        .select("id, status, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    if filters.get("vendor_name"):
        ids = _resolve_vendor_ids(db, company_id, filters["vendor_name"])
        if ids:
            q = q.in_("vendor_id", ids)
    rows = q.execute().data or []
    return {
        "total":     len(rows),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_type":   dict(Counter(r["invoice_type"] for r in rows)),
    }


def _exec_invoice_list(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("invoice_number, status, invoice_type, grand_total, currency, "
                "issue_date, due_date, vendors(name), clients(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    if filters.get("vendor_name"):
        ids = _resolve_vendor_ids(db, company_id, filters["vendor_name"])
        if ids:
            q = q.in_("vendor_id", ids)
    if filters.get("client_name"):
        ids = _resolve_client_ids(db, company_id, filters["client_name"])
        if ids:
            q = q.in_("client_id", ids)
    limit = filters.get("limit") or 50
    return q.order("issue_date", desc=True).limit(limit).execute().data or []


def _exec_total_spending(db: Client, company_id: str, filters: dict) -> dict:
    q = (
        db.table("invoices")
        .select("grand_total, currency, status, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    if filters.get("currency"):
        q = q.eq("currency", filters["currency"])
    if filters.get("vendor_name"):
        ids = _resolve_vendor_ids(db, company_id, filters["vendor_name"])
        if ids:
            q = q.in_("vendor_id", ids)
    rows = q.execute().data or []
    totals: dict[str, float] = {}
    for r in rows:
        cur = r.get("currency") or "USD"
        totals[cur] = round(totals.get(cur, 0.0) + float(r.get("grand_total") or 0), 2)
    return {"total_by_currency": totals, "invoice_count": len(rows)}


def _exec_total_income(db: Client, company_id: str, filters: dict) -> dict:
    q = (
        db.table("invoices")
        .select("grand_total, currency, status, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    if filters.get("currency"):
        q = q.eq("currency", filters["currency"])
    if filters.get("client_name"):
        ids = _resolve_client_ids(db, company_id, filters["client_name"])
        if ids:
            q = q.in_("client_id", ids)
    rows = q.execute().data or []
    totals: dict[str, float] = {}
    for r in rows:
        cur = r.get("currency") or "USD"
        totals[cur] = round(totals.get(cur, 0.0) + float(r.get("grand_total") or 0), 2)
    return {"total_by_currency": totals, "invoice_count": len(rows)}


def _exec_total_revenue(db: Client, company_id: str, filters: dict) -> dict:
    q = (
        db.table("invoices")
        .select("grand_total, currency, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("currency"):
        q = q.eq("currency", filters["currency"])
    rows = q.execute().data or []
    totals: dict[str, float] = {}
    for r in rows:
        cur = r.get("currency") or "USD"
        totals[cur] = round(totals.get(cur, 0.0) + float(r.get("grand_total") or 0), 2)
    return {"total_by_currency": totals, "invoice_count": len(rows)}


def _exec_net_income(db: Client, company_id: str, filters: dict) -> dict:
    base_q = (
        db.table("invoices")
        .select("grand_total, currency, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    base_q = _apply_date_filters(base_q, filters)
    if filters.get("currency"):
        base_q = base_q.eq("currency", filters["currency"])
    rows = base_q.execute().data or []

    income:   dict[str, float] = {}
    spending: dict[str, float] = {}
    for r in rows:
        cur = r.get("currency") or "USD"
        amt = float(r.get("grand_total") or 0)
        if r.get("invoice_type") == "receivable":
            income[cur] = round(income.get(cur, 0.0) + amt, 2)
        else:
            spending[cur] = round(spending.get(cur, 0.0) + amt, 2)

    all_currencies = set(income.keys()) | set(spending.keys())
    net: dict[str, float] = {}
    for cur in all_currencies:
        net[cur] = round(income.get(cur, 0.0) - spending.get(cur, 0.0), 2)

    return {
        "income_by_currency":   income,
        "spending_by_currency": spending,
        "net_by_currency":      net,
        "invoice_count":        len(rows),
    }


def _exec_client_spending(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("grand_total, currency, status, issue_date, clients(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .eq("invoice_type", "receivable")
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("client_name"):
        ids = _resolve_client_ids(db, company_id, filters["client_name"])
        if ids:
            q = q.in_("client_id", ids)
    rows = q.execute().data or []
    client_totals: dict[str, float] = {}
    for r in rows:
        name = (r.get("clients") or {}).get("name") or "Unknown"
        client_totals[name] = round(
            client_totals.get(name, 0.0) + float(r.get("grand_total") or 0), 2
        )
    return [
        {"client_name": k, "total_revenue": v}
        for k, v in sorted(client_totals.items(), key=lambda x: x[1], reverse=True)
    ]


def _exec_vendor_spending(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("grand_total, currency, status, issue_date, vendors(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .eq("invoice_type", "payable")
    )
    q = _apply_date_filters(q, filters)
    if filters.get("status"):
        q = q.eq("status", filters["status"])
    if filters.get("vendor_name"):
        ids = _resolve_vendor_ids(db, company_id, filters["vendor_name"])
        if ids:
            q = q.in_("vendor_id", ids)
    rows = q.execute().data or []
    vendor_totals: dict[str, float] = {}
    for r in rows:
        name = (r.get("vendors") or {}).get("name") or "Unknown"
        vendor_totals[name] = round(
            vendor_totals.get(name, 0.0) + float(r.get("grand_total") or 0), 2
        )
    return [
        {"vendor_name": k, "total_spent": v}
        for k, v in sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)
    ]


def _exec_vendor_count(db: Client, company_id: str, filters: dict) -> dict:
    result = (
        db.table("vendors")
        .select("id", count="exact")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .execute()
    )
    return {"vendor_count": result.count or 0}


def _exec_vendor_balances(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("grand_total, amount_paid_so_far, currency, vendors(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .eq("invoice_type", "payable")
        .in_("status", ["unpaid", "overdue", "partially_paid", "sent"])
    )
    q = _apply_date_filters(q, filters)
    rows = q.execute().data or []
    balances: dict[str, float] = {}
    for r in rows:
        name = (r.get("vendors") or {}).get("name") or "Unknown"
        owed = float(r.get("grand_total") or 0) - float(r.get("amount_paid_so_far") or 0)
        balances[name] = round(balances.get(name, 0.0) + owed, 2)
    return [
        {"vendor_name": k, "outstanding_balance": v}
        for k, v in sorted(balances.items(), key=lambda x: x[1], reverse=True)
    ]


def _exec_client_count(db: Client, company_id: str, filters: dict) -> dict:
    result = (
        db.table("clients")
        .select("id", count="exact")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .execute()
    )
    return {"client_count": result.count or 0}


def _exec_client_balances(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("grand_total, amount_paid_so_far, currency, clients(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .eq("invoice_type", "receivable")
        .in_("status", ["sent", "unpaid", "overdue", "partially_paid"])
    )
    q = _apply_date_filters(q, filters)
    rows = q.execute().data or []
    balances: dict[str, float] = {}
    for r in rows:
        name = (r.get("clients") or {}).get("name") or "Unknown"
        owed = float(r.get("grand_total") or 0) - float(r.get("amount_paid_so_far") or 0)
        balances[name] = round(balances.get(name, 0.0) + owed, 2)
    return [
        {"client_name": k, "outstanding_balance": v}
        for k, v in sorted(balances.items(), key=lambda x: x[1], reverse=True)
    ]


def _exec_overdue_invoices(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("invoices")
        .select("invoice_number, grand_total, amount_paid_so_far, currency, "
                "due_date, issue_date, invoice_type, vendors(name), clients(name)")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
        .eq("status", "overdue")
    )
    if filters.get("date_from"):
        q = q.gte("due_date", filters["date_from"])
    if filters.get("date_to"):
        q = q.lte("due_date", filters["date_to"])
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    if filters.get("vendor_name"):
        ids = _resolve_vendor_ids(db, company_id, filters["vendor_name"])
        if ids:
            q = q.in_("vendor_id", ids)
    if filters.get("client_name"):
        ids = _resolve_client_ids(db, company_id, filters["client_name"])
        if ids:
            q = q.in_("client_id", ids)
    result = q.order("due_date", desc=False).execute()
    log.info(f"overdue raw count: {len(result.data or [])}, filters applied: {filters}")
    return result.data or []

def _exec_monthly_breakdown(db: Client, company_id: str, filters: dict) -> dict:
    q = (
        db.table("invoices")
        .select("issue_date, grand_total, status, invoice_type")
        .eq("company_id", company_id)
        .is_("deleted_at", None)
    )
    q = _apply_date_filters(q, filters)
    if filters.get("invoice_type"):
        q = q.eq("invoice_type", filters["invoice_type"])
    rows = q.execute().data or []
    monthly_count  = Counter()
    monthly_amount = Counter()
    for r in rows:
        d         = (r.get("issue_date") or "")
        month_key = d[:7] if len(d) >= 7 else "unknown"
        monthly_count[month_key]  += 1
        monthly_amount[month_key] += float(r.get("grand_total") or 0)
    return {
        "total_invoices":     len(rows),
        "invoices_per_month": dict(sorted(monthly_count.items())),
        "spending_per_month": {
            k: round(v, 2) for k, v in sorted(monthly_amount.items())
        },
    }


def _exec_payment_history(db: Client, company_id: str, filters: dict) -> list[dict]:
    q = (
        db.table("payments")
        .select("payment_date, amount, method, reference, "
                "invoices(invoice_number, vendors(name), clients(name))")
        .eq("company_id", company_id)
    )
    if filters.get("date_from"):
        q = q.gte("payment_date", filters["date_from"])
    if filters.get("date_to"):
        q = q.lte("payment_date", filters["date_to"])
    limit = filters.get("limit") or 50
    result = q.order("payment_date", desc=True).limit(limit).execute()
    log.info(f"payment_history rows returned: {len(result.data or [])}")
    return result.data or []

def _exec_compliance_summary(db: Client, company_id: str, filters: dict) -> dict:
    rows = (
        db.table("compliance_flags")
        .select("flag_type, severity")
        .eq("company_id", company_id)
        .execute()
        .data or []
    )
    return {
        "total_flags": len(rows),
        "by_type":     dict(Counter(r["flag_type"] for r in rows)),
        "by_severity": dict(Counter(r["severity"]  for r in rows)),
    }


def _exec_top_vendors(db: Client, company_id: str, filters: dict) -> list[dict]:
    return _exec_vendor_spending(db, company_id, filters)


def _exec_avg_payment_delay(db: Client, company_id: str, filters: dict) -> list[dict]:
    try:
        return db.rpc("avg_payment_delay", {"filter_company_id": company_id}).execute().data or []
    except Exception as e:
        log.error(f"avg_payment_delay RPC failed: {e}")
        return []


def _exec_invoice_aging(db: Client, company_id: str, filters: dict) -> list[dict]:
    try:
        return db.rpc("invoice_aging", {"filter_company_id": company_id}).execute().data or []
    except Exception as e:
        log.error(f"invoice_aging RPC failed: {e}")
        return []


# ── Template dispatcher ───────────────────────────────────────────────────────

_TEMPLATE_EXECUTORS = {
    "invoice_count":      _exec_invoice_count,
    "invoice_list":       _exec_invoice_list,
    "total_spending":     _exec_total_spending,
    "total_income":       _exec_total_income,
    "total_revenue":      _exec_total_revenue,
    "net_income":         _exec_net_income,
    "vendor_spending":    _exec_vendor_spending,
    "client_spending":    _exec_client_spending,
    "vendor_count":       _exec_vendor_count,
    "vendor_balances":    _exec_vendor_balances,
    "client_count":       _exec_client_count,
    "client_balances":    _exec_client_balances,
    "overdue_invoices":   _exec_overdue_invoices,
    "monthly_breakdown":  _exec_monthly_breakdown,
    "payment_history":    _exec_payment_history,
    "compliance_summary": _exec_compliance_summary,
    "top_vendors":        _exec_top_vendors,
    "avg_payment_delay":  _exec_avg_payment_delay,
    "invoice_aging":      _exec_invoice_aging,
}


def _run_sql_query(db: Client, company_id: str, question: str) -> tuple:
    """Option C: LLM selects template + extracts filters, executor runs safe query.
    Returns ("__fallback__", "none") when no template matches.
    """
    selection = _select_template(question)
    template  = selection.get("template", "none")
    filters   = selection.get("filters") or {}

    if template == "none":
        log.info("No template matched — falling back to RAG")
        return "__fallback__", "none"

    executor = _TEMPLATE_EXECUTORS.get(template)
    if not executor:
        log.warning(f"No executor for '{template}' — falling back to RAG")
        return "__fallback__", "none"

    try:
        data = executor(db, company_id, filters)
        log.info(f"Template '{template}' executed successfully")
        return data, template
    except Exception as e:
        log.error(f"Template '{template}' failed: {e}")
        return "__fallback__", "none"


def _format_currency_totals(totals: dict[str, float]) -> str:
    if not totals:
        return "0.00"
    return ", ".join(f"{v:,.2f} {k}" for k, v in sorted(totals.items()))


def _python_format(data, template: str) -> str | None:
    """
    Format numeric/aggregation results in Python without LLM involvement.
    Returns a formatted string, or None if the template needs LLM formatting.
    """
    if template == "total_revenue":
        totals = data.get("total_by_currency", {})
        count  = data.get("invoice_count", 0)
        return f"Total revenue (all invoices): {_format_currency_totals(totals)} across {count} invoices."

    if template == "total_spending":
        totals = data.get("total_by_currency", {})
        count  = data.get("invoice_count", 0)
        return f"Total spending: {_format_currency_totals(totals)} across {count} invoices."

    if template == "total_income":
        totals = data.get("total_by_currency", {})
        count  = data.get("invoice_count", 0)
        return f"Total income: {_format_currency_totals(totals)} across {count} invoices."

    if template == "net_income":
        income   = data.get("income_by_currency", {})
        spending = data.get("spending_by_currency", {})
        net      = data.get("net_by_currency", {})
        lines = [
            f"Total income:   {_format_currency_totals(income)}",
            f"Total spending: {_format_currency_totals(spending)}",
            f"Net income:     {_format_currency_totals(net)}",
        ]
        return "\n".join(lines)

    if template == "invoice_count":
        total    = data.get("total", 0)
        by_status = data.get("by_status", {})
        by_type   = data.get("by_type", {})
        status_str = ", ".join(f"{v} {k}" for k, v in sorted(by_status.items())) or "none"
        type_str   = ", ".join(f"{v} {k}" for k, v in sorted(by_type.items())) or "none"
        return f"{total} invoices total — by status: {status_str}; by type: {type_str}."

    if template == "vendor_count":
        return f"{data.get('vendor_count', 0)} vendors."

    if template == "client_count":
        return f"{data.get('client_count', 0)} clients."

    if template == "compliance_summary":
        total     = data.get("total_flags", 0)
        by_sev    = data.get("by_severity", {})
        sev_str   = ", ".join(f"{v} {k}" for k, v in sorted(by_sev.items())) or "none"
        return f"{total} compliance flags — by severity: {sev_str}."

    return None  # fall through to LLM


def _answer_sql(question: str, data, template: str) -> str:
    # Python formatter handles all numeric/aggregation templates — no LLM involvement
    python_answer = _python_format(data, template)
    if python_answer is not None:
        return python_answer

    # LLM formatter for list-based templates (invoice_list, vendor_spending, etc.)
    llm = get_llm_provider()

    if isinstance(data, list) and len(data) > 20:
        data_str = json.dumps({
            "total_count": len(data),
            "showing_first_20": data[:20],
            "note": f"Showing 20 of {len(data)} results"
        }, indent=2)
        row_label = f"{len(data)} rows (summarized)"
    elif isinstance(data, dict):
        data_str  = json.dumps(data, indent=2)
        row_label = "aggregated summary"
    else:
        data_str  = json.dumps(data, indent=2)
        row_label = f"{len(data)} rows"

    return llm.chat(
        messages=[
            {"role": "system", "content": (
                "You are a financial analyst assistant. "
                "Answer the user's question based ONLY on the provided data. "
                "Be concise and precise. Use exact numbers from the data. "
                "For lists, show the top results clearly. "
                "If total_count is provided, mention the total number of results. "
                "If the data includes pre-computed counts or aggregations, "
                "use those numbers directly — do not re-count or re-aggregate. "
                "If data is empty, say no results were found."
            )},
            {"role": "user", "content": (
                f"Question: {question}\n\n"
                f"Query type: {template}\n"
                f"Data ({row_label}):\n{data_str}\n\n"
                "Answer based on this data only."
            )},
        ],
        temperature=0.0,
        max_tokens=512,
    )

# ══════════════════════════════════════════════════════════════════════════════
# RAG PATH (unchanged from v3)
# ══════════════════════════════════════════════════════════════════════════════

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
    try:
        llm      = get_llm_provider()
        response = llm.chat(
            messages=[
                {"role": "system", "content": _MULTI_QUERY_PROMPT},
                {"role": "user",   "content": question},
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
        log.warning(f"Multi-query generation failed: {e}")
    return [question]


def _apply_doc_type_boost(
    chunks: list[RetrievedChunk],
    relevant_doc_types: list[str],
) -> list[RetrievedChunk]:
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
            chunk.metadata["soft_boost_applied"]  = True
            chunk.metadata["original_similarity"] = round(original, 4)
            boosted_count += 1
    if boosted_count > 0:
        log.info(f"Soft boost: {boosted_count} chunks matched {relevant_doc_types}")
    return chunks


_COMPRESSION_PROMPT = """You are a precision text extractor. Given a user question and retrieved document chunks,
extract ONLY the sentences that are directly relevant to answering the question.

Rules:
- Remove irrelevant sentences entirely
- Keep relevant sentences verbatim - do not paraphrase
- Maintain the source labels [Source N] so citations still work
- If a chunk has no relevant content, omit it entirely
- IMPORTANT: Invoice data chunks (containing invoice numbers, amounts, dates, vendor names,
  line items) are ALWAYS relevant when the question asks about invoice compliance,
  verification, or cross-referencing against regulations. Keep them.
- Return the compressed text only, no explanation"""


def _compress_context(question: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    raw_context = "\n\n".join(
        f"[Source {i} - {c.citation}]:\n{c.chunk_text}"
        for i, c in enumerate(chunks, 1)
    )
    try:
        llm = get_llm_provider()
        return llm.chat(
            messages=[
                {"role": "system", "content": _COMPRESSION_PROMPT},
                {"role": "user",   "content": (
                    f"Question: {question}\n\n"
                    f"Chunks:\n{raw_context}\n\n"
                    "Extract only relevant sentences."
                )},
            ],
            temperature=0.0,
            max_tokens=1024,
        ).strip()
    except Exception as e:
        log.warning(f"Compression failed: {e}. Using raw context.")
        return raw_context


def _generate_answer(question: str, compressed_context: str, query_type: str) -> str:
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
            "Do not give legal advice - present the regulations as written."
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
    return llm.chat(
        messages=[
            {"role": "system", "content": system_prompts.get(query_type, system_prompts["rag_invoice"])},
            {"role": "user",   "content": (
                f"Question: {question}\n\n"
                f"Context:\n{compressed_context}\n\n"
                "Answer based on the above context only."
            )},
        ],
        temperature=0.0,
        max_tokens=768,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def handle_query(db: Client, company_id: str, question: str) -> QueryResult:
    """
    Full query pipeline:
    1. Classify intent (keyword pre-filter, no LLM call for obvious cases)
    2. SQL path: LLM picks template + extracts filters -> executor runs safe query
       Falls through to RAG if no template matches
    3. RAG path: multi-query -> embed -> retrieve -> boost -> rerank -> compress -> answer
    """
    question = question.strip()
    if not question:
        return QueryResult(answer="Please provide a question.", sources=[], query_type="none")

    # Step 1: Classify intent
    classification     = classify_intent(question)
    intent             = classification.intent
    relevant_doc_types = classification.relevant_doc_types
    log.info(f"Intent: {intent}, doc_types: {relevant_doc_types}")

    # Step 2: SQL path
    if intent == "sql_aggregation":
        data, template = _run_sql_query(db, company_id, question)
        if data != "__fallback__":
            answer = _answer_sql(question, data, template)
            return QueryResult(answer=answer, sources=[], query_type="sql")
        log.info("SQL fallback: routing to RAG")
        intent = "rag_invoice"

    # Step 3: Multi-query rewrite
    variants      = _generate_query_variants(question)
    log.info(f"Query variants: {variants}")

    # Step 4: Embed
    embedder      = get_embedding_provider()
    query_vectors = embedder.embed(variants)

    # Step 5: Retrieve
    all_chunks: list[RetrievedChunk] = []
    source_names = {
        "rag_invoice":    ["invoices"],
        "rag_compliance": ["regulations"],
        "hybrid":         ["invoices", "regulations"],
    }.get(intent, ["invoices", "regulations"])

    for source_name in source_names:
        source = get_source(source_name)
        if source is None:
            log.warning(f"Source '{source_name}' not in registry")
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

    # Step 6: Soft doc-type boost
    all_chunks = _apply_doc_type_boost(all_chunks, relevant_doc_types)
    all_chunks.sort(key=lambda c: c.similarity, reverse=True)

    # Step 7: Rerank
    if intent == "hybrid" and len(source_names) > 1:
        invoice_chunks    = [c for c in all_chunks if c.source_type == "invoice"]
        regulation_chunks = [c for c in all_chunks if c.source_type != "invoice"]
        slots             = max(2, 6 // len(source_names))
        reranked = (
            rerank_chunks(question, invoice_chunks,    top_n=slots) +
            rerank_chunks(question, regulation_chunks, top_n=slots)
        )
        reranked.sort(key=lambda c: c.similarity, reverse=True)
    else:
        reranked = rerank_chunks(question, all_chunks, top_n=6)

    log.info(f"Chunks after reranking: {len(reranked)}")

    # Step 8: Compress
    compressed = _compress_context(question, reranked)

    # Step 9: Answer
    answer = _generate_answer(question, compressed, intent)

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
