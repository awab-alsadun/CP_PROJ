from fastapi import APIRouter, Query
from typing import Optional
from app.core.supabase import get_supabase
from app.core.config import get_settings

router = APIRouter(prefix="/reports", tags=["reports"])

COMPANY_ID = "7bf697fc-7220-40c7-9678-542d624d22ad"


def get_period_sql(period: str) -> str:
    if period == "monthly":
        return "DATE_TRUNC('month', {col}::date)"
    elif period == "quarterly":
        return "DATE_TRUNC('quarter', {col}::date)"
    else:
        return "DATE_TRUNC('year', {col}::date)"


def format_label(period: str, date_str: str) -> str:
    from datetime import datetime
    dt = datetime.fromisoformat(date_str[:10])
    if period == "monthly":
        return dt.strftime("%b %Y")
    elif period == "quarterly":
        q = (dt.month - 1) // 3 + 1
        return f"Q{q} {dt.year}"
    else:
        return str(dt.year)


@router.get("/income-statement")
def income_statement(
    period: str = Query(default="monthly", pattern="^(monthly|quarterly|annual)$"),
    year: Optional[int] = Query(default=None),
):
    db = get_supabase()

    year_filter = f"AND EXTRACT(year FROM issue_date::date) = {year}" if year and period != "annual" else ""
    trunc = get_period_sql(period).format(col="issue_date")

    query = f"""
        SELECT
            {trunc} AS period_start,
            SUM(CASE WHEN invoice_type = 'receivable' THEN grand_total ELSE 0 END) AS revenue,
            SUM(CASE WHEN invoice_type = 'payable'    THEN grand_total ELSE 0 END) AS expenses
        FROM invoices
        WHERE company_id = '{COMPANY_ID}'
        AND status NOT IN ('draft')
        AND deleted_at IS NULL
        AND issue_date IS NOT NULL
        {year_filter}
        GROUP BY {trunc}
        ORDER BY {trunc} ASC
    """

    result = db.rpc("exec_sql", {"query": query}).execute() if False else None

    raw = db.table("invoices").select(
        "invoice_type, grand_total, issue_date, status"
    ).eq("company_id", COMPANY_ID).not_.in_("status", ["draft"]).is_("deleted_at", "null").execute()

    from datetime import datetime
    from collections import defaultdict

    def get_bucket(date_str):
        dt = datetime.fromisoformat(date_str[:10])
        if period == "monthly":
            return dt.strftime("%Y-%m-01")
        elif period == "quarterly":
            q = (dt.month - 1) // 3
            month = q * 3 + 1
            return f"{dt.year}-{month:02d}-01"
        else:
            return f"{dt.year}-01-01"

    buckets = defaultdict(lambda: {"revenue": 0.0, "expenses": 0.0})

    for row in raw.data:
        if not row.get("issue_date") or not row.get("grand_total"):
            continue
        if year and period != "annual":
            row_year = int(row["issue_date"][:4])
            if row_year != year:
                continue
        bucket = get_bucket(row["issue_date"])
        if row["invoice_type"] == "receivable":
            buckets[bucket]["revenue"] += float(row["grand_total"] or 0)
        else:
            buckets[bucket]["expenses"] += float(row["grand_total"] or 0)

    rows = []
    total_revenue = 0.0
    total_expenses = 0.0

    for bucket_key in sorted(buckets.keys()):
        rev = round(buckets[bucket_key]["revenue"], 2)
        exp = round(buckets[bucket_key]["expenses"], 2)
        net = round(rev - exp, 2)
        total_revenue += rev
        total_expenses += exp
        rows.append({
            "label": format_label(period, bucket_key),
            "period_start": bucket_key,
            "revenue": rev,
            "expenses": exp,
            "net_income": net,
        })

    return {
        "period": period,
        "year": year,
        "rows": rows,
        "totals": {
            "revenue": round(total_revenue, 2),
            "expenses": round(total_expenses, 2),
            "net_income": round(total_revenue - total_expenses, 2),
        }
    }


@router.get("/cash-flow")
def cash_flow(
    period: str = Query(default="monthly", pattern="^(monthly|quarterly|annual)$"),
    year: Optional[int] = Query(default=None),
):
    db = get_supabase()

    raw = db.table("payments").select(
        "amount, payment_date, invoice_id, invoices(invoice_type)"
    ).eq("company_id", COMPANY_ID).execute()

    from datetime import datetime
    from collections import defaultdict

    def get_bucket(date_str):
        dt = datetime.fromisoformat(date_str[:10])
        if period == "monthly":
            return dt.strftime("%Y-%m-01")
        elif period == "quarterly":
            q = (dt.month - 1) // 3
            month = q * 3 + 1
            return f"{dt.year}-{month:02d}-01"
        else:
            return f"{dt.year}-01-01"

    def format_label(date_str):
        dt = datetime.fromisoformat(date_str[:10])
        if period == "monthly":
            return dt.strftime("%b %Y")
        elif period == "quarterly":
            q = (dt.month - 1) // 3 + 1
            return f"Q{q} {dt.year}"
        else:
            return str(dt.year)

    buckets = defaultdict(lambda: {"cash_in": 0.0, "cash_out": 0.0})

    for row in raw.data:
        if not row.get("payment_date") or not row.get("amount"):
            continue
        if year and period != "annual":
            row_year = int(row["payment_date"][:4])
            if row_year != year:
                continue
        invoice = row.get("invoices") or {}
        invoice_type = invoice.get("invoice_type") if isinstance(invoice, dict) else None
        if not invoice_type:
            continue
        bucket = get_bucket(row["payment_date"])
        if invoice_type == "receivable":
            buckets[bucket]["cash_in"] += float(row["amount"] or 0)
        else:
            buckets[bucket]["cash_out"] += float(row["amount"] or 0)

    rows = []
    total_in = 0.0
    total_out = 0.0

    for bucket_key in sorted(buckets.keys()):
        ci = round(buckets[bucket_key]["cash_in"], 2)
        co = round(buckets[bucket_key]["cash_out"], 2)
        net = round(ci - co, 2)
        total_in += ci
        total_out += co
        rows.append({
            "label": format_label(bucket_key),
            "period_start": bucket_key,
            "cash_in": ci,
            "cash_out": co,
            "net_cash": net,
        })

    return {
        "period": period,
        "year": year,
        "rows": rows,
        "totals": {
            "cash_in": round(total_in, 2),
            "cash_out": round(total_out, 2),
            "net_cash": round(total_in - total_out, 2),
        }
    }