"""
K4Y Database Seed Script
=========================
Reads dataset.json and inserts all records into Supabase.
Handles: company, vendors, clients, addresses, invoices, line_items,
         payments, invoice_raw_documents, compliance_flags, notifications, audit_logs.

DESTRUCTIVE: Truncates all tables first. Rerunnable.

Usage:
  cd backend
  venv\Scripts\activate
  python scripts/seed_database.py

Requires .env with SUPABASE_URL and SUPABASE_SERVICE_KEY.
"""

import json
import sys
import uuid
import logging
from pathlib import Path
from datetime import datetime, date

# Path setup
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATASET_DIR = SCRIPT_DIR.parent.parent  # CP_PROJ root level
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

import os
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── Config ─────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
DATASET_FILE = Path(__file__).parent.parent.parent / "sample_data" / "dataset.json"

# If dataset.json is next to generate_dataset.py instead
if not DATASET_FILE.exists():
    alt = Path(__file__).parent.parent.parent / "dataset_gen" / "dataset.json"
    if alt.exists():
        DATASET_FILE = alt

assert SUPABASE_URL, "SUPABASE_URL not set in .env"
assert SUPABASE_KEY, "SUPABASE_SERVICE_KEY not set in .env"


def uid():
    return str(uuid.uuid4())


def now_str():
    return datetime.utcnow().isoformat()


# ─── Truncate ───────────────────────────────────────────────────────────────

TRUNCATE_ORDER = [
    "invoice_embeddings",
    "document_chunks",
    "company_documents",
    "compliance_flags",
    "notifications",
    "audit_logs",
    "credit_notes",
    "refunds",
    "payments",
    "line_items",
    "invoice_raw_documents",
    "invoices",
    "addresses",
    "clients",
    "vendors",
    "companies",
]


def truncate_all(db):
    log.info("Truncating all tables...")
    for table in TRUNCATE_ORDER:
        try:
            # Delete all rows (TRUNCATE not available via SDK)
            db.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            log.info(f"  Cleared {table}")
        except Exception as e:
            log.warning(f"  Could not clear {table}: {e}")


# ─── Insert helpers ─────────────────────────────────────────────────────────

def insert_batch(db, table, rows, batch_size=50):
    """Insert rows in batches."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            db.table(table).insert(batch).execute()
            total += len(batch)
        except Exception as e:
            log.error(f"  Failed batch {i}-{i+len(batch)} in {table}: {e}")
            # Try one by one
            for row in batch:
                try:
                    db.table(table).insert(row).execute()
                    total += 1
                except Exception as e2:
                    log.error(f"  Failed single row in {table}: {e2}")
                    log.error(f"  Row: {json.dumps(row)[:200]}")
    return total


# ─── Main seed ──────────────────────────────────────────────────────────────

def main():
    log.info(f"Loading dataset from {DATASET_FILE}")
    with open(DATASET_FILE) as f:
        data = json.load(f)

    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Step 0: Truncate
    truncate_all(db)

    company = data["company"]
    vendors = data["vendors"]
    clients = data["clients"]
    payables = data["payables"]
    receivables = data["receivables"]
    issues = data["compliance_issues"]

    # Step 1: Company
    log.info("Inserting company...")
    db.table("companies").insert({
        "id": company["id"],
        "name": company["name"],
        "domain": company["domain"],
        "country": company["country"],
        "address": company["address"],
        "phone": company["phone"],
        "email": company["email"],
        "tax_id": company["tax_id"],
        "default_tax_rate": company["default_tax_rate"],
        "logo_url": company.get("logo_url"),
    }).execute()
    log.info("  Company inserted")

    # Step 2: Vendors + addresses
    log.info("Inserting vendors and addresses...")
    vendor_id_map = {}  # vendor_idx -> vendor_id
    for idx, v in enumerate(vendors):
        vid = uid()
        addr = v["address"]
        aid = uid()

        db.table("addresses").insert({
            "id": aid,
            "company_id": company["id"],
            "street": addr["street"],
            "city": addr["city"],
            "state": addr.get("state"),
            "postal_code": addr["postal_code"],
            "country": addr["country"],
        }).execute()

        db.table("vendors").insert({
            "id": vid,
            "company_id": company["id"],
            "name": v["name"],
            "email": v["email"],
            "phone": v["phone"],
            "tax_id": v["tax_id"],
        }).execute()

        vendor_id_map[idx] = {"vendor_id": vid, "address_id": aid}
    log.info(f"  {len(vendors)} vendors + addresses inserted")

    # Step 3: Clients + addresses
    log.info("Inserting clients and addresses...")
    client_id_map = {}  # client_idx -> client_id
    for idx, cl in enumerate(clients):
        cid = uid()
        addr = cl["address"]
        aid = uid()

        db.table("addresses").insert({
            "id": aid,
            "company_id": company["id"],
            "street": addr["street"],
            "city": addr["city"],
            "state": addr.get("state"),
            "postal_code": addr["postal_code"],
            "country": addr["country"],
        }).execute()

        # Check for missing email compliance issue
        client_email = cl["email"]

        db.table("clients").insert({
            "id": cid,
            "company_id": company["id"],
            "name": cl["name"],
            "email": client_email,
            "phone": cl["phone"],
            "tax_id": cl["tax_id"],
        }).execute()

        client_id_map[idx] = {"client_id": cid, "address_id": aid}
    log.info(f"  {len(clients)} clients + addresses inserted")

    # Step 4: Payable invoices
    log.info("Inserting payable invoices...")
    invoice_rows = []
    line_item_rows = []
    payment_rows = []
    raw_doc_rows = []
    notification_rows = []
    audit_rows = []

    for inv in payables:
        v_map = vendor_id_map[inv["vendor_idx"]]

        inv_row = {
            "id": inv["id"],
            "company_id": company["id"],
            "invoice_number": inv["invoice_number"],
            "invoice_type": "payable",
            "issue_date": inv["issue_date"],
            "due_date": inv["due_date"],
            "currency": inv["currency"],
            "tax_percent": inv["tax_percent"],
            "subtotal": inv["subtotal"],
            "total_tax": inv["total_tax"],
            "grand_total": inv["grand_total"],
            "discount": inv["discount"],
            "status": inv["status"],
            "amount_paid_so_far": inv["amount_paid_so_far"],
            "confidence_score": inv["confidence_score"],
            "payment_method": inv.get("payment_method"),
            "description": inv.get("description"),
            "vendor_id": v_map["vendor_id"],
            "client_id": None,
            "vendor_address_id": v_map["address_id"],
            "client_address_id": None,
        }
        invoice_rows.append(inv_row)

        for li in inv["line_items"]:
            line_item_rows.append({
                "id": uid(),
                "company_id": company["id"],
                "invoice_id": inv["id"],
                "description": li["description"],
                "quantity": li["quantity"],
                "unit_price": li["unit_price"],
                "line_subtotal": li["line_subtotal"],
                "discount": li.get("discount", 0),
            })

        for pay in inv.get("payments", []):
            payment_rows.append({
                "id": uid(),
                "company_id": company["id"],
                "invoice_id": inv["id"],
                "payment_date": pay["payment_date"],
                "amount": pay["amount"],
                "method": pay.get("method"),
                "reference": pay.get("reference"),
            })

        # Raw document placeholder (actual extraction happens via ingestion pipeline)
        raw_doc_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "invoice_id": inv["id"],
            "raw_text": f"Invoice {inv['invoice_number']} from {inv['vendor_name']}",
            "extraction_json": json.dumps({
                "schema_version": "1.0",
                "invoice": {
                    "invoice_number": inv["invoice_number"],
                    "issue_date": inv["issue_date"],
                    "due_date": inv["due_date"],
                    "currency": inv["currency"],
                    "grand_total": inv["grand_total"],
                    "subtotal": inv["subtotal"],
                    "total_tax": inv["total_tax"],
                    "tax_percent": inv["tax_percent"],
                    "status": inv["status"],
                },
                "vendor": {"name": inv["vendor_name"]},
                "client": {"name": "K4Y"},
                "line_items": inv["line_items"],
            }),
            "schema_version": "1.0",
        })

        # Notification
        notification_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "type": "upload",
            "title": "Invoice uploaded",
            "message": f"{inv['invoice_number']} from {inv['vendor_name']}",
            "related_invoice_id": inv["id"],
            "is_read": True,
        })

        # Audit log
        audit_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "table_name": "invoices",
            "record_id": inv["id"],
            "action": "create",
            "new_data": json.dumps({"invoice_number": inv["invoice_number"], "status": inv["status"]}),
        })

    n = insert_batch(db, "invoices", invoice_rows)
    log.info(f"  {n} payable invoices inserted")

    # Step 5: Receivable invoices
    log.info("Inserting receivable invoices...")
    rec_invoice_rows = []

    for inv in receivables:
        c_map = client_id_map[inv["client_idx"]]

        inv_row = {
            "id": inv["id"],
            "company_id": company["id"],
            "invoice_number": inv["invoice_number"],
            "invoice_type": "receivable",
            "issue_date": inv["issue_date"],
            "due_date": inv["due_date"],
            "currency": inv["currency"],
            "tax_percent": inv["tax_percent"],
            "subtotal": inv["subtotal"],
            "total_tax": inv["total_tax"],
            "grand_total": inv["grand_total"],
            "discount": inv["discount"],
            "status": inv["status"],
            "amount_paid_so_far": inv["amount_paid_so_far"],
            "confidence_score": inv["confidence_score"],
            "payment_method": inv.get("payment_method"),
            "description": inv.get("description"),
            "vendor_id": None,
            "client_id": c_map["client_id"],
            "vendor_address_id": None,
            "client_address_id": c_map["address_id"],
        }
        rec_invoice_rows.append(inv_row)

        for li in inv["line_items"]:
            line_item_rows.append({
                "id": uid(),
                "company_id": company["id"],
                "invoice_id": inv["id"],
                "description": li["description"],
                "quantity": li["quantity"],
                "unit_price": li["unit_price"],
                "line_subtotal": li["line_subtotal"],
                "discount": li.get("discount", 0),
            })

        for pay in inv.get("payments", []):
            payment_rows.append({
                "id": uid(),
                "company_id": company["id"],
                "invoice_id": inv["id"],
                "payment_date": pay["payment_date"],
                "amount": pay["amount"],
                "method": pay.get("method"),
                "reference": pay.get("reference"),
            })

        # Raw doc for receivables (we created these, so extraction is perfect)
        raw_doc_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "invoice_id": inv["id"],
            "raw_text": f"Invoice {inv['invoice_number']} to {inv['client_name']}",
            "extraction_json": json.dumps({
                "schema_version": "1.0",
                "invoice": {
                    "invoice_number": inv["invoice_number"],
                    "issue_date": inv["issue_date"],
                    "due_date": inv["due_date"],
                    "currency": inv["currency"],
                    "grand_total": inv["grand_total"],
                    "subtotal": inv["subtotal"],
                    "total_tax": inv["total_tax"],
                    "tax_percent": inv["tax_percent"],
                    "status": inv["status"],
                },
                "vendor": {"name": "K4Y"},
                "client": {"name": inv["client_name"]},
                "line_items": inv["line_items"],
            }),
            "schema_version": "1.0",
        })

        notification_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "type": "upload" if inv["status"] == "draft" else "status_change",
            "title": "Invoice created" if inv["status"] == "draft" else f"Invoice {inv['status']}",
            "message": f"{inv['invoice_number']} to {inv['client_name']}",
            "related_invoice_id": inv["id"],
            "is_read": True,
        })

        audit_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "table_name": "invoices",
            "record_id": inv["id"],
            "action": "create",
            "new_data": json.dumps({"invoice_number": inv["invoice_number"], "status": inv["status"]}),
        })

    n = insert_batch(db, "invoices", rec_invoice_rows)
    log.info(f"  {n} receivable invoices inserted")

    # Step 6: Line items
    log.info(f"Inserting {len(line_item_rows)} line items...")
    n = insert_batch(db, "line_items", line_item_rows)
    log.info(f"  {n} line items inserted")

    # Step 7: Payments
    log.info(f"Inserting {len(payment_rows)} payments...")
    n = insert_batch(db, "payments", payment_rows)
    log.info(f"  {n} payments inserted")

    # Step 8: Raw documents
    log.info(f"Inserting {len(raw_doc_rows)} raw documents...")
    n = insert_batch(db, "invoice_raw_documents", raw_doc_rows)
    log.info(f"  {n} raw documents inserted")

    # Step 9: Compliance flags
    log.info("Inserting compliance flags...")
    flag_rows = []
    for issue in issues:
        severity = "high" if issue["type"] in ("tax_mismatch", "duplicate_invoice") else "medium"
        flag_rows.append({
            "id": uid(),
            "company_id": company["id"],
            "invoice_id": issue["invoice_id"],
            "flag_type": issue["type"],
            "severity": severity,
            "reason": issue["detail"],
        })
    n = insert_batch(db, "compliance_flags", flag_rows)
    log.info(f"  {n} compliance flags inserted")

    # Step 10: Notifications
    log.info(f"Inserting {len(notification_rows)} notifications...")
    # Keep only last 50 notifications unread
    for i, notif in enumerate(notification_rows):
        if i >= len(notification_rows) - 50:
            notif["is_read"] = False
    n = insert_batch(db, "notifications", notification_rows)
    log.info(f"  {n} notifications inserted")

    # Step 11: Audit logs
    log.info(f"Inserting {len(audit_rows)} audit logs...")
    n = insert_batch(db, "audit_logs", audit_rows)
    log.info(f"  {n} audit logs inserted")

    # Summary
    log.info("=" * 60)
    log.info("SEED COMPLETE")
    log.info(f"  Company: {company['name']} ({company['id']})")
    log.info(f"  Vendors: {len(vendors)}")
    log.info(f"  Clients: {len(clients)}")
    log.info(f"  Payable invoices: {len(payables)}")
    log.info(f"  Receivable invoices: {len(receivables)}")
    log.info(f"  Line items: {len(line_item_rows)}")
    log.info(f"  Payments: {len(payment_rows)}")
    log.info(f"  Raw documents: {len(raw_doc_rows)}")
    log.info(f"  Compliance flags: {len(flag_rows)}")
    log.info(f"  Notifications: {len(notification_rows)}")
    log.info(f"  Audit logs: {len(audit_rows)}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()