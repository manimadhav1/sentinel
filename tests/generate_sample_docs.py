"""
Generate sample test documents:
  1. sample_timesheet.pdf  — clean typed timesheet
  2. sample_timesheet_handwritten.png — handwritten-style timesheet image

Run: venv/bin/python tests/generate_sample_docs.py
Output: data/sample_docs/
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pathlib import Path
import random

OUT = Path("data/sample_docs")
OUT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
# 1. PDF TIMESHEET
# ══════════════════════════════════════════════════════════════════════
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

NAVY  = colors.HexColor("#0F172A")
BLUE  = colors.HexColor("#2563EB")
LIGHT = colors.HexColor("#EFF6FF")
GREY  = colors.HexColor("#F8FAFC")
BORD  = colors.HexColor("#CBD5E1")
WHITE = colors.white

def _s(name, font="Helvetica", size=9, color=NAVY, align=None):
    kw = {"fontName": font, "fontSize": size, "textColor": color, "leading": size * 1.5}
    if align: kw["alignment"] = align
    return ParagraphStyle(name, **kw)

pdf_path = OUT / "sample_timesheet.pdf"
doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                        leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=20*mm, bottomMargin=20*mm)
story = []

# Header
hdr_data = [[
    Paragraph("TIMESHEET", _s("t", "Helvetica-Bold", 22, NAVY)),
    Paragraph("TASC Outsourcing\nbilling@tasc.ae\nDubai, UAE",
              _s("c", size=8, color=colors.grey, align=TA_RIGHT)),
]]
hdr = Table(hdr_data, colWidths=[90*mm, 90*mm])
hdr.setStyle(TableStyle([
    ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
    ("LINEBELOW", (0,0),(-1,0), 2, BLUE),
    ("BOTTOMPADDING", (0,0),(-1,0), 8),
]))
story += [hdr, Spacer(1, 6*mm)]

# Meta block
meta = [
    ["Employee ID",      "EMP001",              "Employee Name",   "Rahul Mehta"],
    ["Client Code",      "CUST001",             "Company",         "Emirates Steel Industries LLC"],
    ["Contract Ref",     "CON-EMP001-CL001",    "Currency",        "AED"],
    ["Billing Period",   "June 2026",           "Billing Type",    "Hourly"],
    ["Billing Rate",     "AED 44.27 / hour",    "Payment Terms",   "Net 30 days"],
]
meta_data = []
for row in meta:
    meta_data.append([
        Paragraph(row[0], _s(f"ml{row[0]}", "Helvetica-Bold", 8, colors.grey)),
        Paragraph(row[1], _s(f"mv{row[0]}", size=9, color=NAVY)),
        Paragraph(row[2], _s(f"ml2{row[0]}", "Helvetica-Bold", 8, colors.grey)),
        Paragraph(row[3], _s(f"mv2{row[0]}", size=9, color=NAVY)),
    ])
mt = Table(meta_data, colWidths=[40*mm, 55*mm, 40*mm, 45*mm])
mt.setStyle(TableStyle([
    ("ROWBACKGROUNDS", (0,0),(-1,-1), [WHITE, GREY]),
    ("GRID", (0,0),(-1,-1), 0.5, BORD),
    ("LEFTPADDING", (0,0),(-1,-1), 6),
    ("RIGHTPADDING", (0,0),(-1,-1), 6),
    ("TOPPADDING", (0,0),(-1,-1), 4),
    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
]))
story += [mt, Spacer(1, 6*mm)]

# Timesheet rows
story.append(Paragraph("Timesheet Detail — June 2026",
                        _s("sh", "Helvetica-Bold", 10, NAVY)))
story.append(Spacer(1, 3*mm))

from datetime import date, timedelta
import calendar

june_workdays = [
    date(2026, 6, d) for d in range(1, 31)
    if date(2026, 6, d).weekday() < 5
]

ts_data = [[
    Paragraph(h, _s(f"h{h}", "Helvetica-Bold", 8, WHITE))
    for h in ["Date", "Day", "Hours Worked", "Overtime Hrs", "Task Description"]
]]
total_reg = 0
total_ot  = 0
for d in june_workdays:
    hrs = 8.0
    ot  = round(random.choice([0, 0, 0, 1, 2]), 1)
    total_reg += hrs
    total_ot  += ot
    ts_data.append([
        Paragraph(d.strftime("%d %b %Y"), _s(f"td{d}", size=8, color=NAVY)),
        Paragraph(d.strftime("%A"),       _s(f"dy{d}", size=8, color=NAVY)),
        Paragraph(f"{hrs:.1f}",           _s(f"hw{d}", size=8, color=NAVY, align=TA_CENTER)),
        Paragraph(f"{ot:.1f}" if ot else "—", _s(f"ot{d}", size=8, color=NAVY, align=TA_CENTER)),
        Paragraph("Engineering & Development", _s(f"tk{d}", size=8, color=colors.grey)),
    ])

# Totals row
ts_data.append([
    Paragraph("TOTAL", _s("tot", "Helvetica-Bold", 8, WHITE)),
    Paragraph("", _s("t2", size=8, color=WHITE)),
    Paragraph(f"{total_reg:.1f}", _s("tr", "Helvetica-Bold", 8, WHITE, TA_CENTER)),
    Paragraph(f"{total_ot:.1f}",  _s("to", "Helvetica-Bold", 8, WHITE, TA_CENTER)),
    Paragraph(f"Contracted: 192h  |  Total Worked: {total_reg + total_ot:.1f}h",
              _s("tsub", "Helvetica-Bold", 8, WHITE)),
])

ts = Table(ts_data, colWidths=[25*mm, 22*mm, 25*mm, 25*mm, 83*mm])
ts.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,0), NAVY),
    ("BACKGROUND",    (0,-1),(-1,-1), BLUE),
    ("ROWBACKGROUNDS",(0,1),(-1,-2), [WHITE, GREY]),
    ("GRID", (0,0),(-1,-1), 0.5, BORD),
    ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ("RIGHTPADDING",  (0,0),(-1,-1), 5),
    ("TOPPADDING",    (0,0),(-1,-1), 4),
    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
]))
story += [ts, Spacer(1, 8*mm)]

# Signature block
sig_data = [[
    Paragraph("Employee Signature: ___________________\nName: Rahul Mehta\nDate: 30 June 2026",
              _s("sig", size=8, color=NAVY)),
    Paragraph("Manager Approval: ___________________\nName: ___________________\nDate: ___________________",
              _s("mgr", size=8, color=NAVY)),
]]
sig = Table(sig_data, colWidths=[90*mm, 90*mm])
sig.setStyle(TableStyle([
    ("BOX", (0,0),(0,0), 0.5, BORD),
    ("BOX", (1,0),(1,0), 0.5, BORD),
    ("LEFTPADDING", (0,0),(-1,-1), 10),
    ("TOPPADDING", (0,0),(-1,-1), 8),
    ("BOTTOMPADDING", (0,0),(-1,-1), 8),
]))
story += [sig, Spacer(1, 4*mm)]
story.append(Paragraph(
    "This timesheet was generated as a sample document for Sentinel Invoice Automation testing.",
    _s("ft", "Helvetica-Oblique", 7, colors.lightgrey, TA_CENTER),
))

doc.build(story)
print(f"✓ PDF timesheet: {pdf_path}")


# ══════════════════════════════════════════════════════════════════════
# 2. HANDWRITTEN IMAGE TIMESHEET
# ══════════════════════════════════════════════════════════════════════
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1240, 1754  # A4 at 150dpi
img  = Image.new("RGB", (W, H), color=(252, 248, 240))   # aged paper tone
draw = ImageDraw.Draw(img)

# Subtle grid lines (ruled paper effect)
for y in range(80, H, 38):
    draw.line([(40, y), (W-40, y)], fill=(200, 210, 220), width=1)

# Left margin red line
draw.line([(90, 0), (90, H)], fill=(220, 100, 100), width=2)

# ── Helper: draw text with slight random rotation (handwriting feel) ──
def hw(text, x, y, size=22, color=(20, 30, 60), bold=False):
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size)
    except Exception:
        font = ImageFont.load_default()
    # slight jitter
    jx = x + random.randint(-1, 1)
    jy = y + random.randint(-1, 1)
    draw.text((jx, jy), text, fill=color, font=font)

# ── Title ─────────────────────────────────────────────────────────────
hw("TIMESHEET", 350, 40, size=42, color=(15, 25, 80), bold=True)
hw("TASC Outsourcing — June 2026", 270, 95, size=22, color=(80, 80, 120))

# Underline
draw.line([(100, 130), (W-100, 130)], fill=(50, 80, 180), width=3)

# ── Employee info ─────────────────────────────────────────────────────
fields = [
    ("Employee ID :", "EMP001",          100, 160),
    ("Name :",        "Rahul Mehta",     100, 200),
    ("Client Code :", "CUST001",         640, 160),
    ("Department :",  "Engineering",     640, 200),
    ("Period :",      "June 2026",       100, 240),
    ("Rate :",        "AED 44.27/hr",    640, 240),
]
for label, val, fx, fy in fields:
    hw(label, fx, fy, size=20, color=(100, 100, 120))
    hw(val,   fx + len(label)*11, fy, size=20, color=(10, 20, 80), bold=True)

draw.line([(100, 285), (W-100, 285)], fill=(180, 180, 200), width=1)

# ── Table header ──────────────────────────────────────────────────────
headers = ["Date", "Day", "Start", "End", "Hrs", "OT Hrs", "Task / Notes"]
col_x   = [100, 240, 360, 460, 560, 650, 760]
for i, (htext, cx) in enumerate(zip(headers, col_x)):
    hw(htext, cx, 300, size=19, color=(30, 60, 160), bold=True)
draw.line([(100, 328), (W-100, 328)], fill=(50, 80, 180), width=2)

# ── Rows ──────────────────────────────────────────────────────────────
tasks = [
    "API development", "Code review", "Testing", "Documentation",
    "Client call", "Bug fixing", "Feature work", "Design review",
]
row_y = 340
total_hrs = 0
total_ot  = 0
for d in june_workdays[:20]:   # show first 20 rows (fits page)
    hrs = 8
    ot  = random.choice([0, 0, 0, 1, 2])
    task = random.choice(tasks)
    total_hrs += hrs
    total_ot  += ot
    row_color = (10, 20, 70) if row_y % 76 < 38 else (20, 40, 90)

    hw(d.strftime("%d/%m/%y"),  col_x[0], row_y, size=18, color=row_color)
    hw(d.strftime("%a"),        col_x[1], row_y, size=18, color=row_color)
    hw("09:00",                 col_x[2], row_y, size=18, color=row_color)
    hw("18:00",                 col_x[3], row_y, size=18, color=row_color)
    hw(str(hrs),                col_x[4], row_y, size=18, color=row_color)
    hw(str(ot) if ot else "-",  col_x[5], row_y, size=18, color=row_color)
    hw(task,                    col_x[6], row_y, size=17, color=(60, 60, 100))
    row_y += 38

# ── Totals ────────────────────────────────────────────────────────────
draw.line([(100, row_y+2), (W-100, row_y+2)], fill=(50, 80, 180), width=2)
hw(f"TOTAL REGULAR HOURS: {total_hrs}",    100, row_y + 10, size=20, color=(15, 25, 80), bold=True)
hw(f"TOTAL OVERTIME HOURS: {total_ot}",   640, row_y + 10, size=20, color=(15, 25, 80), bold=True)

# ── Signature ─────────────────────────────────────────────────────────
sig_y = row_y + 70
hw("Employee Signature: _________________________", 100, sig_y, size=19, color=(40, 40, 80))
hw("Date: 30 / 06 / 2026",                         100, sig_y + 40, size=19, color=(40, 40, 80))
hw("Manager Approval: _________________________",   640, sig_y, size=19, color=(40, 40, 80))
hw("Date: ____________________",                    640, sig_y + 40, size=19, color=(40, 40, 80))

# Slight paper texture noise
import random as rnd
for _ in range(3000):
    px = rnd.randint(0, W-1)
    py = rnd.randint(0, H-1)
    v  = rnd.randint(210, 240)
    img.putpixel((px, py), (v, v, v-10))

img_path = OUT / "sample_timesheet_handwritten.png"
img.save(str(img_path), dpi=(150, 150))
print(f"✓ Handwritten timesheet image: {img_path}")
print(f"\nBoth files saved to: {OUT.resolve()}")
