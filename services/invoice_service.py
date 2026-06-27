from __future__ import annotations
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

from models.invoice import Invoice
from utils.helpers import format_currency
from utils.logger import get_logger
from config import PDF_OUTPUT_DIR

logger = get_logger("invoice_service")

# ── Brand colours ──────────────────────────────────────────────────────────────
PRIMARY   = colors.HexColor("#1B2A4A")   # dark navy
ACCENT    = colors.HexColor("#2563EB")   # blue
LIGHT_BG  = colors.HexColor("#F1F5F9")  # light grey
BORDER    = colors.HexColor("#CBD5E1")
WHITE     = colors.white
GREEN     = colors.HexColor("#16A34A")
RED       = colors.HexColor("#DC2626")


def generate_pdf(invoice: Invoice) -> Path:
    """
    Generate a professional PDF invoice using ReportLab.
    Returns the path to the saved PDF file.
    """
    filename = f"{invoice.invoice_number}.pdf"
    output_path = PDF_OUTPUT_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Header ─────────────────────────────────────────────────────────────────
    story += _build_header(invoice, styles)
    story.append(Spacer(1, 6 * mm))

    # ── Bill To / Bill From ────────────────────────────────────────────────────
    story += _build_parties(invoice, styles)
    story.append(Spacer(1, 6 * mm))

    # ── Billing period & contract ref ─────────────────────────────────────────
    story += _build_meta(invoice, styles)
    story.append(Spacer(1, 6 * mm))

    # ── Line items table ───────────────────────────────────────────────────────
    story += _build_line_items(invoice, styles)
    story.append(Spacer(1, 4 * mm))

    # ── Totals ─────────────────────────────────────────────────────────────────
    story += _build_totals(invoice, styles)
    story.append(Spacer(1, 6 * mm))

    # ── Notes & payment terms ─────────────────────────────────────────────────
    story += _build_footer(invoice, styles)

    doc.build(story)
    logger.info(f"PDF generated: {output_path}")
    return output_path


# ── Section builders ───────────────────────────────────────────────────────────

def _build_header(invoice: Invoice, styles) -> list:
    title_style = ParagraphStyle(
        "InvTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=PRIMARY,
    )
    sub_style = ParagraphStyle(
        "InvSub",
        fontName="Helvetica",
        fontSize=9,
        textColor=ACCENT,
    )
    num_style = ParagraphStyle(
        "InvNum",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=WHITE,
        alignment=TA_RIGHT,
    )
    date_style = ParagraphStyle(
        "InvDate",
        fontName="Helvetica",
        fontSize=9,
        textColor=WHITE,
        alignment=TA_RIGHT,
    )

    left = [
        [Paragraph("SENTINEL", title_style)],
        [Paragraph("Touchless Invoice Automation", sub_style)],
    ]
    right = [
        [Paragraph(f"INVOICE", num_style)],
        [Paragraph(invoice.invoice_number, num_style)],
        [Paragraph(f"Date: {invoice.invoice_date}", date_style)],
        [Paragraph(f"Due:  {invoice.due_date}", date_style)],
    ]

    header_table = Table(
        [[
            Table(left, colWidths=[90 * mm]),
            Table(right, colWidths=[85 * mm],
                  style=TableStyle([
                      ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
                      ("ROWPADDINGS", (0, 0), (-1, -1), (4, 4, 4, 4)),
                  ])),
        ]],
        colWidths=[95 * mm, 85 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("RIGHTPADDING", (1, 0), (1, 0), 6),
        ("TOPPADDING", (1, 0), (1, 0), 6),
        ("BOTTOMPADDING", (1, 0), (1, 0), 6),
        ("BACKGROUND", (1, 0), (1, 0), PRIMARY),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return [header_table, HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=2)]


def _build_parties(invoice: Invoice, styles) -> list:
    label_style = ParagraphStyle("Label", fontName="Helvetica-Bold",
                                 fontSize=8, textColor=ACCENT)
    val_style   = ParagraphStyle("Val", fontName="Helvetica",
                                 fontSize=10, textColor=PRIMARY)
    sub_style   = ParagraphStyle("Sub", fontName="Helvetica",
                                 fontSize=8, textColor=colors.grey)

    from_block = [
        [Paragraph("FROM", label_style)],
        [Paragraph("Your Outsourcing Company", val_style)],
        [Paragraph("invoicing@sentinel.ai", sub_style)],
    ]
    to_block = [
        [Paragraph("BILL TO", label_style)],
        [Paragraph(invoice.client_name, val_style)],
        [Paragraph(f"Client ID: {invoice.client_id}", sub_style)],
    ]

    table = Table(
        [[Table(from_block), Table(to_block)]],
        colWidths=[90 * mm, 90 * mm],
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_BG),
        ("BACKGROUND", (1, 0), (1, 0), LIGHT_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return [table]


def _build_meta(invoice: Invoice, styles) -> list:
    label_s = ParagraphStyle("ML", fontName="Helvetica-Bold", fontSize=8, textColor=colors.grey)
    val_s   = ParagraphStyle("MV", fontName="Helvetica", fontSize=9, textColor=PRIMARY)

    rows = [
        ["Billing Period",
         f"{invoice.billing_period_start}  →  {invoice.billing_period_end}"],
        ["Employee",      f"{invoice.employee_name}  ({invoice.employee_id})"],
        ["Contract Ref",  invoice.contract_id],
        ["Payment Terms", f"Net {invoice.billing.line_items[0].rate if invoice.billing.line_items else 30} days"
         if False else f"Due by {invoice.due_date}"],
    ]

    data = [[Paragraph(r[0], label_s), Paragraph(r[1], val_s)] for r in rows]
    t = Table(data, colWidths=[45 * mm, 135 * mm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    return [t]


def _build_line_items(invoice: Invoice, styles) -> list:
    hdr_style = ParagraphStyle("LH", fontName="Helvetica-Bold",
                               fontSize=9, textColor=WHITE)
    row_style = ParagraphStyle("LR", fontName="Helvetica",
                               fontSize=9, textColor=PRIMARY)
    num_style = ParagraphStyle("LN", fontName="Helvetica",
                               fontSize=9, textColor=PRIMARY, alignment=TA_RIGHT)

    headers = ["Description", "Hours", "Rate", "Amount"]
    data    = [[Paragraph(h, hdr_style) for h in headers]]

    currency = invoice.billing.currency
    for item in invoice.billing.line_items:
        data.append([
            Paragraph(item.description, row_style),
            Paragraph(f"{item.hours:.2f}" if item.hours else "—", num_style),
            Paragraph(format_currency(item.rate, currency), num_style),
            Paragraph(format_currency(item.amount, currency), num_style),
        ])

    col_widths = [95 * mm, 22 * mm, 35 * mm, 28 * mm]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), PRIMARY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [t]


def _build_totals(invoice: Invoice, styles) -> list:
    b = invoice.billing
    currency = b.currency

    lbl = ParagraphStyle("TL", fontName="Helvetica",
                         fontSize=9, textColor=PRIMARY, alignment=TA_RIGHT)
    val = ParagraphStyle("TV", fontName="Helvetica",
                         fontSize=9, textColor=PRIMARY, alignment=TA_RIGHT)
    bold_lbl = ParagraphStyle("TBL", fontName="Helvetica-Bold",
                               fontSize=11, textColor=WHITE, alignment=TA_RIGHT)
    bold_val = ParagraphStyle("TBV", fontName="Helvetica-Bold",
                               fontSize=11, textColor=WHITE, alignment=TA_RIGHT)

    rows = [
        [Paragraph("Subtotal", lbl),
         Paragraph(format_currency(b.subtotal, currency), val)],
        [Paragraph(f"GST ({int(b.gst_amount / b.subtotal * 100) if b.subtotal else 0}%)", lbl),
         Paragraph(format_currency(b.gst_amount, currency), val)],
        [Paragraph("TOTAL DUE", bold_lbl),
         Paragraph(format_currency(b.total_amount, currency), bold_val)],
    ]
    if currency != "INR":
        rows.append([
            Paragraph(f"Total (INR equiv.)", lbl),
            Paragraph(f"₹{b.total_amount_inr:,.2f}", val),
        ])

    t = Table(rows, colWidths=[135 * mm, 45 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 2), (-1, 2), ACCENT),
        ("ROWBACKGROUNDS",(0, 0), (-1, 1), [LIGHT_BG, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [t]


def _build_footer(invoice: Invoice, styles) -> list:
    note_style = ParagraphStyle("FN", fontName="Helvetica",
                                fontSize=8, textColor=colors.grey)
    bold_note  = ParagraphStyle("FNB", fontName="Helvetica-Bold",
                                fontSize=8, textColor=PRIMARY)
    elements = [
        HRFlowable(width="100%", thickness=1, color=BORDER),
        Spacer(1, 3 * mm),
        Paragraph("Billing Notes", bold_note),
    ]
    for note in invoice.billing.billing_notes:
        elements.append(Paragraph(f"• {note}", note_style))

    elements += [
        Spacer(1, 4 * mm),
        Paragraph(
            f"Please remit payment by <b>{invoice.due_date}</b>. "
            "For queries contact invoicing@sentinel.ai",
            note_style,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "Generated by Sentinel — Touchless Invoice Automation",
            ParagraphStyle("Brand", fontName="Helvetica-Oblique",
                           fontSize=7, textColor=colors.lightgrey,
                           alignment=TA_CENTER),
        ),
    ]
    return elements
