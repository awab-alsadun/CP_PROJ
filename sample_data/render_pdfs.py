"""
Invoice PDF Generator
=====================
Renders the full sample dataset (dataset.json) to PDFs.

Output:
  sample_data/payable_pdfs/    — 5 vendor templates (T1–T5)
  sample_data/receivable_pdfs/ — K4Y-branded layout

Renamed from `input_pdfs/` to `payable_pdfs/` to disambiguate from receivables.

Payable template assignments (by vendor):
  T1: NexaCloud, Apex Office Supply — clean minimal gray
  T2: Prisma Software, CodeForge Contractors — black header modern
  T3: Summit Legal, Ironside Hardware — teal retail
  T4: Meridian Workspace, Broadleaf Marketing — navy professional
  T5: DataVault Security, Greenline Facilities — warm beige European

Receivables: single K4Y-branded layout (no per-client variation).
Layout bug fix: 18pt spacer between INVOICE title (28pt) and metadata block;
explicit leading=32 on title to prevent descender bleed into the next line.
"""

import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

DATA_FILE = Path(__file__).parent / "dataset.json"
PAYABLE_OUTPUT_DIR    = Path(__file__).parent / "payable_pdfs"
RECEIVABLE_OUTPUT_DIR = Path(__file__).parent / "receivable_pdfs"


# ─── K4Y constants (issuer for all receivables) ─────────────────────────────
K4Y_NAME    = "K4Y"
K4Y_ADDRESS = "1200 Tech Park Drive, Suite 400, Austin, TX 78701"
K4Y_EMAIL   = "finance@k4y.io"
K4Y_PHONE   = "+1 (512) 555-0147"
K4Y_TAX_ID  = "84-2957301"


# ─── Helpers ────────────────────────────────────────────────────────────────

def d(val):
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_money(val, currency="USD"):
    if val is None:
        return f"${0:,.2f}" if currency == "USD" else f"0.00 {currency}"
    v = d(val)
    if currency == "USD":
        return f"${v:,.2f}"
    return f"{v:,.2f} {currency}"


def fmt_money_plain(val):
    return f"{d(val):,.2f}"


def random_digits(n):
    import random as _r
    return "".join(str(_r.randint(0, 9)) for _ in range(n))


# ═══════════════════════════════════════════════════════════════════════════
# PAYABLE TEMPLATES T1–T5 (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def render_template_1(c, inv, vendor):
    w, h = letter
    gray_bg = HexColor("#E0E0E0")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 50, f"Invoice no: {inv['invoice_number']}")
    c.setFont("Helvetica", 10)
    c.drawString(50, h - 70, f"Date of issue:")
    c.drawString(200, h - 70, inv["issue_date"])

    y = h - 120
    c.setFillColor(gray_bg)
    c.rect(50, y - 5, 230, 18, fill=1, stroke=0)
    c.rect(320, y - 5, 230, 18, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, "Seller:")
    c.drawString(325, y, "Client:")

    c.setFont("Helvetica", 9)
    y -= 25
    addr = vendor["address"]
    c.drawString(55, y, vendor["name"])
    y -= 14
    c.drawString(55, y, addr["street"])
    y -= 14
    c.drawString(55, y, f"{addr['city']}, {addr['state']} {addr['postal_code']}")
    y -= 20
    c.drawString(55, y, f"Tax Id: {vendor['tax_id']}")
    if vendor.get("iban"):
        y -= 14
        c.drawString(55, y, f"IBAN: {vendor['iban']}")

    y_client = h - 145
    c.drawString(325, y_client, K4Y_NAME)
    y_client -= 14
    c.drawString(325, y_client, "1200 Tech Park Drive, Suite 400")
    y_client -= 14
    c.drawString(325, y_client, "Austin, TX 78701")
    y_client -= 20
    c.drawString(325, y_client, f"Tax Id: {K4Y_TAX_ID}")

    y = h - 280
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "ITEMS")

    y -= 25
    headers = ["No.", "Description", "Qty", "UM", "Net price", "Net worth", "VAT [%]", "Gross worth"]
    col_widths = [30, 170, 35, 30, 65, 65, 45, 70]

    c.setFillColor(gray_bg)
    c.rect(50, y - 5, sum(col_widths), 18, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    x = 50
    for i, hdr in enumerate(headers):
        c.drawString(x + 3, y, hdr)
        x += col_widths[i]

    c.setFont("Helvetica", 8)
    y -= 22
    tax_pct = inv["tax_percent"]
    for idx, item in enumerate(inv["line_items"], 1):
        net_worth = item["line_subtotal"]
        vat_amt = d(net_worth * tax_pct / 100)
        gross = d(net_worth + vat_amt)
        row_data = [
            str(idx) + ".",
            item["description"][:45],
            f"{item['quantity']:.0f}" if item["quantity"] == int(item["quantity"]) else f"{item['quantity']:.2f}",
            "each",
            fmt_money_plain(item["unit_price"]),
            fmt_money_plain(net_worth),
            f"{tax_pct:.0f}%",
            fmt_money_plain(gross),
        ]
        x = 50
        desc = item["description"]
        if len(desc) > 45:
            c.drawString(x + 3 + col_widths[0], y, desc[:45])
            y -= 12
            c.drawString(x + 3 + col_widths[0], y, desc[45:90])
        for i, val in enumerate(row_data):
            c.drawString(x + 3, y, val)
            x += col_widths[i]
        y -= 5
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.line(50, y, 50 + sum(col_widths), y)
        y -= 17

    y -= 15
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "SUMMARY")
    y -= 25
    subtotal = inv["subtotal"]
    total_tax = inv["total_tax"]
    grand_total = inv["grand_total"]
    c.setFillColor(gray_bg)
    c.rect(300, y - 5, 210, 18, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    for label, xpos in [("VAT [%]", 305), ("Net worth", 370), ("VAT", 430), ("Gross worth", 465)]:
        c.drawString(xpos, y, label)
    y -= 20
    c.setFont("Helvetica", 8)
    c.drawString(305, y, f"{tax_pct:.0f}%")
    c.drawString(370, y, fmt_money_plain(subtotal))
    c.drawString(430, y, fmt_money_plain(total_tax))
    c.drawString(465, y, fmt_money_plain(grand_total))
    y -= 25
    c.setFont("Helvetica-Bold", 10)
    c.drawString(305, y, "Total")
    c.drawString(370, y, f"$ {fmt_money_plain(subtotal)}")
    c.drawString(430, y, f"$ {fmt_money_plain(total_tax)}")
    c.drawString(465, y, f"$ {fmt_money_plain(grand_total)}")


def render_template_2(c, inv, vendor):
    w, h = letter
    blk = HexColor("#1A1A1A")
    c.setFillColor(blk)
    c.rect(0, h - 55, w, 55, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 38, "INVOICE")
    c.setFont("Helvetica", 9)
    c.drawString(w - 200, h - 28, vendor["name"])
    c.drawString(w - 200, h - 40, vendor.get("email", ""))

    y = h - 80
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50, y, "INVOICE NUMBER")
    c.drawString(220, y, "DATE")
    c.drawString(400, y, "DUE DATE")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(50, y, inv["invoice_number"])
    c.drawString(220, y, inv["issue_date"])
    c.drawString(400, y, inv["due_date"] or "N/A")

    y -= 35
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50, y, "BILL TO")
    c.drawString(300, y, "FROM")
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, K4Y_NAME)
    c.drawString(300, y, vendor["name"])
    y -= 14
    c.setFont("Helvetica", 8)
    c.drawString(50, y, "1200 Tech Park Drive, Suite 400")
    addr = vendor["address"]
    c.drawString(300, y, addr["street"])
    y -= 12
    c.drawString(50, y, "Austin, TX 78701")
    c.drawString(300, y, f"{addr['city']}, {addr['state']} {addr['postal_code']}")
    y -= 12
    c.drawString(50, y, f"Tax Id: {K4Y_TAX_ID}")
    c.drawString(300, y, f"Tax Id: {vendor['tax_id']}")
    y -= 12
    c.drawString(50, y, K4Y_EMAIL)
    c.drawString(300, y, vendor.get("phone", ""))

    y -= 35
    c.setFillColor(blk)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "DESCRIPTION")
    c.drawString(350, y, "QTY")
    c.drawString(400, y, "UNIT PRICE")
    c.drawString(490, y, "AMOUNT")

    y -= 25
    c.setFillColor(black)
    c.setFont("Helvetica", 9)
    for item in inv["line_items"]:
        desc = item["description"]
        if len(desc) > 50:
            c.drawString(55, y, desc[:50])
            y -= 12
            c.setFont("Helvetica", 8)
            c.drawString(55, y, f"({desc[50:100]})")
            c.setFont("Helvetica", 9)
        else:
            c.drawString(55, y, desc)
        c.drawString(355, y, str(int(item["quantity"])))
        c.drawString(400, y, fmt_money(item["unit_price"]))
        c.drawString(490, y, fmt_money(item["line_subtotal"]))
        y -= 22

    y -= 15
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.line(350, y + 5, w - 50, y + 5)
    c.setFont("Helvetica", 9)
    c.drawString(370, y - 10, "Subtotal:")
    c.drawString(490, y - 10, fmt_money(inv["subtotal"]))
    tax_label = f"Tax ({inv['tax_percent']:.1f}%):" if inv["tax_percent"] > 0 else "Tax (0%):"
    c.drawString(370, y - 25, tax_label)
    c.drawString(490, y - 25, fmt_money(inv["total_tax"]))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(370, y - 50, "TOTAL DUE:")
    c.drawString(480, y - 50, fmt_money(inv["grand_total"]))

    c.setFont("Helvetica", 7)
    payment_method = inv.get("payment_method") or "Bank Transfer"
    c.drawString(50, 50, f"Payment Method: {payment_method}  |  Currency: {inv['currency']}")


def render_template_3(c, inv, vendor):
    w, h = letter
    teal = HexColor("#008B8B")
    c.setFillColor(teal)
    c.rect(0, h - 60, w, 60, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 40, vendor["name"])
    c.setFont("Helvetica-Bold", 14)
    c.drawString(w - 150, h - 30, "INVOICE")
    c.setFont("Helvetica", 8)
    c.drawString(w - 150, h - 42, f"# {inv['invoice_number']}")
    addr = vendor["address"]
    y = h - 52
    c.drawString(50, y, f"{addr['street']}  |  {addr['city']}, {addr['state']} {addr['postal_code']}")

    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    c.drawString(w - 150, h - 75, f"Date: {inv['issue_date']}")

    y = h - 95
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "BILL TO:")
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(50, y, K4Y_NAME)
    y -= 12
    c.drawString(50, y, "1200 Tech Park Drive, Suite 400")
    y -= 12
    c.drawString(50, y, "Austin, TX 78701")
    y -= 12
    c.drawString(50, y, f"Tax Id: {K4Y_TAX_ID}")
    if inv.get("due_date"):
        y -= 12
        c.drawString(50, y, f"Due Date: {inv['due_date']}")

    y -= 30
    c.setFillColor(teal)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "ITEM")
    c.drawString(200, y, "DESCRIPTION")
    c.drawString(370, y, "QTY")
    c.drawString(415, y, "PRICE")
    c.drawString(490, y, "TOTAL")

    y -= 22
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    for idx, item in enumerate(inv["line_items"]):
        sku = f"SKU-{1000 + idx:04d}"
        c.drawString(55, y, sku)
        c.drawString(200, y, item["description"][:35])
        c.drawString(375, y, str(int(item["quantity"])))
        c.drawString(415, y, fmt_money(item["unit_price"]))
        c.drawString(490, y, fmt_money(item["line_subtotal"]))
        y -= 18

    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(390, y, "Subtotal:")
    c.drawString(490, y, fmt_money(inv["subtotal"]))
    y -= 15
    if inv.get("discount", 0) > 0:
        c.drawString(390, y, f"Discount ({inv['discount']}%):")
        c.drawString(490, y, f"-{fmt_money(inv['subtotal'] * inv['discount'] / 100)}")
        y -= 15
    if inv["tax_percent"] > 0:
        c.drawString(390, y, f"Sales Tax ({inv['tax_percent']}%):")
        c.drawString(490, y, fmt_money(inv["total_tax"]))
        y -= 15

    y -= 5
    c.setFillColor(teal)
    c.rect(380, y - 8, w - 430, 25, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(390, y, "TOTAL:")
    c.drawString(490, y, fmt_money(inv["grand_total"]))

    c.setFillColor(black)
    c.setFont("Helvetica", 7)
    pm = inv.get("payment_method") or "Bank Transfer"
    c.drawString(50, 50, f"Payment: {pm}  |  Currency: {inv['currency']}  |  Thank you for your business!")


def render_template_4(c, inv, vendor):
    w, h = letter
    navy = HexColor("#1F497D")
    navy_light = HexColor("#DCE6F1")
    c.setFillColor(navy)
    c.rect(0, h - 70, w, 70, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 35, vendor["name"])
    c.setFont("Helvetica-Bold", 14)
    c.drawString(w - 180, h - 30, "TAX INVOICE")
    c.setFont("Helvetica", 8)
    c.drawString(50, h - 52, vendor.get("email", ""))
    c.drawString(w - 180, h - 45, inv["invoice_number"])

    y = h - 90
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50, y, "Invoice Date:")
    c.drawString(200, y, "Due Date:")
    c.drawString(400, y, "Payment Terms:")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(50, y, inv["issue_date"])
    c.drawString(200, y, inv["due_date"] or "N/A")
    c.drawString(400, y, "Net 30")

    y -= 35
    c.setFillColor(navy_light)
    c.rect(50, y - 80, 230, 90, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(55, y, "SERVICE PROVIDER:")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y - 15, vendor["name"])
    c.setFont("Helvetica", 8)
    addr = vendor["address"]
    c.drawString(55, y - 30, addr["street"])
    c.drawString(55, y - 42, f"{addr['city']}, {addr['state']} {addr['postal_code']}")
    c.drawString(55, y - 56, f"EIN: {vendor['tax_id']}")
    c.drawString(55, y - 68, vendor.get("email", ""))

    c.setFillColor(navy_light)
    c.rect(320, y - 80, 230, 90, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(325, y, "CLIENT:")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(325, y - 15, K4Y_NAME)
    c.setFont("Helvetica", 8)
    c.drawString(325, y - 30, "1200 Tech Park Drive, Suite 400")
    c.drawString(325, y - 42, "Austin, TX 78701")
    c.drawString(325, y - 56, f"EIN: {K4Y_TAX_ID}")
    c.drawString(325, y - 68, K4Y_EMAIL)

    y -= 110
    c.setFillColor(navy)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "#")
    c.drawString(75, y, "Service Description")
    c.drawString(350, y, "Hours")
    c.drawString(410, y, "Rate (USD)")
    c.drawString(490, y, "Amount (USD)")

    y -= 22
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    for idx, item in enumerate(inv["line_items"], 1):
        c.drawString(55, y, str(idx))
        c.drawString(75, y, item["description"][:45])
        c.drawString(355, y, f"{item['quantity']:.1f}")
        c.drawString(410, y, fmt_money(item["unit_price"]))
        c.drawString(490, y, fmt_money(item["line_subtotal"]))
        y -= 18

    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(400, y, "Subtotal:")
    c.drawString(490, y, fmt_money(inv["subtotal"]))
    y -= 15
    c.drawString(400, y, f"Tax ({inv['tax_percent']}% — {inv['currency']}):")
    c.drawString(490, y, fmt_money(inv["total_tax"]))

    y -= 25
    c.setFillColor(navy)
    c.rect(380, y - 8, w - 430, 25, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(390, y, "TOTAL DUE:")
    c.drawString(480, y, f"{inv['currency']} {fmt_money_plain(inv['grand_total'])}")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    y -= 40
    c.drawString(50, y, "Wire Transfer Instructions:")
    c.setFont("Helvetica", 7)
    y -= 12
    c.drawString(50, y, f"Bank: Bank of America  |  Account: {random_digits(10)}  |  Routing: {random_digits(9)}")


def render_template_5(c, inv, vendor):
    w, h = letter
    beige = HexColor("#C4A35A")
    brown = HexColor("#5C4A28")
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(brown)
    c.drawString(50, h - 45, vendor["name"])
    c.setFont("Helvetica", 8)
    addr = vendor["address"]
    c.drawString(50, h - 60, addr["street"])
    c.drawString(50, h - 72, f"{addr['city']}, {addr['state']} {addr['postal_code']}")
    c.drawString(50, h - 84, addr.get("country", "USA"))
    y_left = h - 100
    if vendor.get("tax_id"):
        c.drawString(50, y_left, f"Tax ID: {vendor['tax_id']}")
        y_left -= 12
    c.drawString(50, y_left, vendor.get("email", ""))
    y_left -= 12
    c.drawString(50, y_left, vendor.get("phone", ""))

    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(brown)
    c.drawString(w - 200, h - 50, "INVOICE")

    c.setFont("Helvetica", 9)
    c.setFillColor(black)
    y = h - 80
    c.drawString(350, y, f"Nr. {inv['invoice_number']}")
    y -= 15
    c.drawString(350, y, f"Issue date: {inv['issue_date']}")
    y -= 12
    if inv.get("due_date"):
        c.drawString(350, y, f"Due date: {inv['due_date']}")
        y -= 12
    c.drawString(350, y, f"Currency: {inv['currency']}")

    y -= 35
    c.setFont("Helvetica-Bold", 9)
    c.drawString(350, y, "BILL TO")
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, y, K4Y_NAME)
    c.setFont("Helvetica", 8)
    y -= 12
    c.drawString(350, y, "1200 Tech Park Drive, Suite 400")
    y -= 12
    c.drawString(350, y, "Austin, TX 78701")
    y -= 12
    c.drawString(350, y, "USA")
    y -= 12
    c.drawString(350, y, f"Tax ID: {K4Y_TAX_ID}")

    y -= 35
    c.setFillColor(beige)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "DESCRIPTION")
    c.drawString(340, y, "QTY")
    c.drawString(390, y, "UNIT PRICE")
    c.drawString(490, y, "AMOUNT")

    y -= 22
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    for item in inv["line_items"]:
        desc = item["description"]
        if len(desc) > 40:
            c.drawString(55, y, desc[:40])
            y -= 11
            c.setFont("Helvetica", 7)
            c.drawString(55, y, desc[40:80])
            c.setFont("Helvetica", 8)
        else:
            c.drawString(55, y, desc)
        c.drawString(345, y, str(int(item["quantity"])))
        c.drawString(390, y, f"{fmt_money_plain(item['unit_price'])} {inv['currency']}")
        c.drawString(490, y, f"{fmt_money_plain(item['line_subtotal'])} {inv['currency']}")
        y -= 20

    y -= 10
    c.setFont("Helvetica", 9)
    c.drawString(380, y, "Subtotal:")
    c.drawString(490, y, f"{fmt_money_plain(inv['subtotal'])} {inv['currency']}")
    y -= 15
    if inv["tax_percent"] > 0:
        c.drawString(380, y, f"VAT ({inv['tax_percent']:.1f}%):")
        c.drawString(490, y, f"{fmt_money_plain(inv['total_tax'])} {inv['currency']}")
        y -= 15

    c.setFillColor(beige)
    c.rect(370, y - 10, w - 420, 25, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y - 3, "TOTAL:")
    c.drawString(475, y - 3, f"{fmt_money_plain(inv['grand_total'])} {inv['currency']}")

    c.setFillColor(black)
    y -= 45
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "PAYMENT")
    y -= 15
    c.setFont("Helvetica", 8)
    pm = inv.get("payment_method") or "Bank Wire"
    c.drawString(50, y, f"Method: {pm}")
    y -= 12
    c.drawString(50, y, f"Reference: {inv['invoice_number']}")

    if vendor.get("iban"):
        y -= 25
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y, "BANK DETAILS")
        c.setFont("Helvetica", 8)
        y -= 14
        c.drawString(50, y, f"IBAN: {vendor['iban']}")

    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#888888"))
    c.drawString(200, 40, "Thank you for your business.")


TEMPLATE_MAP = {
    1: render_template_1,
    2: render_template_2,
    3: render_template_3,
    4: render_template_4,
    5: render_template_5,
}


# ═══════════════════════════════════════════════════════════════════════════
# RECEIVABLE — K4Y-branded layout (Platypus)
# ═══════════════════════════════════════════════════════════════════════════

def _receivable_styles():
    PRIMARY    = HexColor("#1a56db")
    DARK       = HexColor("#111827")
    MID        = HexColor("#6b7280")
    return {
        "company_name": ParagraphStyle(
            "company_name", fontSize=20, fontName="Helvetica-Bold",
            textColor=PRIMARY, leading=24, spaceAfter=2,
        ),
        "company_detail": ParagraphStyle(
            "company_detail", fontSize=8, fontName="Helvetica",
            textColor=MID, leading=12,
        ),
        # CRITICAL FIX: explicit leading=32 on 28pt title; 18pt spacer after
        "invoice_title": ParagraphStyle(
            "invoice_title", fontSize=28, fontName="Helvetica-Bold",
            textColor=DARK, alignment=TA_RIGHT, leading=32,
        ),
        "invoice_meta_label": ParagraphStyle(
            "invoice_meta_label", fontSize=7, fontName="Helvetica-Bold",
            textColor=MID, alignment=TA_RIGHT, leading=10,
        ),
        "invoice_meta_value": ParagraphStyle(
            "invoice_meta_value", fontSize=10, fontName="Helvetica-Bold",
            textColor=DARK, alignment=TA_RIGHT, leading=13,
        ),
        "section_label": ParagraphStyle(
            "section_label", fontSize=7, fontName="Helvetica-Bold",
            textColor=MID, spaceAfter=2, leading=10,
        ),
        "bill_to_name": ParagraphStyle(
            "bill_to_name", fontSize=11, fontName="Helvetica-Bold",
            textColor=DARK, leading=14,
        ),
        "bill_to_detail": ParagraphStyle(
            "bill_to_detail", fontSize=8, fontName="Helvetica",
            textColor=DARK, leading=12,
        ),
        "table_header": ParagraphStyle(
            "table_header", fontSize=8, fontName="Helvetica-Bold",
            textColor=white, leading=10,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontSize=8, fontName="Helvetica",
            textColor=DARK, leading=11,
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right", fontSize=8, fontName="Helvetica",
            textColor=DARK, alignment=TA_RIGHT, leading=11,
        ),
        "total_label": ParagraphStyle(
            "total_label", fontSize=9, fontName="Helvetica",
            textColor=MID, alignment=TA_RIGHT, leading=12,
        ),
        "total_value": ParagraphStyle(
            "total_value", fontSize=9, fontName="Helvetica",
            textColor=DARK, alignment=TA_RIGHT, leading=12,
        ),
        "grand_total_label": ParagraphStyle(
            "grand_total_label", fontSize=11, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_RIGHT, leading=14,
        ),
        "grand_total_value": ParagraphStyle(
            "grand_total_value", fontSize=11, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_RIGHT, leading=14,
        ),
        "notes": ParagraphStyle(
            "notes", fontSize=8, fontName="Helvetica",
            textColor=MID, leading=13,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=7, fontName="Helvetica",
            textColor=MID, alignment=TA_CENTER, leading=10,
        ),
    }


def render_receivable(filepath, inv, client):
    """
    K4Y-branded receivable PDF.

    Layout bug fix: 18pt spacer between INVOICE title (28pt) and
    "INVOICE NUMBER" label (was 4pt — caused descender overlap).
    """
    PRIMARY    = HexColor("#1a56db")
    LIGHT_GREY = HexColor("#f3f4f6")
    BORDER     = HexColor("#d1d5db")

    PAGE_W, PAGE_H = letter
    MARGIN = 0.6 * inch
    USABLE = PAGE_W - 2 * MARGIN

    s = _receivable_styles()
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    story = []
    currency = inv.get("currency") or "USD"

    # ─── Header: K4Y (left) + INVOICE block (right) ───
    company_block = [
        Paragraph(K4Y_NAME, s["company_name"]),
        Paragraph(
            "<br/>".join([
                K4Y_ADDRESS,
                K4Y_EMAIL,
                K4Y_PHONE,
                f"Tax ID: {K4Y_TAX_ID}",
            ]),
            s["company_detail"],
        ),
    ]

    invoice_title_block = [
        Paragraph("INVOICE", s["invoice_title"]),
        Spacer(1, 18),  # FIXED: was 4pt
        Paragraph("INVOICE NUMBER", s["invoice_meta_label"]),
        Paragraph(inv.get("invoice_number") or "N/A", s["invoice_meta_value"]),
        Spacer(1, 6),
        Paragraph("ISSUE DATE", s["invoice_meta_label"]),
        Paragraph(inv.get("issue_date") or "N/A", s["invoice_meta_value"]),
        Spacer(1, 6),
        Paragraph("DUE DATE", s["invoice_meta_label"]),
        Paragraph(inv.get("due_date") or "—", s["invoice_meta_value"]),
    ]

    header_table = Table(
        [[company_block, invoice_title_block]],
        colWidths=[USABLE * 0.55, USABLE * 0.45],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 12))

    # ─── BILL TO ───
    addr = client.get("address") or {}
    bill_to_lines = list(filter(None, [
        addr.get("street"),
        ", ".join(filter(None, [
            addr.get("city"),
            addr.get("state"),
            addr.get("postal_code"),
        ])),
        addr.get("country"),
        client.get("email"),
        client.get("phone"),
        f"Tax ID: {client['tax_id']}" if client.get("tax_id") else None,
    ]))

    bill_to_block = [
        Paragraph("BILL TO", s["section_label"]),
        Paragraph(client.get("name") or "Client Name", s["bill_to_name"]),
        Paragraph("<br/>".join(bill_to_lines), s["bill_to_detail"]),
    ]
    bill_to_table = Table(
        [[bill_to_block]],
        colWidths=[USABLE * 0.5],
        hAlign="LEFT",
    )
    bill_to_table.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(bill_to_table)
    story.append(Spacer(1, 18))

    # ─── Line items ───
    # Discount column widened so "DISCOUNT" header doesn't wrap.
    col_widths = [USABLE * w for w in [0.40, 0.08, 0.16, 0.14, 0.22]]
    rows = [[
        Paragraph("DESCRIPTION", s["table_header"]),
        Paragraph("QTY",         s["table_header"]),
        Paragraph("UNIT PRICE",  s["table_header"]),
        Paragraph("DISCOUNT",    s["table_header"]),
        Paragraph("AMOUNT",      s["table_header"]),
    ]]
    for item in inv["line_items"]:
        disc = float(item.get("discount") or 0)
        qty = item.get("quantity", 1)
        qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"
        rows.append([
            Paragraph(item.get("description", "—"), s["table_cell"]),
            Paragraph(qty_str, s["table_cell_right"]),
            Paragraph(fmt_money(item.get("unit_price"), currency), s["table_cell_right"]),
            Paragraph(fmt_money(disc, currency) if disc else "—", s["table_cell_right"]),
            Paragraph(fmt_money(item.get("line_subtotal"), currency), s["table_cell_right"]),
        ])

    line_table = Table(rows, colWidths=col_widths, repeatRows=1)
    line_table.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GREY]),
        ("GRID",           (0, 0), (-1, -1), 0.25, BORDER),
        ("TOPPADDING",     (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 15))

    # ─── Totals ───
    subtotal    = float(inv.get("subtotal")    or 0)
    total_tax   = float(inv.get("total_tax")   or 0)
    grand_total = float(inv.get("grand_total") or 0)
    discount    = float(inv.get("discount")    or 0)
    tax_pct     = float(inv.get("tax_percent") or 0)

    totals_data = [[
        Paragraph("Subtotal", s["total_label"]),
        Paragraph(fmt_money(subtotal, currency), s["total_value"]),
    ]]
    if discount > 0:
        totals_data.append([
            Paragraph("Discount", s["total_label"]),
            Paragraph(f"- {fmt_money(discount, currency)}", s["total_value"]),
        ])
    totals_data.append([
        Paragraph(f"Tax ({tax_pct:.1f}%)", s["total_label"]),
        Paragraph(fmt_money(total_tax, currency), s["total_value"]),
    ])

    totals_table = Table(totals_data, colWidths=[USABLE * 0.75, USABLE * 0.25])
    totals_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 5))

    grand_table = Table(
        [[
            Paragraph("TOTAL DUE", s["grand_total_label"]),
            Paragraph(fmt_money(grand_total, currency), s["grand_total_value"]),
        ]],
        colWidths=[USABLE * 0.75, USABLE * 0.25],
    )
    grand_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(grand_table)
    story.append(Spacer(1, 22))

    # ─── Notes ───
    notes_lines = []
    if inv.get("payment_method"):
        notes_lines.append(f"Payment method: {inv['payment_method']}")
    if inv.get("due_date"):
        notes_lines.append(f"Payment due by: {inv['due_date']}")
    if inv.get("description"):
        notes_lines.append(inv["description"])

    if notes_lines:
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
        story.append(Spacer(1, 8))
        story.append(Paragraph("NOTES &amp; PAYMENT TERMS", s["section_label"]))
        story.append(Paragraph("<br/>".join(notes_lines), s["notes"]))
        story.append(Spacer(1, 18))

    # ─── Footer ───
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Thank you for your business. | {K4Y_NAME} | {K4Y_EMAIL} | {K4Y_PHONE}",
        s["footer"],
    ))

    doc.build(story)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    with open(DATA_FILE) as f:
        data = json.load(f)

    PAYABLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIVABLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    vendors_list = data["vendors"]
    clients_list = data["clients"]
    payables     = data["payables"]
    receivables  = data["receivables"]

    # ─── Payables ───
    print(f"Rendering {len(payables)} payable invoices...")
    template_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for inv in payables:
        template_id = inv["template"]
        vendor      = vendors_list[inv["vendor_idx"]]
        renderer    = TEMPLATE_MAP[template_id]

        safe_name = inv["invoice_number"].replace("/", "-").replace("\\", "-")
        filepath  = PAYABLE_OUTPUT_DIR / f"{safe_name}.pdf"

        c_pdf = canvas.Canvas(str(filepath), pagesize=letter)
        renderer(c_pdf, inv, vendor)
        c_pdf.save()
        template_counts[template_id] += 1

    print(f"  -> {PAYABLE_OUTPUT_DIR}")
    print(f"  Template distribution: {template_counts}")
    print(f"  Total: {sum(template_counts.values())} files")

    # ─── Receivables ───
    print(f"\nRendering {len(receivables)} receivable invoices...")
    for inv in receivables:
        client    = clients_list[inv["client_idx"]]
        safe_name = inv["invoice_number"].replace("/", "-").replace("\\", "-")
        filepath  = RECEIVABLE_OUTPUT_DIR / f"{safe_name}.pdf"
        render_receivable(filepath, inv, client)

    print(f"  -> {RECEIVABLE_OUTPUT_DIR}")
    print(f"  Total: {len(receivables)} files")


if __name__ == "__main__":
    main()