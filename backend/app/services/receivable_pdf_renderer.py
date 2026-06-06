"""
Receivable PDF Renderer
-----------------------
Renders a branded receivable invoice PDF for a company.

All company-side values (name, address, contact, tax_id, branding colors,
logo, footer text) are pulled from the company row at render time — nothing
is hardcoded. Existing seed PDFs are NOT re-rendered; branding applies to
new receivables only.

Bucket choice: logo fetched from the public "branding" bucket via logo_url
(permanent public URL — no expiry risk on embedded images).

Logo layout: rendered in its own row above the header table, flush to the
top-right corner, sized up to 2" wide / 1" tall with original aspect ratio
preserved. INVOICE title sits below it on the right side.
"""

import io
import logging

import httpx
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

log = logging.getLogger(__name__)

# ─── Fallback defaults — used ONLY if company_data is missing fields ────────
DEFAULT_PRIMARY = "#1F2937"
DEFAULT_ACCENT  = "#6B7280"
DEFAULT_TEXT    = "#FFFFFF"

# ─── Logo sizing (top-right corner) ─────────────────────────────────────────
LOGO_MAX_WIDTH  = 2.0 * inch
LOGO_MAX_HEIGHT = 1.0 * inch


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


def _hex(color: str | None, fallback: str) -> HexColor:
    """Parse hex string to HexColor, fall back on invalid/None."""
    try:
        val = (color or fallback).strip()
        if not val.startswith("#") or len(val) != 7:
            return HexColor(fallback)
        return HexColor(val)
    except Exception:
        return HexColor(fallback)


def _fetch_logo(logo_url: str | None) -> io.BytesIO | None:
    """Fetch logo bytes from URL. Returns None if URL is None or fetch fails."""
    if not logo_url:
        return None
    try:
        resp = httpx.get(logo_url, timeout=5)
        resp.raise_for_status()
        return io.BytesIO(resp.content)
    except Exception as e:
        log.warning(f"Logo fetch failed url={logo_url} error={e}")
        return None


def _make_logo_image(logo_data: io.BytesIO) -> Image | None:
    """
    Build a reportlab Image flowable that preserves the original aspect ratio,
    fitting inside LOGO_MAX_WIDTH x LOGO_MAX_HEIGHT.
    Returns None if the image cannot be parsed.
    """
    try:
        reader = ImageReader(logo_data)
        iw, ih = reader.getSize()
        logo_data.seek(0)

        if iw <= 0 or ih <= 0:
            return None

        scale = min(LOGO_MAX_WIDTH / iw, LOGO_MAX_HEIGHT / ih)
        w, h = iw * scale, ih * scale

        img = Image(logo_data, width=w, height=h)
        img.hAlign = "RIGHT"
        return img
    except Exception as e:
        log.warning(f"Logo image build failed: {e}")
        return None


def _styles(PRIMARY: HexColor, TEXT_COLOR: HexColor):
    DARK = HexColor("#111827")
    MID  = HexColor("#6b7280")
    return {
        "company_name": ParagraphStyle(
            "company_name", fontSize=20, fontName="Helvetica-Bold",
            textColor=PRIMARY, leading=24, spaceAfter=2,
        ),
        "company_detail": ParagraphStyle(
            "company_detail", fontSize=8, fontName="Helvetica",
            textColor=MID, leading=12,
        ),
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
            textColor=TEXT_COLOR, leading=10,
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
            textColor=TEXT_COLOR, alignment=TA_RIGHT, leading=14,
        ),
        "grand_total_value": ParagraphStyle(
            "grand_total_value", fontSize=11, fontName="Helvetica-Bold",
            textColor=TEXT_COLOR, alignment=TA_RIGHT, leading=14,
        ),
        "notes": ParagraphStyle(
            "notes", fontSize=8, fontName="Helvetica",
            textColor=MID, leading=13,
        ),
        "footer_text": ParagraphStyle(
            "footer_text", fontSize=8, fontName="Helvetica",
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
    company_data: dict | None = None,
) -> bytes:
    """
    Render a branded receivable invoice PDF and return the bytes.

    company_data is expected to include both profile fields
    (name, address, email, phone, tax_id) and branding fields
    (logo_url, invoice_primary_color, invoice_accent_color,
     invoice_text_color, invoice_footer_text).
    Missing fields fall back to defaults / empty strings.
    """
    company       = company_data or {}

    # Branding
    PRIMARY       = _hex(company.get("invoice_primary_color"), DEFAULT_PRIMARY)
    ACCENT        = _hex(company.get("invoice_accent_color"),  DEFAULT_ACCENT)
    TEXT_COLOR    = _hex(company.get("invoice_text_color"),    DEFAULT_TEXT)
    footer_text   = company.get("invoice_footer_text") or None
    logo_url      = company.get("logo_url") or None

    # Company profile (dynamic — pulled from companies row)
    co_name    = company.get("name")    or "Company Name"
    co_address = company.get("address") or ""
    co_email   = company.get("email")   or ""
    co_phone   = company.get("phone")   or ""
    co_tax_id  = company.get("tax_id")  or ""

    LIGHT_GREY = HexColor("#f3f4f6")
    BORDER     = HexColor("#d1d5db")

    PAGE_W, _ = letter
    MARGIN    = 0.6 * inch
    USABLE    = PAGE_W - 2 * MARGIN

    s = _styles(PRIMARY, TEXT_COLOR)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    story = []
    currency = invoice_data.get("currency") or "USD"

    # ─── Logo row (full width, right-aligned) ───
    logo_data = _fetch_logo(logo_url)
    if logo_data:
        logo_img = _make_logo_image(logo_data)
        if logo_img is not None:
            logo_table = Table([[logo_img]], colWidths=[USABLE])
            logo_table.setStyle(TableStyle([
                ("ALIGN",        (0, 0), (-1, -1), "RIGHT"),
                ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING",   (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
            ]))
            story.append(logo_table)
            story.append(Spacer(1, 10))

    # ─── Header: company info (left) + INVOICE meta block (right) ───
    # Build the company detail block dynamically from whatever fields exist
    detail_lines = [line for line in [
        co_address,
        co_email,
        co_phone,
        f"Tax ID: {co_tax_id}" if co_tax_id else None,
    ] if line]

    company_block = [
        Paragraph(co_name, s["company_name"]),
    ]
    if detail_lines:
        company_block.append(
            Paragraph("<br/>".join(detail_lines), s["company_detail"])
        )

    invoice_title_block = [
        Paragraph("INVOICE", s["invoice_title"]),
        Spacer(1, 18),
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

    # ─── Line items (header bg = ACCENT color) ───
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
        ("BACKGROUND",     (0, 0), (-1, 0),  ACCENT),
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

    # ─── Grand total bar (bg = PRIMARY color) ───
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

    # ─── Custom footer text (from company.invoice_footer_text) ───
    if footer_text:
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
        story.append(Spacer(1, 8))
        story.append(Paragraph(footer_text, s["footer_text"]))
        story.append(Spacer(1, 12))

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

    # ─── Footer bar (uses dynamic company info) ───
    footer_parts = ["Thank you for your business.", co_name]
    if co_email:
        footer_parts.append(co_email)
    if co_phone:
        footer_parts.append(co_phone)
    footer_line = " | ".join(footer_parts)

    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 8))
    story.append(Paragraph(footer_line, s["footer"]))

    doc.build(story)
    return buffer.getvalue()