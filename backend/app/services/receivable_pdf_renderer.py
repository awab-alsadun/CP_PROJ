"""
Receivable PDF Renderer
-----------------------
K4Y-branded invoice PDF for receivables created via the structured form.

Lifted from sample_data/render_pdfs.py::render_receivable so the same
visual layout is used for both the seed batch (rendered offline) and
runtime form-created receivables (rendered here, in-memory).

K4Y is single-tenant for the MVP; company constants are hardcoded.
"""

import io
import logging

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

log = logging.getLogger(__name__)

# ─── K4Y constants ──────────────────────────────────────────────────────────
K4Y_NAME    = "K4Y"
K4Y_ADDRESS = "1200 Tech Park Drive, Suite 400, Austin, TX 78701"
K4Y_EMAIL   = "finance@k4y.io"
K4Y_PHONE   = "+1 (512) 555-0147"
K4Y_TAX_ID  = "84-2957301"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _num(v, default: float = 0.0) -> float:
    """Coerce any Decimal/string/number to float."""
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _fmt_money(val, currency: str = "USD") -> str:
    v = _num(val)
    if currency == "USD":
        return f"${v:,.2f}"
    return f"{v:,.2f} {currency}"


def _styles():
    PRIMARY = HexColor("#1a56db")
    DARK    = HexColor("#111827")
    MID     = HexColor("#6b7280")
    return {
        "company_name": ParagraphStyle(
            "company_name", fontSize=20, fontName="Helvetica-Bold",
            textColor=PRIMARY, leading=24, spaceAfter=2,
        ),
        "company_detail": ParagraphStyle(
            "company_detail", fontSize=8, fontName="Helvetica",
            textColor=MID, leading=12,
        ),
        # Layout-bug fix: explicit leading=32 on 28pt title; 18pt spacer below
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


# ─── Main entry ─────────────────────────────────────────────────────────────

def render_receivable_pdf(
    invoice_data: dict,
    client_data: dict,
    line_items: list,
) -> bytes:
    """
    Render a K4Y-branded receivable invoice PDF and return the bytes.

    Args:
        invoice_data: invoice row dict — invoice_number, issue_date, due_date,
                      currency, tax_percent, subtotal, total_tax, grand_total,
                      discount, payment_method, description.
        client_data:  {name, tax_id, email, phone,
                       address: {street, city, state, postal_code, country}}
        line_items:   list of {description, quantity, unit_price,
                               line_subtotal, discount}
    """
    PRIMARY    = HexColor("#1a56db")
    LIGHT_GREY = HexColor("#f3f4f6")
    BORDER     = HexColor("#d1d5db")

    PAGE_W, _ = letter
    MARGIN    = 0.6 * inch
    USABLE    = PAGE_W - 2 * MARGIN

    s = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    story = []
    currency = invoice_data.get("currency") or "USD"

    # ─── Header: K4Y (left) + INVOICE block (right) ───
    company_block = [
        Paragraph(K4Y_NAME, s["company_name"]),
        Paragraph(
            "<br/>".join([K4Y_ADDRESS, K4Y_EMAIL, K4Y_PHONE, f"Tax ID: {K4Y_TAX_ID}"]),
            s["company_detail"],
        ),
    ]

    invoice_title_block = [
        Paragraph("INVOICE", s["invoice_title"]),
        Spacer(1, 18),  # gap fix — was 4pt
        Paragraph("INVOICE NUMBER", s["invoice_meta_label"]),
        Paragraph(str(invoice_data.get("invoice_number") or "N/A"), s["invoice_meta_value"]),
        Spacer(1, 6),
        Paragraph("ISSUE DATE", s["invoice_meta_label"]),
        Paragraph(str(invoice_data.get("issue_date") or "N/A"), s["invoice_meta_value"]),
        Spacer(1, 6),
        Paragraph("DUE DATE", s["invoice_meta_label"]),
        Paragraph(str(invoice_data.get("due_date") or "—"), s["invoice_meta_value"]),
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
    addr = client_data.get("address") or {}
    bill_to_lines = list(filter(None, [
        addr.get("street"),
        ", ".join(filter(None, [
            addr.get("city"), addr.get("state"), addr.get("postal_code"),
        ])),
        addr.get("country"),
        client_data.get("email"),
        client_data.get("phone"),
        f"Tax ID: {client_data['tax_id']}" if client_data.get("tax_id") else None,
    ]))

    bill_to_block = [
        Paragraph("BILL TO", s["section_label"]),
        Paragraph(client_data.get("name") or "Client Name", s["bill_to_name"]),
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
    col_widths = [USABLE * w for w in [0.40, 0.08, 0.16, 0.14, 0.22]]
    rows = [[
        Paragraph("DESCRIPTION", s["table_header"]),
        Paragraph("QTY",         s["table_header"]),
        Paragraph("UNIT PRICE",  s["table_header"]),
        Paragraph("DISCOUNT",    s["table_header"]),
        Paragraph("AMOUNT",      s["table_header"]),
    ]]
    for item in line_items:
        disc = _num(item.get("discount"))
        qty  = _num(item.get("quantity"), 1)
        qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"
        rows.append([
            Paragraph(item.get("description") or "—", s["table_cell"]),
            Paragraph(qty_str, s["table_cell_right"]),
            Paragraph(_fmt_money(item.get("unit_price"), currency), s["table_cell_right"]),
            Paragraph(_fmt_money(disc, currency) if disc else "—", s["table_cell_right"]),
            Paragraph(_fmt_money(item.get("line_subtotal"), currency), s["table_cell_right"]),
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
    subtotal    = _num(invoice_data.get("subtotal"))
    total_tax   = _num(invoice_data.get("total_tax"))
    grand_total = _num(invoice_data.get("grand_total"))
    discount    = _num(invoice_data.get("discount"))
    tax_pct     = _num(invoice_data.get("tax_percent"))

    totals_data = [[
        Paragraph("Subtotal", s["total_label"]),
        Paragraph(_fmt_money(subtotal, currency), s["total_value"]),
    ]]
    if discount > 0:
        totals_data.append([
            Paragraph("Discount", s["total_label"]),
            Paragraph(f"- {_fmt_money(discount, currency)}", s["total_value"]),
        ])
    totals_data.append([
        Paragraph(f"Tax ({tax_pct:.1f}%)", s["total_label"]),
        Paragraph(_fmt_money(total_tax, currency), s["total_value"]),
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
            Paragraph(_fmt_money(grand_total, currency), s["grand_total_value"]),
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
    if invoice_data.get("payment_method"):
        notes_lines.append(f"Payment method: {invoice_data['payment_method']}")
    if invoice_data.get("due_date"):
        notes_lines.append(f"Payment due by: {invoice_data['due_date']}")
    if invoice_data.get("description"):
        notes_lines.append(str(invoice_data["description"]))

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
    return buffer.getvalue()