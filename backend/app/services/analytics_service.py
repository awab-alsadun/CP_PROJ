"""
Analytics service.
Fetches data from Supabase, aggregates in Python.
"""

import uuid
from datetime import date, datetime, timedelta
from collections import defaultdict
from statistics import median

from supabase import Client
from app.core.exceptions import DatabaseError


def _parse_date(d) -> date | None:
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _is_outstanding(status: str) -> bool:
    return status in ("sent", "unpaid", "partially_paid", "overdue")


def _is_paid(status: str) -> bool:
    return status == "paid"


def get_dashboard(db: Client, company_id: str) -> dict:
    try:
        invoices_result = (
            db.table("invoices")
            .select("id, invoice_number, issue_date, grand_total, status, "
                    "invoice_type, amount_paid_so_far, confidence_score, "
                    "vendor_id, client_id, created_at")
            .eq("company_id", company_id)
            .is_("deleted_at", None)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch invoices for dashboard", detail=str(e))

    invoices = invoices_result.data or []
    today = date.today()
    first_of_month = today.replace(day=1)

    status_breakdown: dict[str, int] = {}
    type_breakdown = {"payable": 0, "receivable": 0}

    total_payables_outstanding  = 0.0
    total_receivables_outstanding = 0.0
    overdue_count = 0
    paid_this_month = 0.0
    monthly_payable:    dict[str, float] = defaultdict(float)
    monthly_receivable: dict[str, float] = defaultdict(float)

    # For net income
    total_income   = 0.0
    total_spending = 0.0

    # For top client
    client_totals: dict[str, float] = defaultdict(float)

    for inv in invoices:
        status   = inv.get("status", "unpaid")
        inv_type = inv.get("invoice_type", "payable")
        grand_total = float(inv.get("grand_total") or 0)
        paid = float(inv.get("amount_paid_so_far") or 0)
        issue_date = _parse_date(inv.get("issue_date"))

        status_breakdown[status] = status_breakdown.get(status, 0) + 1
        type_breakdown[inv_type] = type_breakdown.get(inv_type, 0) + 1

        # Split outstanding by type
        if _is_outstanding(status):
            remaining = max(0.0, grand_total - paid)
            if inv_type == "payable":
                total_payables_outstanding += remaining
            else:
                total_receivables_outstanding += remaining

        if status == "overdue":
            overdue_count += 1

        if _is_paid(status) and issue_date and issue_date >= first_of_month:
            paid_this_month += grand_total

        if issue_date:
            cutoff = today - timedelta(days=365)
            if issue_date >= cutoff:
                key = _month_key(issue_date)
                if inv_type == "payable":
                    monthly_payable[key] += grand_total
                else:
                    monthly_receivable[key] += grand_total

        # Net income tracking
        if inv_type == "receivable":
            total_income += grand_total
            client_id = inv.get("client_id")
            if client_id:
                client_totals[client_id] += grand_total
        else:
            total_spending += grand_total

    net_income = round(total_income - total_spending, 2)

    all_months = sorted(set(list(monthly_payable.keys()) + list(monthly_receivable.keys())))
    monthly_revenue_list = [
        {
            "month":              m,
            "payable_amount":     round(monthly_payable.get(m, 0.0), 2),
            "receivable_amount":  round(monthly_receivable.get(m, 0.0), 2),
        }
        for m in all_months
    ]

    # Recent invoices
    recent = invoices[:10]
    vendor_ids = list(set(i["vendor_id"] for i in recent if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in recent if i.get("client_id")))

    vendor_names: dict[str, str] = {}
    client_names: dict[str, str] = {}

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
    for inv in recent:
        inv_type = inv.get("invoice_type", "payable")
        if inv_type == "payable":
            entity_name = vendor_names.get(inv.get("vendor_id"), "Unknown Vendor")
        else:
            entity_name = client_names.get(inv.get("client_id"), "Unknown Client")

        recent_invoices.append({
            "id":               inv["id"],
            "invoice_number":   inv["invoice_number"],
            "invoice_type":     inv_type,
            "entity_name":      entity_name,
            "vendor_name":      vendor_names.get(inv.get("vendor_id")),
            "client_name":      client_names.get(inv.get("client_id")),
            "grand_total":      float(inv.get("grand_total") or 0),
            "amount_paid_so_far": float(inv.get("amount_paid_so_far") or 0),
            "status":           inv.get("status"),
            "issue_date":       str(inv.get("issue_date", "")),
            "confidence_score": float(inv.get("confidence_score") or 0),
        })

    # Top client by total receivable invoiced
    top_client = None
    if client_totals:
        top_client_id = max(client_totals, key=client_totals.get)
        top_client_name = client_names.get(top_client_id)
        if not top_client_name:
            try:
                cr = db.table("clients").select("name").eq("id", top_client_id).single().execute()
                top_client_name = (cr.data or {}).get("name", "Unknown")
            except Exception:
                top_client_name = "Unknown"
        top_client = {
            "client_id":    top_client_id,
            "client_name":  top_client_name,
            "total_billed": round(client_totals[top_client_id], 2),
        }

    # Vendor / client counts
    vendor_count = 0
    client_count = 0
    try:
        vcount = db.table("vendors").select("id", count="exact").eq("company_id", company_id).is_("deleted_at", None).execute()
        vendor_count = vcount.count or 0
    except Exception:
        pass
    try:
        ccount = db.table("clients").select("id", count="exact").eq("company_id", company_id).is_("deleted_at", None).execute()
        client_count = ccount.count or 0
    except Exception:
        pass

    return {
        "total_invoices":                  len(invoices),
        "total_payables_outstanding":      round(total_payables_outstanding, 2),
        "total_receivables_outstanding":   round(total_receivables_outstanding, 2),
        "total_outstanding":               round(total_payables_outstanding + total_receivables_outstanding, 2),
        "overdue_count":                   overdue_count,
        "paid_this_month":                 round(paid_this_month, 2),
        "total_income":                    round(total_income, 2),
        "total_spending":                  round(total_spending, 2),
        "net_income":                      net_income,
        "top_client":                      top_client,
        "vendor_count":                    vendor_count,
        "client_count":                    client_count,
        "status_breakdown":                status_breakdown,
        "type_breakdown":                  type_breakdown,
        "monthly_revenue":                 monthly_revenue_list,
        "recent_invoices":                 recent_invoices,
    }


def get_spending(db: Client, company_id: str, months: int = 6) -> dict:
    cutoff = date.today() - timedelta(days=months * 30)
    try:
        result = (
            db.table("invoices")
            .select("vendor_id, grand_total, issue_date")
            .eq("company_id", company_id)
            .eq("invoice_type", "payable")
            .is_("deleted_at", None)
            .gte("issue_date", cutoff.isoformat())
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch spending data", detail=str(e))

    invoices = result.data or []
    vendor_data: dict = defaultdict(lambda: {"total": 0.0, "count": 0, "last_date": None})
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

    sorted_vendors = sorted(vendor_data.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
    vendor_ids = [v[0] for v in sorted_vendors]
    vendor_names: dict[str, str] = {}
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
            "vendor_id":          vid,
            "vendor_name":        vendor_names.get(vid, "Unknown"),
            "total_spent":        round(data["total"], 2),
            "invoice_count":      data["count"],
            "avg_invoice_amount": round(avg, 2),
            "last_invoice_date":  str(data["last_date"]) if data["last_date"] else None,
        })

    return {"period_months": months, "vendors": vendors}


def get_revenue(db: Client, company_id: str, months: int = 6) -> dict:
    cutoff = date.today() - timedelta(days=months * 30)
    try:
        result = (
            db.table("invoices")
            .select("client_id, grand_total, issue_date, status")
            .eq("company_id", company_id)
            .eq("invoice_type", "receivable")
            .is_("deleted_at", None)
            .gte("issue_date", cutoff.isoformat())
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch revenue data", detail=str(e))

    invoices = result.data or []
    client_data: dict = defaultdict(lambda: {"total": 0.0, "paid": 0.0, "count": 0, "last_date": None})
    for inv in invoices:
        cid = inv.get("client_id")
        if not cid:
            continue
        cd = client_data[cid]
        total = float(inv.get("grand_total") or 0)
        cd["total"] += total
        cd["count"] += 1
        if _is_paid(inv.get("status", "")):
            cd["paid"] += total
        inv_date = _parse_date(inv.get("issue_date"))
        if inv_date and (cd["last_date"] is None or inv_date > cd["last_date"]):
            cd["last_date"] = inv_date

    sorted_clients = sorted(client_data.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
    client_ids = [c[0] for c in sorted_clients]
    client_names: dict[str, str] = {}
    if client_ids:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids).execute()
            client_names = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    clients = []
    for cid, data in sorted_clients:
        clients.append({
            "client_id":         cid,
            "client_name":       client_names.get(cid, "Unknown"),
            "total_invoiced":    round(data["total"], 2),
            "total_paid":        round(data["paid"], 2),
            "invoice_count":     data["count"],
            "last_invoice_date": str(data["last_date"]) if data["last_date"] else None,
        })

    return {"period_months": months, "clients": clients}


def get_trends(db: Client, company_id: str, months: int = 12, invoice_type: str | None = None) -> dict:
    cutoff = date.today() - timedelta(days=months * 30)
    try:
        q = (
            db.table("invoices")
            .select("issue_date, grand_total, status, invoice_type")
            .eq("company_id", company_id)
            .is_("deleted_at", None)
            .gte("issue_date", cutoff.isoformat())
        )
        if invoice_type:
            q = q.eq("invoice_type", invoice_type)
        result = q.execute()
    except Exception as e:
        raise DatabaseError("Failed to fetch trends data", detail=str(e))

    invoices = result.data or []
    payable_months:    dict = defaultdict(lambda: {"invoice_count": 0, "total_amount": 0.0, "paid_amount": 0.0})
    receivable_months: dict = defaultdict(lambda: {"invoice_count": 0, "total_amount": 0.0, "paid_amount": 0.0})

    for inv in invoices:
        issue_date = _parse_date(inv.get("issue_date"))
        if not issue_date:
            continue
        key      = _month_key(issue_date)
        total    = float(inv.get("grand_total") or 0)
        inv_type = inv.get("invoice_type", "payable")
        status   = inv.get("status", "unpaid")

        bucket = payable_months[key] if inv_type == "payable" else receivable_months[key]
        bucket["invoice_count"] += 1
        bucket["total_amount"]  += total
        if _is_paid(status):
            bucket["paid_amount"] += total

    def _format(month_dict: dict) -> list[dict]:
        return [
            {
                "month":         m,
                "invoice_count": d["invoice_count"],
                "total_amount":  round(d["total_amount"], 2),
                "paid_amount":   round(d["paid_amount"], 2),
            }
            for m, d in sorted(month_dict.items())
        ]

    return {
        "period_months": months,
        "payables":      _format(payable_months),
        "receivables":   _format(receivable_months),
    }


def get_payment_timing(db: Client, company_id: str) -> dict:
    try:
        inv_result = (
            db.table("invoices")
            .select("id, issue_date, client_id, status")
            .eq("company_id", company_id)
            .eq("invoice_type", "receivable")
            .in_("status", ["paid", "partially_paid"])
            .is_("deleted_at", None)
            .execute()
        )
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

    earliest_payment: dict[str, date] = {}
    for p in payments:
        inv_id = p.get("invoice_id")
        pdate  = _parse_date(p.get("payment_date"))
        if inv_id and pdate:
            if inv_id not in earliest_payment or pdate < earliest_payment[inv_id]:
                earliest_payment[inv_id] = pdate

    days_list: list[int] = []
    client_days: dict[str, list[int]] = defaultdict(list)

    for inv in invoices:
        inv_id     = inv["id"]
        issue_date = _parse_date(inv.get("issue_date"))
        pay_date   = earliest_payment.get(inv_id)
        client_id  = inv.get("client_id")

        if issue_date and pay_date:
            days = (pay_date - issue_date).days
            if days >= 0:
                days_list.append(days)
                if client_id:
                    client_days[client_id].append(days)

    if not days_list:
        return {
            "average_days_to_payment": 0.0,
            "median_days_to_payment":  0.0,
            "fastest_payer":           None,
            "slowest_payer":           None,
            "distribution":            [],
            "trend":                   [],
        }

    avg_days = sum(days_list) / len(days_list)
    med_days = float(median(days_list))

    buckets = [
        ("0-7 days",   0,  7),
        ("8-14 days",  8,  14),
        ("15-30 days", 15, 30),
        ("31-60 days", 31, 60),
        ("60+ days",   61, 99999),
    ]
    distribution = [
        {"range": label, "count": sum(1 for d in days_list if low <= d <= high)}
        for label, low, high in buckets
    ]

    client_avgs = {cid: sum(dlist) / len(dlist) for cid, dlist in client_days.items()}
    fastest_id  = min(client_avgs, key=client_avgs.get) if client_avgs else None
    slowest_id  = max(client_avgs, key=client_avgs.get) if client_avgs else None

    client_ids_to_fetch = [c for c in [fastest_id, slowest_id] if c]
    client_name_map: dict[str, str] = {}
    if client_ids_to_fetch:
        try:
            cr = db.table("clients").select("id, name").in_("id", client_ids_to_fetch).execute()
            client_name_map = {c["id"]: c["name"] for c in (cr.data or [])}
        except Exception:
            pass

    fastest_payer = (
        {"name": client_name_map.get(fastest_id, "Unknown"), "avg_days": round(client_avgs[fastest_id], 1)}
        if fastest_id else None
    )
    slowest_payer = (
        {"name": client_name_map.get(slowest_id, "Unknown"), "avg_days": round(client_avgs[slowest_id], 1)}
        if slowest_id else None
    )

    monthly_days: dict[str, list[int]] = defaultdict(list)
    for inv in invoices:
        inv_id     = inv["id"]
        issue_date = _parse_date(inv.get("issue_date"))
        pay_date   = earliest_payment.get(inv_id)
        if issue_date and pay_date:
            days = (pay_date - issue_date).days
            if days >= 0:
                monthly_days[_month_key(issue_date)].append(days)

    trend = [
        {"month": m, "avg_days": round(sum(dlist) / len(dlist), 1)}
        for m, dlist in sorted(monthly_days.items())
    ]

    return {
        "average_days_to_payment": round(avg_days, 1),
        "median_days_to_payment":  round(med_days, 1),
        "fastest_payer":           fastest_payer,
        "slowest_payer":           slowest_payer,
        "distribution":            distribution,
        "trend":                   trend,
    }


def get_overdue(db: Client, company_id: str) -> dict:
    try:
        result = (
            db.table("invoices")
            .select("id, invoice_number, invoice_type, grand_total, amount_paid_so_far, "
                    "due_date, issue_date, vendor_id, client_id")
            .eq("company_id", company_id)
            .eq("status", "overdue")
            .is_("deleted_at", None)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch overdue data", detail=str(e))

    invoices = result.data or []
    today    = date.today()

    vendor_ids = list(set(i["vendor_id"] for i in invoices if i.get("vendor_id")))
    client_ids = list(set(i["client_id"] for i in invoices if i.get("client_id")))

    vendor_names: dict[str, str] = {}
    client_names: dict[str, str] = {}

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
    days_overdue_list: list[int] = []
    overdue_invoices: list[dict] = []

    for inv in invoices:
        grand_total = float(inv.get("grand_total") or 0)
        amount_paid = float(inv.get("amount_paid_so_far") or 0)
        remaining   = max(0.0, grand_total - amount_paid)
        total_overdue_amount += remaining

        due   = _parse_date(inv.get("due_date"))
        issue = _parse_date(inv.get("issue_date"))
        if not due:
            due = (issue + timedelta(days=30)) if issue else today

        days_over = max(0, (today - due).days)
        days_overdue_list.append(days_over)

        inv_type = inv.get("invoice_type", "payable")
        entity_name = (
            vendor_names.get(inv.get("vendor_id"), "Unknown Vendor")
            if inv_type == "payable"
            else client_names.get(inv.get("client_id"), "Unknown Client")
        )

        overdue_invoices.append({
            "id":               inv["id"],
            "invoice_number":   inv["invoice_number"],
            "invoice_type":     inv_type,
            "entity_name":      entity_name,
            "grand_total":      grand_total,
            "amount_paid_so_far": amount_paid,
            "remaining_balance":  round(remaining, 2),
            "due_date":         str(due) if due else None,
            "days_overdue":     days_over,
            "issue_date":       str(inv.get("issue_date", "")),
        })

    overdue_invoices.sort(key=lambda x: x["days_overdue"], reverse=True)
    avg_days = sum(days_overdue_list) / len(days_overdue_list) if days_overdue_list else 0.0

    aging_config = [
        ("1-30 days",  1,  30),
        ("31-60 days", 31, 60),
        ("61-90 days", 61, 90),
        ("90+ days",   91, 99999),
    ]
    aging_buckets = [
        {
            "range":  label,
            "count":  sum(1 for i in overdue_invoices if low <= i["days_overdue"] <= high),
            "amount": round(sum(
                i["remaining_balance"] for i in overdue_invoices if low <= i["days_overdue"] <= high
            ), 2),
        }
        for label, low, high in aging_config
    ]

    return {
        "total_overdue_amount": round(total_overdue_amount, 2),
        "overdue_count":        len(invoices),
        "avg_days_overdue":     round(avg_days, 1),
        "overdue_invoices":     overdue_invoices,
        "aging_buckets":        aging_buckets,
    }


def get_system_stats(db: Client, company_id: str) -> dict:
    counts: dict[str, int] = {}

    for key, table, soft_delete in [
        ("total_invoices", "invoices", True),
        ("total_vendors",  "vendors",  True),
        ("total_clients",  "clients",  True),
    ]:
        try:
            q = db.table(table).select("id", count="exact").eq("company_id", company_id)
            if soft_delete:
                q = q.is_("deleted_at", None)
            counts[key] = q.execute().count or 0
        except Exception:
            counts[key] = 0

    for inv_type in ("payable", "receivable"):
        try:
            q = (
                db.table("invoices")
                .select("id", count="exact")
                .eq("company_id", company_id)
                .eq("invoice_type", inv_type)
                .is_("deleted_at", None)
            )
            counts[f"total_{inv_type}s"] = q.execute().count or 0
        except Exception:
            counts[f"total_{inv_type}s"] = 0

    try:
        counts["total_embeddings"] = (
            db.table("invoice_embeddings")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .execute()
            .count or 0
        )
    except Exception:
        counts["total_embeddings"] = 0

    try:
        result = (
            db.table("company_documents")
            .select("document_id")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )
        doc_ids = set(r["document_id"] for r in (result.data or []) if r.get("document_id"))
        counts["total_documents"]       = len(doc_ids)
        counts["total_document_chunks"] = len(result.data or [])
    except Exception:
        counts["total_documents"]       = 0
        counts["total_document_chunks"] = 0

    # Aliases for dashboard cards
    counts["vendor_count"] = counts.get("total_vendors", 0)
    counts["client_count"] = counts.get("total_clients", 0)
    counts["embedding_count"] = counts.get("total_embeddings", 0)
    counts["document_count"]  = counts.get("total_documents", 0)

    return counts


def get_page_metrics(db: Client, company_id: str, invoice_type: str) -> dict:
    """
    Stable metric card values for Payables or Receivables page.
    Aggregated server-side — never changes with filter/search/page.
    invoice_type: 'payable' | 'receivable'
    """
    try:
        result = (
            db.table("invoices")
            .select("status, grand_total, amount_paid_so_far")
            .eq("company_id", company_id)
            .eq("invoice_type", invoice_type)
            .is_("deleted_at", None)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch page metrics", detail=str(e))

    rows = result.data or []

    total_count    = len(rows)
    overdue_count  = 0
    draft_count    = 0
    outstanding    = 0.0
    sent_amt       = 0.0
    unpaid_amt     = 0.0

    for r in rows:
        status      = r.get("status", "")
        grand_total = float(r.get("grand_total") or 0)
        paid        = float(r.get("amount_paid_so_far") or 0)
        remaining   = max(0.0, grand_total - paid)

        if status == "overdue":
            overdue_count += 1
        if status == "draft":
            draft_count += 1
        if status in ("sent", "unpaid", "partially_paid", "overdue"):
            outstanding += remaining
        if status == "sent":
            sent_amt += grand_total
        if status in ("unpaid", "partially_paid", "overdue"):
            unpaid_amt += remaining

    result = {
        "total_count":   total_count,
        "overdue_count": overdue_count,
        "outstanding":   round(outstanding, 2),
    }

    if invoice_type == "receivable":
        result["draft_count"] = draft_count
        result["sent_amt"]    = round(sent_amt, 2)
    else:
        result["unpaid_amt"] = round(unpaid_amt, 2)

    return result