import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import SentinelPipeline
from utils.file_utils import save_upload

st.set_page_config(page_title="Upload — Sentinel", page_icon="📤", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }
.result-card {
    background: #1E293B; border-radius: 12px; padding: 20px;
    border: 1px solid #334155; margin: 8px 0;
}
.conf-bar-wrap { background: #334155; border-radius: 4px; height: 8px; margin-top: 4px; }
.conf-bar      { background: #2563EB; border-radius: 4px; height: 8px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<div style='padding:16px 8px 8px'><span style='font-size:22px;font-weight:800;color:#F1F5F9'>⚡ Sentinel</span></div>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#1E293B;margin:8px 0'>", unsafe_allow_html=True)
    st.page_link("app.py",                       label="🏠  Home")
    st.page_link("pages/01_upload.py",            label="📤  Upload & Process")
    st.page_link("pages/02_review_queue.py",      label="🔍  Review Queue")
    st.page_link("pages/03_invoice_preview.py",   label="📄  Invoice Preview")
    st.page_link("pages/04_dashboard.py",         label="📊  Dashboard")

st.markdown("<h2 style='color:#F1F5F9'>📤 Upload & Process</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#94A3B8'>Upload any timesheet. Sentinel auto-generates the invoice if confidence ≥ 75%.</p>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Drop your timesheet here",
    type=["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg"],
    help="Supports PDF, Excel, CSV, and images (handwritten or typed)",
)

if not uploaded:
    # Show supported formats
    st.markdown("""
    <div style='background:#1E293B;border-radius:12px;padding:24px;text-align:center;border:2px dashed #334155;margin-top:16px'>
        <div style='font-size:40px;margin-bottom:12px'>📂</div>
        <p style='color:#94A3B8;margin:0'>Drop any timesheet document above</p>
        <p style='color:#475569;font-size:13px;margin:8px 0 0'>PDF &nbsp;·&nbsp; Excel (XLSX/XLS) &nbsp;·&nbsp; CSV &nbsp;·&nbsp; PNG/JPG (typed or handwritten)</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.markdown(
    f"<div style='background:#0F2027;border:1px solid #2563EB;border-radius:8px;padding:12px 16px;color:#93C5FD'>"
    f"📎 <b>{uploaded.name}</b> &nbsp; <span style='color:#475569'>({uploaded.size/1024:.1f} KB)</span>"
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

if not st.button("⚡ Process Document", type="primary", use_container_width=True):
    st.stop()

file_path = save_upload(uploaded.read(), uploaded.name)

# ── Pipeline stages ────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)
st.markdown("<h3 style='color:#F1F5F9'>Pipeline Progress</h3>", unsafe_allow_html=True)

stages = {
    "document":   ("📄", "Document Engine",   "Reading & extracting with Gemini AI"),
    "processing": ("⚙️",  "Processing Engine", "Calculating billing & overtime"),
    "validation": ("✅", "Validation Engine", "Checking 14 business rules"),
    "invoice":    ("📋", "Invoice Engine",    "Generating PDF & ERP Excel"),
    "database":   ("💾", "Database",          "Saving to audit record"),
}
placeholders = {k: st.empty() for k in stages}

def render_stage(stage, status, detail=""):
    icon_s = {"pending":"⏳","running":"🔄","done":"✅","failed":"❌","skipped":"⏭️","warn":"⚠️"}.get(status,"⏳")
    color  = {"done":"#16A34A","failed":"#DC2626","running":"#2563EB",
               "skipped":"#334155","warn":"#D97706","pending":"#1E293B"}.get(status,"#1E293B")
    icon, label, sub = stages[stage]
    detail_html = f"<br><span style='font-size:12px;color:#94A3B8;margin-left:24px'>{detail}</span>" if detail else ""
    placeholders[stage].markdown(
        f"<div style='padding:10px 14px;border-radius:8px;border-left:4px solid {color};"
        f"background:#1E293B;margin:4px 0;color:#E2E8F0'>"
        f"{icon_s} <b>{icon} {label}</b>"
        f"<span style='color:#475569;font-size:12px'> — {sub}</span>"
        f"{detail_html}</div>",
        unsafe_allow_html=True,
    )

for s in stages:
    render_stage(s, "pending")

render_stage("document", "running")
with st.spinner("Processing your document…"):
    pipeline = SentinelPipeline()
    result   = pipeline.run(file_path)

# Update all stage statuses
doc = result.document
pd_  = result.processing
vd_  = result.validation
inv_ = result.invoice

if doc.status == "FAILED":
    render_stage("document",   "failed",  doc.errors[0] if doc.errors else "Extraction failed")
    for s in ["processing","validation","invoice","database"]: render_stage(s, "skipped")
else:
    conf = doc.confidence
    conf_color = "#16A34A" if conf >= 0.90 else "#D97706" if conf >= 0.75 else "#DC2626"
    render_stage("document", "done", f"Confidence: <b style='color:{conf_color}'>{conf:.0%}</b>")

    if pd_:
        amt = pd_.data.get("total_amount",0) if pd_.data else 0
        cur = pd_.data.get("currency","") if pd_.data else ""
        render_stage("processing", "done" if pd_.status=="SUCCESS" else "failed",
                     f"Total: <b>{cur} {amt:,.2f}</b>")
    else:
        render_stage("processing", "skipped")

    if vd_:
        chk = vd_.data or {}
        if vd_.status == "SUCCESS":
            render_stage("validation", "done",
                         f"{chk.get('passed',0)}/{chk.get('total_checks',0)} checks passed")
        else:
            err = vd_.errors[0] if vd_.errors else "Validation failed"
            render_stage("validation", "failed" if not result.is_duplicate else "warn",
                         f"{'Duplicate — existing invoice returned' if result.is_duplicate else err}")
    else:
        render_stage("validation", "skipped")

    if result.success:
        render_stage("invoice",  "done")
        render_stage("database", "done" if not result.is_duplicate else "skipped",
                     "Already saved" if result.is_duplicate else "")
    else:
        render_stage("invoice",  "skipped")
        render_stage("database", "skipped")

# ── Result section ─────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

if result.success:
    if result.is_duplicate:
        st.warning(f"**Duplicate document** — this invoice already exists. Showing the existing record.")

    # ── Invoice card ──────────────────────────────────────────────────────────
    inv_data = result.invoice.data if result.invoice else {}
    b        = inv_data.get("billing", {})
    currency = b.get("currency", inv_data.get("currency", "AED"))
    total    = b.get("total_amount", inv_data.get("total_amount", 0))
    total_inr= b.get("total_amount_inr", inv_data.get("total_amount_inr", 0))

    st.markdown(
        f"<div style='background:#0F2027;border:1px solid #16A34A;border-radius:12px;padding:20px;margin:12px 0'>"
        f"<p style='color:#4ADE80;font-size:12px;margin:0'>INVOICE GENERATED</p>"
        f"<h2 style='color:#F1F5F9;margin:4px 0'>{result.invoice_number}</h2>"
        f"<p style='color:#64748B;font-size:13px;margin:0'>Employee: {inv_data.get('employee_name','')} &nbsp;|&nbsp; "
        f"Client: {inv_data.get('client_name','')} &nbsp;|&nbsp; "
        f"Period: {inv_data.get('billing_period_start','')} → {inv_data.get('billing_period_end','')}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Key numbers ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Amount",     f"{currency} {total:,.2f}")
    c2.metric("INR Equivalent",   f"₹{total_inr:,.2f}")
    c3.metric("AI Confidence",    f"{doc.confidence:.0%}")
    c4.metric("Status",           "DUPLICATE" if result.is_duplicate else "✅ GENERATED")

    # ── Downloads ─────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<p style='color:#94A3B8;font-size:13px;margin-bottom:8px'>📥 DOWNLOAD</p>", unsafe_allow_html=True)
    dc1, dc2 = st.columns(2)

    pdf_p = result.pdf_path or inv_data.get("pdf_path","")
    xls_p = result.excel_path or inv_data.get("excel_path","")

    if pdf_p and Path(pdf_p).exists():
        with open(pdf_p, "rb") as f:
            dc1.download_button("📄 Download PDF Invoice", data=f.read(),
                file_name=Path(pdf_p).name, mime="application/pdf",
                use_container_width=True, type="primary")
    else:
        dc1.caption("PDF not available")

    if xls_p and Path(xls_p).exists():
        with open(xls_p, "rb") as f:
            dc2.download_button("📊 Download ERP Excel", data=f.read(),
                file_name=Path(xls_p).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
    else:
        dc2.caption("Excel not available")

    st.session_state["last_invoice_number"] = result.invoice_number

    # ── Confidence breakdown ──────────────────────────────────────────────────
    scores = doc.metadata.get("confidence_scores", {})
    if scores:
        with st.expander("🎯 AI Confidence Breakdown"):
            for field, score in scores.items():
                if field == "overall": continue
                try:
                    pct = float(score)
                    color = "#4ADE80" if pct >= 0.90 else "#FCD34D" if pct >= 0.75 else "#F87171"
                    st.markdown(
                        f"<div style='margin:6px 0'>"
                        f"<div style='display:flex;justify-content:space-between'>"
                        f"<span style='color:#CBD5E1;font-size:13px;text-transform:capitalize'>{field}</span>"
                        f"<span style='color:{color};font-size:13px;font-weight:700'>{pct:.0%}</span>"
                        f"</div>"
                        f"<div style='background:#334155;border-radius:4px;height:6px;margin-top:3px'>"
                        f"<div style='background:{color};border-radius:4px;height:6px;width:{pct*100:.0f}%'></div>"
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                except Exception:
                    pass

    # ── Validation report ─────────────────────────────────────────────────────
    if vd_ and vd_.data and vd_.data.get("report"):
        with st.expander("✅ Validation Report — 14 Rules"):
            for chk in vd_.data["report"]:
                icon = "✅" if chk["passed"] else ("⚠️" if chk.get("severity")=="WARNING" else "❌")
                color = "#4ADE80" if chk["passed"] else "#FCD34D" if chk.get("severity")=="WARNING" else "#F87171"
                st.markdown(
                    f"<div style='padding:5px 0;border-bottom:1px solid #1E293B'>"
                    f"{icon} <span style='color:{color};font-weight:600'>{chk['rule']}</span>"
                    f" <span style='color:#64748B;font-size:12px'>— {chk['message']}</span></div>",
                    unsafe_allow_html=True,
                )

    # ── Billing breakdown ─────────────────────────────────────────────────────
    if pd_ and pd_.data:
        bd = pd_.data
        with st.expander("💰 Billing Breakdown"):
            bc1, bc2, bc3, bc4 = st.columns(4)
            bc1.metric("Regular Hours",  f"{bd.get('regular_hours',0)}h")
            bc2.metric("Overtime Hours", f"{bd.get('overtime_hours',0)}h")
            bc3.metric("Subtotal",       f"{currency} {bd.get('subtotal',0):,.2f}")
            bc4.metric("GST",            f"{currency} {bd.get('gst_amount',0):,.2f}")
            for note in bd.get("billing_notes", []):
                st.caption(f"• {note}")

elif result.routed_to_review:
    # Determine the real reason for routing
    conf = doc.confidence
    failed_stage = result.validation or result.processing or doc

    if result.validation and result.validation.status == "FAILED":
        route_reason = "Data validation failed — document is missing required fields"
        route_detail = "The document was read successfully but failed one or more validation checks. A reviewer must fill in the missing data before the invoice can be generated."
        route_color  = "#B45309"
    elif conf < 0.75:
        route_reason = f"AI extraction confidence too low ({conf:.0%})"
        route_detail = "The document was unclear or had too many ambiguous fields. A reviewer must verify the extracted data before proceeding."
        route_color  = "#B45309"
    else:
        route_reason = "Manual review required"
        route_detail = "This document has been flagged for human verification before the invoice can be generated."
        route_color  = "#B45309"

    st.markdown(
        f"<div style='background:#1C1408;border:1px solid #D97706;border-radius:12px;padding:20px;margin:12px 0'>"
        f"<p style='color:#FCD34D;font-size:14px;font-weight:700;margin:0 0 6px'>🔍 NEEDS HUMAN REVIEW — Queue #{result.review_queue_id}</p>"
        f"<p style='color:#FCD34D;font-size:13px;font-weight:600;margin:0 0 4px'>{route_reason}</p>"
        f"<p style='color:#94A3B8;font-size:12px;margin:0'>{route_detail}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    c1.metric("AI Confidence Score", f"{conf:.0%}", help="Confidence in the AI's data extraction from the document")
    c2.metric("Review Queue #", result.review_queue_id)

    errors = failed_stage.errors if failed_stage else []
    if errors:
        st.markdown("<p style='color:#F87171;font-weight:600;margin:12px 0 4px'>What the reviewer needs to fix:</p>", unsafe_allow_html=True)
        for e in errors:
            st.error(f"⛔ {e}")

    warnings = failed_stage.warnings if failed_stage else []
    if warnings:
        for w in warnings[:3]:
            st.warning(w)

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👉 Go to the **Review Queue** page to approve or reject this document.")

else:
    st.markdown(
        "<div style='background:#1C0808;border:1px solid #DC2626;border-radius:12px;padding:20px;margin:12px 0'>"
        "<p style='color:#F87171;font-size:14px;margin:0 0 8px'>❌ PROCESSING FAILED</p></div>",
        unsafe_allow_html=True,
    )
    for e in result.summary().get("errors", []):
        st.error(e)
