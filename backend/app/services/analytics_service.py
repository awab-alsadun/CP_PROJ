"""
Analytics service.
Fetches data from Supabase, aggregates in Python.
Fine for 250-500 invoices. For 10k+ you'd move to SQL functions.
"""

import uuid
from datetime import date, datetime, timedelta
from collections import defaultdict
from statistics import median

from supabase import Client
from app.core.exceptions import DatabaseError


def _parse_date(d) -> date | None:
    """Parse a date from Supabase — could be string or date object."""
    if d is None:
        return None
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _month_key(d: date) -> str:
    """Format date as YYYY-MM."""
    return d.strftime("%Y-%m")


def get_dashboard(db: Client, company_id: str) -> dict:
    """Everything the dashboard page needs in one response."""
    try:
        invoices_result = (
            db.table("invoices")
            .select("id, invoice_number, issue_date, grand_total, status, "
                     "confidence_score, vendor_id, client_id, created_at")
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch invoices for dashboard", detail=str(e))

    invoices = invoices_result.data or []
    today = date.today()
    first_of_month = today.replace(day=1)

    # Status breakdown
    status_breakdown = {"draft": 0, "sent": 0, "paid": 0, "overdue": 0}
    total_outstanding = 0.0
    overdue_count = 0
    paid_this_month = 0.0
    monthly_revenue = defaultdict(float)

    for inv in invoices:
        status = inv.get("status", "draft")
        grand_total = float(inv.get("grand_total") or 0)
        issue_date = _parse_date(inv.get("issue_date"))

        status_breakdown[status] = status_breakdown.get(status, 0) + 1

        if status in ("sent", "overdue"):
            total_outstanding += grand_total
        if status == "overdue":
            overdue_count += 1
        if status == "paid" and issue_date and issue_date >= first_of_month:
            paid_this_month += grand_total

        # Monthly revenue (last 12 months)
        if issue_date:
            cutoff = today - timedelta(days=365)
            if issue_date >= cutoff:
                monthly_revenue[_month_key(issue_date)] += grand_total

    # Sort monthly revenue by month
    sorted_months = sorted(monthly_revenue.items())
    monthly_revenue_list = [{"month": m, "amount": round(a, 2)} for m, a in sorted_months]

    # Recent invoices with vendor/client names
    recent_ids = invoices[:10]
    vendor_ids = list(set(i["vendor_id"] for i in recent_ids if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in recent_ids if i.get("client_id")))

    vendor_names = {}
    client_names = {}

    if vendor_ids:
        try:
            vr = db.table("vendors").select("id, name").in_("id", vendor_ids).execute()
            vendor_names = {v["id"]: v["name"] for v in (vr.data or [])}
        except Exception:
            pass

    if client_ids:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids).execute()
            client_names = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    recent_invoices = []
    for inv in recent_ids:
        recent_invoices.append({
            "id": inv["id"],
            "invoice_number": inv["invoice_number"],
            "vendor_name": vendor_names.get(inv.get("vendor_id"), "Unknown"),
            "client_name": client_names.get(inv.get("client_id"), "Unknown"),
            "grand_total": float(inv.get("grand_total") or 0),
            "status": inv.get("status", "draft"),
            "issue_date": str(inv.get("issue_date", "")),
            "confidence_score": float(inv.get("confidence_score") or 0),
        })

    return {
        "total_invoices": len(invoices),
        "total_outstanding": round(total_outstanding, 2),
        "overdue_count": overdue_count,
        "paid_this_month": round(paid_this_month, 2),
        "status_breakdown": status_breakdown,
        "monthly_revenue": monthly_revenue_list,
        "recent_invoices": recent_invoices,
    }


def get_spending(db: Client, company_id: str, months: int = 6) -> dict:
    """Top 10 vendors by total spending."""
    cutoff = date.today() - timedelta(days=months * 30)

    try:
        result = (
            db.table("invoices")
            .select("vendor_id, grand_total, issue_date")
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .gte("issue_date", cutoff.isoformat())
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch spending data", detail=str(e))

    invoices = result.data or []

    # Group by vendor
    vendor_data = defaultdict(lambda: {"total": 0.0, "count": 0, "last_date": None})
    for inv in invoices:
        vid = inv.get("vendor_id")
        if not vid:
            continue
        vd = vendor_data[vid]
        vd["total"] += float(inv.get("grand_total") or 0)
        vd["count"] += 1
        inv_date = _parse_date(inv.get("issue_date"))
        if inv_date and (vd["last_date"] is None or inv_date > vd["last_date"]):
            vd["last_date"] = inv_date

    # Sort by total, top 10
    sorted_vendors = sorted(vendor_data.items(), key=lambda x: x[1]["total"], reverse=True)[:10]

    # Fetch vendor names
    vendor_ids = [v[0] for v in sorted_vendors]
    vendor_names = {}
    if vendor_ids:
        try:
            vr = db.table("vendors").select("id, name").in_("id", vendor_ids).execute()
            vendor_names = {v["id"]: v["name"] for v in (vr.data or [])}
        except Exception:
            pass

    vendors = []
    for vid, data in sorted_vendors:
        avg = data["total"] / data["count"] if data["count"] > 0 else 0
        vendors.append({
            "vendor_id": vid,
            "vendor_name": vendor_names.get(vid, "Unknown"),
            "total_spent": round(data["total"], 2),
            "invoice_count": data["count"],
            "avg_invoice_amount": round(avg, 2),
            "last_invoice_date": str(data["last_date"]) if data["last_date"] else None,
        })

    return {
        "period_months": months,
        "vendors": vendors,
    }


def get_trends(db: Client, company_id: str, months: int = 12) -> dict:
    """Monthly invoice volume and amounts."""
    cutoff = date.today() - timedelta(days=months * 30)

    try:
        result = (
            db.table("invoices")
            .select("issue_date, grand_total, status")
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .gte("issue_date", cutoff.isoformat())
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch trends data", detail=str(e))

    invoices = result.data or []

    month_data = defaultdict(lambda: {
        "invoice_count": 0, "total_amount": 0.0,
        "paid_amount": 0.0, "outstanding_amount": 0.0,
    })

    for inv in invoices:
        issue_date = _parse_date(inv.get("issue_date"))
        if not issue_date:
            continue
        key = _month_key(issue_date)
        total = float(inv.get("grand_total") or 0)
        status = inv.get("status", "draft")

        md = month_data[key]
        md["invoice_count"] += 1
        md["total_amount"] += total
        if status == "paid":
            md["paid_amount"] += total
        elif status in ("sent", "overdue", "draft"):
            md["outstanding_amount"] += total

    sorted_months = sorted(month_data.items())
    months_list = []
    for m, d in sorted_months:
        months_list.append({
            "month": m,
            "invoice_count": d["invoice_count"],
            "total_amount": round(d["total_amount"], 2),
            "paid_amount": round(d["paid_amount"], 2),
            "outstanding_amount": round(d["outstanding_amount"], 2),
        })

    return {
        "period_months": months,
        "months": months_list,
    }


def get_payment_timing(db: Client, company_id: str) -> dict:
    """Payment speed analysis."""
    try:
        # Get paid invoices
        inv_result = (
            db.table("invoices")
            .select("id, issue_date, client_id")
            .eq("company_id", company_id)
            .eq("status", "paid")
            .is_("deleted_at", "null")
            .execute()
        )
        # Get all payments
        pay_result = (
            db.table("payments")
            .select("invoice_id, payment_date")
            .eq("company_id", company_id)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch payment timing data", detail=str(e))

    invoices = inv_result.data or []
    payments = pay_result.data or []

    # Build earliest payment per invoice
    earliest_payment = {}
    for p in payments:
        inv_id = p.get("invoice_id")
        pdate = _parse_date(p.get("payment_date"))
        if inv_id and pdate:
            if inv_id not in earliest_payment or pdate < earliest_payment[inv_id]:
                earliest_payment[inv_id] = pdate

    # Compute days to payment per invoice
    days_list = []
    client_days = defaultdict(list)

    for inv in invoices:
        inv_id = inv["id"]
        issue_date = _parse_date(inv.get("issue_date"))
        pay_date = earliest_payment.get(inv_id)
        client_id = inv.get("client_id")

        if issue_date and pay_date:
            days = (pay_date - issue_date).days
            if days >= 0:
                days_list.append(days)
                if client_id:
                    client_days[client_id].append(days)

    if not days_list:
        return {
            "average_days_to_payment": 0.0,
            "median_days_to_payment": 0.0,
            "fastest_payer": None,
            "slowest_payer": None,
            "distribution": [],
            "trend": [],
        }

    avg_days = sum(days_list) / len(days_list)
    med_days = float(median(days_list))

    # Distribution buckets
    buckets = [
        ("0-7 days", 0, 7),
        ("8-14 days", 8, 14),
        ("15-30 days", 15, 30),
        ("31-60 days", 31, 60),
        ("60+ days", 61, 99999),
    ]
    distribution = []
    for label, low, high in buckets:
        count = sum(1 for d in days_list if low <= d <= high)
        distribution.append({"range": label, "count": count})

    # Fastest/slowest payer
    client_avgs = {}
    for cid, dlist in client_days.items():
        client_avgs[cid] = sum(dlist) / len(dlist)

    fastest_id = min(client_avgs, key=client_avgs.get) if client_avgs else None
    slowest_id = max(client_avgs, key=client_avgs.get) if client_avgs else None

    # Fetch client names
    client_ids_to_fetch = [c for c in [fastest_id, slowest_id] if c]
    client_name_map = {}
    if client_ids_to_fetch:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids_to_fetch).execute()
            client_name_map = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    fastest_payer = None
    slowest_payer = None
    if fastest_id:
        fastest_payer = {
            "name": client_name_map.get(fastest_id, "Unknown"),
            "avg_days": round(client_avgs[fastest_id], 1),
        }
    if slowest_id:
        slowest_payer = {
            "name": client_name_map.get(slowest_id, "Unknown"),
            "avg_days": round(client_avgs[slowest_id], 1),
        }

    # Monthly trend
    monthly_days = defaultdict(list)
    for inv in invoices:
        inv_id = inv["id"]
        issue_date = _parse_date(inv.get("issue_date"))
        pay_date = earliest_payment.get(inv_id)
        if issue_date and pay_date:
            days = (pay_date - issue_date).days
            if days >= 0:
                monthly_days[_month_key(issue_date)].append(days)

    trend = []
    for m in sorted(monthly_days):
        dlist = monthly_days[m]
        trend.append({
            "month": m,
            "avg_days": round(sum(dlist) / len(dlist), 1),
        })

    return {
        "average_days_to_payment": round(avg_days, 1),
        "median_days_to_payment": round(med_days, 1),
        "fastest_payer": fastest_payer,
        "slowest_payer": slowest_payer,
        "distribution": distribution,
        "trend": trend,
    }


def get_overdue(db: Client, company_id: str) -> dict:
    """Overdue invoice analysis."""
    try:
        result = (
            db.table("invoices")
            .select("id, invoice_number, grand_total, due_date, issue_date, "
                     "vendor_id, client_id")
            .eq("company_id", company_id)
            .eq("status", "overdue")
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch overdue data", detail=str(e))

    invoices = result.data or []
    today = date.today()

    # Fetch vendor/client names
    vendor_ids = list(set(i["vendor_id"] for i in invoices if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in invoices if i.get("client_id")))

    vendor_names = {}
    client_names = {}
    if vendor_ids:
        try:
            vr = db.table("vendors").select("id, name").in_("id", vendor_ids).execute()
            vendor_names = {v["id"]: v["name"] for v in (vr.data or [])}
        except Exception:
            pass
    if client_ids:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids).execute()
            client_names = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    total_overdue_amount = 0.0
    days_overdue_list = []
    overdue_invoices = []

    for inv in invoices:
        grand_total = float(inv.get("grand_total") or 0)
        total_overdue_amount += grand_total

        due = _parse_date(inv.get("due_date"))
        issue = _parse_date(inv.get("issue_date"))

        # If no due_date, assume issue_date + 30
        if not due:
            if issue:
                due = issue + timedelta(days=30)
            else:
                due = today  # fallback

        days_over = (today - due).days
        if days_over < 0:
            days_over = 0
        days_overdue_list.append(days_over)

        overdue_invoices.append({
            "id": inv["id"],
            "invoice_number": inv["invoice_number"],
            "vendor_name": vendor_names.get(inv.get("vendor_id"), "Unknown"),
            "client_name": client_names.get(inv.get("client_id"), "Unknown"),
            "grand_total": grand_total,
            "due_date": str(due) if due else None,
            "days_overdue": days_over,
            "issue_date": str(inv.get("issue_date", "")),
        })

    # Sort by days overdue descending
    overdue_invoices.sort(key=lambda x: x["days_overdue"], reverse=True)

    avg_days = sum(days_overdue_list) / len(days_overdue_list) if days_overdue_list else 0.0

    # Aging buckets
    aging_config = [
        ("1-30 days", 1, 30),
        ("31-60 days", 31, 60),
        ("61-90 days", 61, 90),
        ("90+ days", 91, 99999),
    ]
    aging_buckets = []
    for label, low, high in aging_config:
        matching = [inv for inv in overdue_invoices if low <= inv["days_overdue"] <= high]
        aging_buckets.append({
            "range": label,
            "count": len(matching),
            "amount": round(sum(i["grand_total"] for i in matching), 2),
        })

    return {
        "total_overdue_amount": round(total_overdue_amount, 2),
        "overdue_count": len(invoices),
        "avg_days_overdue": round(avg_days, 1),
        "overdue_invoices": overdue_invoices,
        "aging_buckets": aging_buckets,
    }


def get_system_stats(db: Client, company_id: str) -> dict:
    """System-wide entity counts."""
    counts = {}

    queries = {
        "total_invoices": ("invoices", "id", {"deleted_at": "null"}),
        "total_vendors": ("vendors", "id", {"deleted_at": "null"}),
        "total_clients": ("clients", "id", {"deleted_at": "null"}),
    }

    for key, (table, col, filters) in queries.items():
        try:
            q = db.table(table).select(col, count="exact").eq("company_id", company_id)
            for fk, fv in filters.items():
                q = q.is_(fk, fv)
            result = q.execute()
            counts[key] = result.count or 0
        except Exception:
            counts[key] = 0

    # Embeddings
    try:
        result = (
            db.table("invoice_embeddings")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .execute()
        )
        counts["total_embeddings"] = result.count or 0
    except Exception:
        counts["total_embeddings"] = 0

    # Documents
    try:
        result = (
            db.table("company_documents")
            .select("document_id", count="exact")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )
        counts["total_document_chunks"] = result.count or 0

        # Distinct document count — fetch document_ids and count unique
        result2 = (
            db.table("company_documents")
            .select("document_id")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )
        doc_ids = set(r["document_id"] for r in (result2.data or []) if r.get("document_id"))
        counts["total_documents"] = len(doc_ids)
    except Exception:
        counts["total_documents"] = 0
        counts["total_document_chunks"] = 0

    return counts