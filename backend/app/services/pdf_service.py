"""
PDF Service
-----------
Generates professional invoice PDFs for receivable invoices only.

Rules:
  - ONLY for receivable invoices (outbound to clients)
  - ONLY triggered when receivable transitions draft → sent
  - Never generate for payables (they arrived as uploaded PDFs)
  - Never generate for draft receivables

Output stored in invoice_raw_documents as bytea (pdf_binary column).
Retrieved via GET /api/v1/invoices/{id}/pdf → StreamingResponse.

Layout:
  - Company header (name, address, phone, email, tax_id)
  - INVOICE title + number + issue_date + due_date
  - Bill To: client info
  - Line items table
  - Totals: subtotal, discount, tax, grand_total
  - Payment terms / notes
  - Footer
"""

import io
import logging
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from supabase import Client
from app.core.exceptions import DatabaseError, NotFoundError, ValidationError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand colours (FinTech dark theme accent)
# ---------------------------------------------------------------------------
PRIMARY    = HexColor("#1a56db")   # blue
PRIMARY_LT = HexColor("#e8f0fe")   # light blue fill
DARK       = HexColor("#111827")   # near-black text
MID        = HexColor("#6b7280")   # grey labels
LIGHT_GREY = HexColor("#f3f4f6")   # table row alt
BORDER     = HexColor("#d1d5db")   # subtle border


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _styles():
    base = getSampleStyleSheet()
    styles = {
        "company_name": ParagraphStyle(
            "company_name",
            fontSize=20, fontName="Helvetica-Bold",
            textColor=PRIMARY, spaceAfter=2,
        ),
        "company_detail": ParagraphStyle(
            "company_detail",
            fontSize=8, fontName="Helvetica",
            textColor=MID, leading=12,
        ),
        "invoice_title": ParagraphStyle(
            "invoice_title",
            fontSize=28, fontName="Helvetica-Bold",
            textColor=DARK, alignment=TA_RIGHT,
        ),
        "invoice_meta_label": ParagraphStyle(
            "invoice_meta_label",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=MID, alignment=TA_RIGHT,
        ),
        "invoice_meta_value": ParagraphStyle(
            "invoice_meta_value",
            fontSize=9, fontName="Helvetica",
            textColor=DARK, alignment=TA_RIGHT,
        ),
        "section_label": ParagraphStyle(
            "section_label",
            fontSize=7, fontName="Helvetica-Bold",
            textColor=MID, spaceAfter=2,
        ),
        "bill_to_name": ParagraphStyle(
            "bill_to_name",
            fontSize=10, fontName="Helvetica-Bold",
            textColor=DARK, spaceAfter=1,
        ),
        "bill_to_detail": ParagraphStyle(
            "bill_to_detail",
            fontSize=8, fontName="Helvetica",
            textColor=DARK, leading=12,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=white,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            fontSize=8, fontName="Helvetica",
            textColor=DARK,
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right",
            fontSize=8, fontName="Helvetica",
            textColor=DARK, alignment=TA_RIGHT,
        ),
        "total_label": ParagraphStyle(
            "total_label",
            fontSize=9, fontName="Helvetica",
            textColor=MID, alignment=TA_RIGHT,
        ),
        "total_value": ParagraphStyle(
            "total_value",
            fontSize=9, fontName="Helvetica",
            textColor=DARK, alignment=TA_RIGHT,
        ),
        "grand_total_label": ParagraphStyle(
            "grand_total_label",
            fontSize=11, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_RIGHT,
        ),
        "grand_total_value": ParagraphStyle(
            "grand_total_value",
            fontSize=11, fontName="Helvetica-Bold",
            textColor=white, alignment=TA_RIGHT,
        ),
        "notes": ParagraphStyle(
            "notes",
            fontSize=8, fontName="Helvetica",
            textColor=MID, leading=13,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontSize=7, fontName="Helvetica",
            textColor=MID, alignment=TA_CENTER,
        ),
    }
    return styles


# ---------------------------------------------------------------------------
# Layout builder
# ---------------------------------------------------------------------------

def _format_money(amount, currency: str = "") -> str:
    if amount is None:
        return f"{currency} 0.00".strip()
    return f"{currency} {float(amount):.2f}".strip()


def _safe(value, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


def _build_pdf_bytes(invoice: dict, company: dict, line_items: list[dict]) -> bytes:
    buffer = io.BytesIO()
    s = _styles()

    PAGE_W, PAGE_H = A4
    MARGIN = 20 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    story = []
    currency = _safe(invoice.get("currency"), "USD")

    # -----------------------------------------------------------------------
    # Header: company info (left) + INVOICE title (right)
    # -----------------------------------------------------------------------
    company_block = [
        Paragraph(_safe(company.get("name"), "Company Name"), s["company_name"]),
        Paragraph(
            "<br/>".join(filter(None, [
                _safe(company.get("address")),
                _safe(company.get("email")),
                _safe(company.get("phone")),
                f"Tax ID: {company['tax_id']}" if company.get("tax_id") else None,
            ])),
            s["company_detail"],
        ),
    ]

    invoice_title_block = [
        Paragraph("INVOICE", s["invoice_title"]),
        Spacer(1, 4),
        Paragraph("Invoice Number", s["invoice_meta_label"]),
        Paragraph(_safe(invoice.get("invoice_number"), "N/A"), s["invoice_meta_value"]),
        Spacer(1, 2),
        Paragraph("Issue Date", s["invoice_meta_label"]),
        Paragraph(_safe(invoice.get("issue_date"), "N/A"), s["invoice_meta_value"]),
        Spacer(1, 2),
        Paragraph("Due Date", s["invoice_meta_label"]),
        Paragraph(_safe(invoice.get("due_date"), "N/A"), s["invoice_meta_value"]),
    ]

    header_table = Table(
        [[company_block, invoice_title_block]],
        colWidths=[(PAGE_W - 2 * MARGIN) * 0.55,
                   (PAGE_W - 2 * MARGIN) * 0.45],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 5 * mm))

    # -----------------------------------------------------------------------
    # Bill To
    # -----------------------------------------------------------------------
    client = invoice.get("client") or {}
    client_addr = invoice.get("client_address") or {}

    bill_to_lines = filter(None, [
        client_addr.get("street"),
        ", ".join(filter(None, [
            client_addr.get("city"),
            client_addr.get("state"),
            client_addr.get("postal_code"),
        ])),
        client_addr.get("country"),
        client.get("email"),
        client.get("phone"),
        f"Tax ID: {client['tax_id']}" if client.get("tax_id") else None,
    ])

    bill_to_block = [
        Paragraph("BILL TO", s["section_label"]),
        Paragraph(_safe(client.get("name"), "Client Name"), s["bill_to_name"]),
        Paragraph("<br/>".join(bill_to_lines), s["bill_to_detail"]),
    ]

    story.append(Table(
        [[bill_to_block]],
        colWidths=[(PAGE_W - 2 * MARGIN) * 0.5],
    ))
    story.append(Spacer(1, 6 * mm))

    # -----------------------------------------------------------------------
    # Line items table
    # -----------------------------------------------------------------------
    col_widths_raw = [0.42, 0.10, 0.16, 0.10, 0.22]
    usable = PAGE_W - 2 * MARGIN
    col_widths = [usable * w for w in col_widths_raw]

    header_row = [
        Paragraph("DESCRIPTION", s["table_header"]),
        Paragraph("QTY",         s["table_header"]),
        Paragraph("UNIT PRICE",  s["table_header"]),
        Paragraph("DISCOUNT",    s["table_header"]),
        Paragraph("AMOUNT",      s["table_header"]),
    ]

    rows = [header_row]
    for i, item in enumerate(line_items):
        discount = float(item.get("discount") or 0)
        rows.append([
            Paragraph(_safe(item.get("description"), "—"), s["table_cell"]),
            Paragraph(_safe(item.get("quantity"), "1"),    s["table_cell_right"]),
            Paragraph(_format_money(item.get("unit_price"), currency), s["table_cell_right"]),
            Paragraph(_format_money(discount) if discount else "—", s["table_cell_right"]),
            Paragraph(_format_money(item.get("line_subtotal"), currency), s["table_cell_right"]),
        ])

    line_table = Table(rows, colWidths=col_widths, repeatRows=1)

    row_count = len(rows)
    line_table_style = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0),  PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1),  0.25, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1),  5),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  5),
        ("LEFTPADDING",   (0, 0), (-1, -1),  6),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  6),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        # Right-align numeric columns
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]
    line_table.setStyle(TableStyle(line_table_style))
    story.append(line_table)
    story.append(Spacer(1, 5 * mm))

    # -----------------------------------------------------------------------
    # Totals block (right-aligned)
    # -----------------------------------------------------------------------
    subtotal    = float(invoice.get("subtotal")    or 0)
    total_tax   = float(invoice.get("total_tax")   or 0)
    grand_total = float(invoice.get("grand_total") or 0)
    discount    = float(invoice.get("discount")    or 0)
    tax_pct     = float(invoice.get("tax_percent") or 0)

    totals_data = []
    totals_data.append([
        Paragraph("Subtotal",              s["total_label"]),
        Paragraph(_format_money(subtotal, currency), s["total_value"]),
    ])
    if discount > 0:
        totals_data.append([
            Paragraph("Discount",                      s["total_label"]),
            Paragraph(f"- {_format_money(discount, currency)}", s["total_value"]),
        ])
    totals_data.append([
        Paragraph(f"Tax ({tax_pct:.1f}%)",             s["total_label"]),
        Paragraph(_format_money(total_tax, currency),  s["total_value"]),
    ])

    totals_table = Table(
        totals_data,
        colWidths=[usable * 0.75, usable * 0.25],
    )
    totals_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 2 * mm))

    # Grand total highlighted row
    grand_table = Table(
        [[
            Paragraph("TOTAL DUE",                          s["grand_total_label"]),
            Paragraph(_format_money(grand_total, currency), s["grand_total_value"]),
        ]],
        colWidths=[usable * 0.75, usable * 0.25],
    )
    grand_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(grand_table)
    story.append(Spacer(1, 8 * mm))

    # -----------------------------------------------------------------------
    # Notes / payment terms
    # -----------------------------------------------------------------------
    description = invoice.get("description")
    payment_method = invoice.get("payment_method")
    due_date = invoice.get("due_date")

    notes_lines = []
    if payment_method:
        notes_lines.append(f"Payment method: {payment_method}")
    if due_date:
        notes_lines.append(f"Payment due by: {due_date}")
    if description:
        notes_lines.append(description)

    if notes_lines:
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("NOTES &amp; PAYMENT TERMS", s["section_label"]))
        story.append(Paragraph("<br/>".join(notes_lines), s["notes"]))
        story.append(Spacer(1, 6 * mm))

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 3 * mm))
    company_name = _safe(company.get("name"), "")
    story.append(Paragraph(
        f"Thank you for your business. | {company_name} | "
        f"{_safe(company.get('email'))} | {_safe(company.get('phone'))}",
        s["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_invoice_pdf(
    db: Client,
    company_id: str,
    invoice_id: str,
) -> bytes:
    """
    Generate a PDF for a receivable invoice and store it in
    invoice_raw_documents (pdf_binary column).

    Returns PDF bytes.
    Raises ValidationError if called on a payable invoice.
    Raises NotFoundError if invoice doesn't exist.
    """
    # Fetch invoice with nested client
    try:
        inv_result = (
            db.table("invoices").select("*")
            .eq("id", invoice_id)
            .eq("company_id", company_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch invoice for PDF generation", detail=str(e))

    if not inv_result.data:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    invoice = inv_result.data

    if invoice.get("invoice_type") != "receivable":
        raise ValidationError(
            "PDF generation is only available for receivable invoices. "
            "Payable invoices use the original uploaded document."
        )

    # Fetch client
    client_id = invoice.get("client_id")
    client = {}
    if client_id:
        try:
            cr = (
                db.table("clients")
                .select("id, name, email, phone, tax_id")
                .eq("id", client_id).single().execute()
            )
            client = cr.data or {}
        except Exception:
            pass
    invoice["client"] = client

    # Fetch client address
    client_address_id = invoice.get("client_address_id")
    client_address = {}
    if client_address_id:
        try:
            ar = (
                db.table("addresses")
                .select("street, city, state, postal_code, country")
                .eq("id", client_address_id).single().execute()
            )
            client_address = ar.data or {}
        except Exception:
            pass
    invoice["client_address"] = client_address

    # Fetch line items
    try:
        li_result = (
            db.table("line_items").select("*")
            .eq("invoice_id", invoice_id).execute()
        )
        line_items = li_result.data or []
    except Exception:
        line_items = []

    # Fetch company profile
    try:
        co_result = (
            db.table("companies")
            .select("name, address, phone, email, tax_id")
            .eq("id", company_id).single().execute()
        )
        company = co_result.data or {}
    except Exception:
        company = {}

    # Generate PDF bytes
    try:
        pdf_bytes = _build_pdf_bytes(invoice, company, line_items)
    except Exception as e:
        raise DatabaseError("PDF generation failed", detail=str(e))

    # Store in invoice_raw_documents (pdf_binary column)
    # Encode bytes as latin-1 string for Supabase bytea storage
    try:
        existing = (
            db.table("invoice_raw_documents")
            .select("id")
            .eq("invoice_id", invoice_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            db.table("invoice_raw_documents").update({
                "pdf_binary": pdf_bytes.decode("latin-1"),
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            # No raw document yet (manually created receivable)
            db.table("invoice_raw_documents").insert({
                "company_id":      company_id,
                "invoice_id":      invoice_id,
                "raw_text":        "",
                "extraction_json": {},
                "schema_version":  "1.0",
                "pdf_binary":      pdf_bytes.decode("latin-1"),
            }).execute()
    except Exception as e:
        # Storage failure is non-fatal — still return the bytes
        log.error(f"Failed to store PDF for invoice {invoice_id}: {e}")

    log.info(f"PDF generated for receivable invoice {invoice_id}: {len(pdf_bytes)} bytes")
    return pdf_bytes


def get_stored_pdf(
    db: Client,
    company_id: str,
    invoice_id: str,
) -> bytes | None:
    """
    Retrieve stored PDF bytes for an invoice.

    For receivables: returns generated PDF from pdf_binary column.
    For payables: returns None (use storage_path to fetch the original upload).
    """
    try:
        result = (
            db.table("invoice_raw_documents")
            .select("pdf_binary")
            .eq("invoice_id", invoice_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise DatabaseError("Failed to fetch stored PDF", detail=str(e))

    if not result.data:
        return None

    raw = result.data[0].get("pdf_binary")
    if not raw:
        return None

    # Supabase returns bytea as hex string with \x prefix
    if isinstance(raw, str):
        if raw.startswith("\\x"):
            return bytes.fromhex(raw[2:])
        # latin-1 encoded string (our storage format)
        return raw.encode("latin-1")

    return raw