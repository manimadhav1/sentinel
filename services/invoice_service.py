from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

from models.invoice import Invoice
from utils.logger import get_logger
from config import PDF_OUTPUT_DIR

logger = get_logger("invoice_service")

# ── Brand palette ──────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#0F172A")
BLUE    = colors.HexColor("#2563EB")
LBLUE   = colors.HexColor("#EFF6FF")
SILVER  = colors.HexColor("#F8FAFC")
BORDER  = colors.HexColor("#E2E8F0")
GREY    = colors.HexColor("#64748B")
WHITE   = colors.white
GREEN   = colors.HexColor("#16A34A")

W = A4[0] - 30 * mm   # usable width


def _fmt(amount: float, currency: str) -> str:
    """Format amount without problematic unicode symbols."""
    cur = currency.upper()
    # Use plain text codes so ReportLab Helvetica renders correctly
    return f"{cur} {amount:,.2f}"


def _inr(amount: float) -> str:
    return f"INR {amount:,.2f}"


def generate_pdf(invoice: Invoice) -> Path:
    filename    = f"{invoice.invoice_number}.pdf"
    output_path = PDF_OUTPUT_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm,   bottomMargin=15 * mm,
    )
    doc.build(_build_story(invoice))
    logger.info(f"PDF generated: {output_path}")
    return output_path


# ── Style helpers ──────────────────────────────────────────────────────────────
def _s(name, font="Helvetica", size=9, color=NAVY, align=TA_LEFT, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size,
                          textColor=color, alignment=align,
                          leading=size * 1.4, **kw)


def _build_story(invoice: Invoice) -> list:
    b     = invoice.billing
    cur   = b.currency
    story = []

    # ── 1. Header band ─────────────────────────────────────────────────────────
    left_cells = [
        [Paragraph("SENTINEL", _s("H1", "Helvetica-Bold", 26, NAVY))],
        [Paragraph("Touchless Invoice Automation",
                   _s("H2", size=8, color=BLUE))],
    ]
    right_cells = [
        [Paragraph("INVOICE", _s("IR", "Helvetica-Bold", 14, WHITE, TA_RIGHT))],
        [Paragraph(invoice.invoice_number,
                   _s("IN", "Helvetica-Bold", 11, WHITE, TA_RIGHT))],
        [Paragraph(f"Date: {invoice.invoice_date}",
                   _s("ID", size=8, color=WHITE, align=TA_RIGHT))],
        [Paragraph(f"Due:  {invoice.due_date}",
                   _s("IDD", size=8, color=WHITE, align=TA_RIGHT))],
    ]

    hdr = Table(
        [[Table(left_cells,  colWidths=[95 * mm]),
          Table(right_cells, colWidths=[85 * mm],
                style=TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
                    ("TOPPADDING",    (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                ]))]],
        colWidths=[95 * mm, 85 * mm],
    )
    hdr.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (1, 0), (1, 0),   NAVY),
        ("TOPPADDING",    (0, 0), (0, 0),   4),
        ("BOTTOMPADDING", (0, 0), (0, 0),   4),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=3, color=BLUE, spaceAfter=5))
    story.append(Spacer(1, 4 * mm))

    # ── 2. Parties row ─────────────────────────────────────────────────────────
    lbl  = _s("lbl", "Helvetica-Bold", 7, BLUE)
    name = _s("nm",  "Helvetica-Bold", 11, NAVY)
    sub  = _s("sub", size=8, color=GREY)

    from_data = [
        [Paragraph("FROM",                     lbl)],
        [Paragraph("TASC Outsourcing",          name)],
        [Paragraph("billing@tasc.ae",           sub)],
        [Paragraph("Dubai, UAE",                sub)],
    ]
    to_data = [
        [Paragraph("BILL TO",                   lbl)],
        [Paragraph(invoice.client_name,         name)],
        [Paragraph(f"Client ID: {invoice.client_id}", sub)],
    ]

    parties = Table(
        [[Table(from_data), Table(to_data)]],
        colWidths=[88 * mm, 88 * mm],
    )
    parties.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), SILVER),
        ("BACKGROUND",    (1, 0), (1, 0), LBLUE),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (0, 0), 0.5, BORDER),
        ("BOX",           (1, 0), (1, 0), 0.5, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story += [parties, Spacer(1, 5 * mm)]

    # ── 3. Meta table ──────────────────────────────────────────────────────────
    ml = _s("ml", "Helvetica-Bold", 8, GREY)
    mv = _s("mv", size=9, color=NAVY)

    meta_rows = [
        ["Billing Period",
         f"{invoice.billing_period_start}  to  {invoice.billing_period_end}"],
        ["Employee",
         f"{invoice.employee_name}  ({invoice.employee_id})"],
        ["Contract Reference", invoice.contract_id],
        ["Payment Terms",      f"Due by {invoice.due_date}"],
        ["Currency",           cur],
    ]
    meta_data = [[Paragraph(r[0], ml), Paragraph(r[1], mv)] for r in meta_rows]
    meta = Table(meta_data, colWidths=[45 * mm, 131 * mm])
    meta.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SILVER]),
        ("GRID",           (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story += [meta, Spacer(1, 5 * mm)]

    # ── 4. Line items ──────────────────────────────────────────────────────────
    hh = _s("hh", "Helvetica-Bold", 9, WHITE)
    hr = _s("hr", "Helvetica-Bold", 9, WHITE, TA_RIGHT)
    dr = _s("dr", size=9, color=NAVY)
    nr = _s("nr", size=9, color=NAVY, align=TA_RIGHT)

    li_data = [[
        Paragraph("Description", hh),
        Paragraph("Hours",  hr),
        Paragraph("Rate",   hr),
        Paragraph("Amount", hr),
    ]]
    for item in b.line_items:
        hrs = f"{item.hours:.1f}" if item.hours else "—"
        li_data.append([
            Paragraph(item.description, dr),
            Paragraph(hrs,                              nr),
            Paragraph(_fmt(item.rate, cur),             nr),
            Paragraph(_fmt(item.amount, cur),           nr),
        ])

    li = Table(li_data, colWidths=[95 * mm, 20 * mm, 38 * mm, 23 * mm])
    li.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, SILVER]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [li, Spacer(1, 3 * mm)]

    # ── 5. Totals block ────────────────────────────────────────────────────────
    tl  = _s("tl",  size=9,  color=GREY,  align=TA_RIGHT)
    tv  = _s("tv",  size=9,  color=NAVY,  align=TA_RIGHT)
    ttl = _s("ttl", "Helvetica-Bold", 11, WHITE, TA_RIGHT)
    ttv = _s("ttv", "Helvetica-Bold", 11, WHITE, TA_RIGHT)

    gst_pct = int(b.gst_amount / b.subtotal * 100) if b.subtotal else 0
    totals_data = [
        [Paragraph("Subtotal",          tl), Paragraph(_fmt(b.subtotal,     cur), tv)],
        [Paragraph(f"GST ({gst_pct}%)", tl), Paragraph(_fmt(b.gst_amount,   cur), tv)],
        [Paragraph("TOTAL DUE",        ttl), Paragraph(_fmt(b.total_amount,  cur), ttv)],
    ]
    if cur != "INR":
        totals_data.append([
            Paragraph("Equivalent (INR)", tl),
            Paragraph(_inr(b.total_amount_inr), tv),
        ])

    totals = Table(totals_data, colWidths=[135 * mm, 41 * mm])
    totals.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 1), SILVER),
        ("BACKGROUND",    (0, 2), (-1, 2), BLUE),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEABOVE",     (0, 2), (-1, 2), 1.5, BLUE),
    ]))
    story += [totals, Spacer(1, 6 * mm)]

    # ── 6. Footer ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 3 * mm))

    if b.billing_notes:
        story.append(Paragraph("Billing Notes",
                               _s("bnt", "Helvetica-Bold", 8, NAVY)))
        story.append(Spacer(1, 1 * mm))
        for note in b.billing_notes:
            story.append(Paragraph(f"  {note}",
                                   _s(f"bn{note[:4]}", size=8, color=GREY)))
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        f"Please remit payment by <b>{invoice.due_date}</b>. "
        "For queries contact billing@tasc.ae",
        _s("pay", size=8, color=GREY),
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Generated by Sentinel  |  Touchless Invoice Automation  |  Powered by Gemini AI",
        _s("brand", "Helvetica-Oblique", 7, colors.HexColor("#CBD5E1"), TA_CENTER),
    ))

    return story
