"""
Invoice PDF Generator — 5 Templates
=====================================
Renders payable invoices from dataset.json into PDFs matching the 5 template designs.
Output: /mnt/user-data/outputs/sample_data/input_pdfs/

Template assignments (by vendor):
T1: NexaCloud Solutions, Apex Office Supply Co — clean minimal gray
T2: Prisma Software Inc, CodeForge Contractors — black header/footer modern
T3: Summit Legal Partners, Ironside Hardware Corp — teal retail style
T4: Meridian Workspace LLC, Broadleaf Marketing Group — navy professional
T5: DataVault Security Inc, Greenline Facilities Mgmt — warm beige European
"""

import json
import os
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import HexColor, black, white, Color
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import Table, TableStyle

DATA_FILE = Path(__file__).parent / "dataset.json"
OUTPUT_DIR = Path(__file__).parent / "input_pdfs"

def d(val):
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_money(val, currency="USD"):
    """Format number as money string."""
    v = d(val)
    if currency == "USD":
        return f"${v:,.2f}"
    return f"{v:,.2f} {currency}"


def fmt_money_plain(val):
    """Format without currency symbol."""
    return f"{d(val):,.2f}"


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 1 — Clean minimal gray (NexaCloud, Apex)
# Based on: simple gray header bars, seller/client sections, items table, summary
# ═══════════════════════════════════════════════════════════════════════════

def render_template_1(c, inv, vendor):
    w, h = letter
    gray_bg = HexColor("#E0E0E0")
    dark_gray = HexColor("#555555")
    
    # Invoice number + date
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 50, f"Invoice no: {inv['invoice_number']}")
    c.setFont("Helvetica", 10)
    c.drawString(50, h - 70, f"Date of issue:")
    c.drawString(200, h - 70, inv["issue_date"])
    
    # Seller / Client header bars
    y = h - 120
    c.setFillColor(gray_bg)
    c.rect(50, y - 5, 230, 18, fill=1, stroke=0)
    c.rect(320, y - 5, 230, 18, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, "Seller:")
    c.drawString(325, y, "Client:")
    
    # Seller info
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
    
    # Client info (K4Y)
    y_client = h - 145
    c.drawString(325, y_client, "K4Y")
    y_client -= 14
    c.drawString(325, y_client, "1200 Tech Park Drive, Suite 400")
    y_client -= 14
    c.drawString(325, y_client, "Austin, TX 78701")
    y_client -= 20
    c.drawString(325, y_client, "Tax Id: 84-2957301")
    
    # ITEMS header
    y = h - 280
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "ITEMS")
    
    # Items table
    y -= 25
    headers = ["No.", "Description", "Qty", "UM", "Net price", "Net worth", "VAT [%]", "Gross worth"]
    col_widths = [30, 170, 35, 30, 65, 65, 45, 70]
    
    # Header row
    c.setFillColor(gray_bg)
    c.rect(50, y - 5, sum(col_widths), 18, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    x = 50
    for i, hdr in enumerate(headers):
        c.drawString(x + 3, y, hdr)
        x += col_widths[i]
    
    # Item rows
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
        # Wrap long descriptions
        desc = item["description"]
        if len(desc) > 45:
            c.drawString(x + 3 + col_widths[0], y, desc[:45])
            y -= 12
            c.drawString(x + 3 + col_widths[0], y, desc[45:90])
        
        for i, val in enumerate(row_data):
            c.drawString(x + 3, y, val)
            x += col_widths[i]
        
        # Row separator
        y -= 5
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.line(50, y, 50 + sum(col_widths), y)
        y -= 17
    
    # SUMMARY
    y -= 15
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "SUMMARY")
    y -= 25
    
    subtotal = inv["subtotal"]
    total_tax = inv["total_tax"]
    grand_total = inv["grand_total"]
    
    # Summary table
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


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 2 — Black header modern (Prisma, CodeForge)
# Based on: black top bar, bold INVOICE, three-column date layout, black items bar
# ═══════════════════════════════════════════════════════════════════════════

def render_template_2(c, inv, vendor):
    w, h = letter
    blk = HexColor("#1A1A1A")
    
    # Black header bar
    c.setFillColor(blk)
    c.rect(0, h - 55, w, 55, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 38, "INVOICE")
    c.setFont("Helvetica", 9)
    c.drawString(w - 200, h - 28, vendor["name"])
    c.drawString(w - 200, h - 40, vendor.get("email", ""))
    
    # Invoice number, date, due date row
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
    
    # Bill To / From
    y -= 35
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50, y, "BILL TO")
    c.drawString(300, y, "FROM")
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "K4Y")
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
    c.drawString(50, y, f"Tax Id: 84-2957301")
    c.drawString(300, y, f"Tax Id: {vendor['tax_id']}")
    y -= 12
    c.drawString(50, y, "finance@k4y.io")
    c.drawString(300, y, vendor.get("phone", ""))
    
    # Items table header (black bar)
    y -= 35
    c.setFillColor(blk)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "DESCRIPTION")
    c.drawString(350, y, "QTY")
    c.drawString(400, y, "UNIT PRICE")
    c.drawString(490, y, "AMOUNT")
    
    # Items
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
    
    # Summary
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
    
    # Footer
    c.setFont("Helvetica", 7)
    payment_method = inv.get("payment_method") or "Bank Transfer"
    c.drawString(50, 50, f"Payment Method: {payment_method}  |  Currency: {inv['currency']}")


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 3 — Teal retail style (Summit Legal, Ironside Hardware)
# Based on: teal header bar with company name, teal items bar, discount line
# ═══════════════════════════════════════════════════════════════════════════

def render_template_3(c, inv, vendor):
    w, h = letter
    teal = HexColor("#008B8B")
    teal_light = HexColor("#E0F5F5")
    
    # Header
    c.setFillColor(teal)
    c.rect(0, h - 60, w, 60, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 40, vendor["name"])
    c.setFont("Helvetica-Bold", 14)
    c.drawString(w - 150, h - 30, "INVOICE")
    
    # Contact info
    c.setFont("Helvetica", 8)
    c.drawString(w - 150, h - 42, f"# {inv['invoice_number']}")
    addr = vendor["address"]
    y = h - 52
    c.drawString(50, y, f"{addr['street']}  |  {addr['city']}, {addr['state']} {addr['postal_code']}")
    
    # Date
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    c.drawString(w - 150, h - 75, f"Date: {inv['issue_date']}")
    
    # Bill To
    y = h - 95
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "BILL TO:")
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(50, y, "K4Y")
    y -= 12
    c.drawString(50, y, "1200 Tech Park Drive, Suite 400")
    y -= 12
    c.drawString(50, y, "Austin, TX 78701")
    y -= 12
    c.drawString(50, y, f"Tax Id: 84-2957301")
    if inv.get("due_date"):
        y -= 12
        c.drawString(50, y, f"Due Date: {inv['due_date']}")
    
    # Items header (teal bar)
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
    
    # Items
    y -= 22
    c.setFillColor(black)
    c.setFont("Helvetica", 8)
    for idx, item in enumerate(inv["line_items"]):
        sku = f"SKU-{1000 + idx:04d}"
        c.drawString(55, y, sku)
        desc = item["description"][:35]
        c.drawString(200, y, desc)
        c.drawString(375, y, str(int(item["quantity"])))
        c.drawString(415, y, fmt_money(item["unit_price"]))
        c.drawString(490, y, fmt_money(item["line_subtotal"]))
        y -= 18
    
    # Summary
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
    
    # Total bar
    y -= 5
    c.setFillColor(teal)
    c.rect(380, y - 8, w - 430, 25, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(390, y, "TOTAL:")
    c.drawString(490, y, fmt_money(inv["grand_total"]))
    
    # Footer
    c.setFillColor(black)
    c.setFont("Helvetica", 7)
    pm = inv.get("payment_method") or "Bank Transfer"
    c.drawString(50, 50, f"Payment: {pm}  |  Currency: {inv['currency']}  |  Thank you for your business!")


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 4 — Navy professional (Meridian, Broadleaf)
# Based on: navy header with "TAX INVOICE", service provider / client layout
# ═══════════════════════════════════════════════════════════════════════════

def render_template_4(c, inv, vendor):
    w, h = letter
    navy = HexColor("#1F497D")
    navy_light = HexColor("#DCE6F1")
    
    # Header
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
    
    # Dates row
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
    
    # Service Provider / Client boxes
    y -= 35
    # Left box
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
    
    # Right box
    c.setFillColor(navy_light)
    c.rect(320, y - 80, 230, 90, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(325, y, "CLIENT:")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(325, y - 15, "K4Y")
    c.setFont("Helvetica", 8)
    c.drawString(325, y - 30, "1200 Tech Park Drive, Suite 400")
    c.drawString(325, y - 42, "Austin, TX 78701")
    c.drawString(325, y - 56, "EIN: 84-2957301")
    c.drawString(325, y - 68, "finance@k4y.io")
    
    # Items table header (navy bar)
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
    
    # Items
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
    
    # Summary
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
    
    # Wire transfer info
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    y -= 40
    c.drawString(50, y, "Wire Transfer Instructions:")
    c.setFont("Helvetica", 7)
    y -= 12
    c.drawString(50, y, f"Bank: Bank of America  |  Account: {random_digits(10)}  |  Routing: {random_digits(9)}")


def random_digits(n):
    import random as _r
    return "".join(str(_r.randint(0, 9)) for _ in range(n))


# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATE 5 — Warm beige European (DataVault, Greenline)
# Based on: beige/brown tones, left-aligned vendor info, IBAN, payment section
# ═══════════════════════════════════════════════════════════════════════════

def render_template_5(c, inv, vendor):
    w, h = letter
    beige = HexColor("#C4A35A")
    beige_light = HexColor("#F5ECD7")
    brown = HexColor("#5C4A28")
    
    # Vendor info (left column)
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
    
    # Invoice title (right)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(brown)
    c.drawString(w - 200, h - 50, "INVOICE")
    
    # Invoice details
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
    
    # Bill To
    y -= 35
    c.setFont("Helvetica-Bold", 9)
    c.drawString(350, y, "BILL TO")
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, y, "K4Y")
    c.setFont("Helvetica", 8)
    y -= 12
    c.drawString(350, y, "1200 Tech Park Drive, Suite 400")
    y -= 12
    c.drawString(350, y, "Austin, TX 78701")
    y -= 12
    c.drawString(350, y, "USA")
    y -= 12
    c.drawString(350, y, "Tax ID: 84-2957301")
    
    # Items header
    y -= 35
    c.setFillColor(beige)
    c.rect(50, y - 5, w - 100, 20, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(55, y, "DESCRIPTION")
    c.drawString(340, y, "QTY")
    c.drawString(390, y, f"UNIT PRICE")
    c.drawString(490, y, "AMOUNT")
    
    # Items
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
    
    # Summary
    y -= 10
    c.setFont("Helvetica", 9)
    c.drawString(380, y, "Subtotal:")
    c.drawString(490, y, f"{fmt_money_plain(inv['subtotal'])} {inv['currency']}")
    y -= 15
    if inv["tax_percent"] > 0:
        c.drawString(380, y, f"VAT ({inv['tax_percent']:.1f}%):")
        c.drawString(490, y, f"{fmt_money_plain(inv['total_tax'])} {inv['currency']}")
        y -= 15
    
    # Total bar
    c.setFillColor(beige)
    c.rect(370, y - 10, w - 420, 25, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y - 3, "TOTAL:")
    c.drawString(475, y - 3, f"{fmt_money_plain(inv['grand_total'])} {inv['currency']}")
    
    # Payment section
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
    
    # Bank details
    if vendor.get("iban"):
        y -= 25
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y, "BANK DETAILS")
        c.setFont("Helvetica", 8)
        y -= 14
        c.drawString(50, y, f"IBAN: {vendor['iban']}")
    
    # Footer
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#888888"))
    c.drawString(200, 40, "Thank you for your business.")


# ═══════════════════════════════════════════════════════════════════════════
# Main renderer
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE_MAP = {
    1: render_template_1,
    2: render_template_2,
    3: render_template_3,
    4: render_template_4,
    5: render_template_5,
}


def main():
    with open(DATA_FILE) as f:
        data = json.load(f)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    vendors_list = data["vendors"]
    payables = data["payables"]
    
    print(f"Rendering {len(payables)} payable invoices as PDFs...")
    
    template_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    for inv in payables:
        template_id = inv["template"]
        vendor = vendors_list[inv["vendor_idx"]]
        renderer = TEMPLATE_MAP[template_id]
        
        # Filename
        safe_name = inv["invoice_number"].replace("/", "-").replace("\\", "-")
        filename = f"{safe_name}.pdf"
        filepath = OUTPUT_DIR / filename
        
        c_pdf = canvas.Canvas(str(filepath), pagesize=letter)
        renderer(c_pdf, inv, vendor)
        c_pdf.save()
        
        template_counts[template_id] += 1
    
    print(f"\nPDFs rendered to: {OUTPUT_DIR}")
    print(f"Template distribution: {template_counts}")
    print(f"Total files: {sum(template_counts.values())}")


if __name__ == "__main__":
    main()