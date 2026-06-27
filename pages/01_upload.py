import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import SentinelPipeline
from utils.file_utils import save_upload

st.set_page_config(page_title="Upload — Sentinel", page_icon="📤", layout="wide")

# ── Shared CSS (hide default nav) ──────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }
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
st.markdown("<p style='color:#94A3B8'>Upload any timesheet document. Sentinel processes it automatically.</p>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Drop your timesheet here",
    type=["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg"],
    help="Supports PDF, Excel, CSV, and images",
)

if not uploaded:
    st.info("📂 Waiting for upload. Supported formats: PDF · Excel · CSV · Image")
    st.stop()

st.success(f"✓ File received: **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

if st.button("⚡ Process Document", type="primary", use_container_width=True):
    file_path = save_upload(uploaded.read(), uploaded.name)

    st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color:#F1F5F9'>Pipeline Progress</h3>", unsafe_allow_html=True)

    pipeline = SentinelPipeline()

    stages = {
        "document":   ("📄", "Document Engine", "Reading file with Gemini AI"),
        "processing": ("⚙️",  "Processing Engine", "Calculating billing & overtime"),
        "validation": ("✅", "Validation Engine", "Checking 14 business rules"),
        "invoice":    ("📋", "Invoice Engine", "Generating PDF & ERP Excel"),
        "database":   ("💾", "Database", "Saving to audit record"),
    }
    placeholders = {k: st.empty() for k in stages}

    def render_stage(stage, status, detail=""):
        icon_map  = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}
        color_map = {"pending": "#334155", "running": "#2563EB", "done": "#16A34A",
                     "failed": "#DC2626", "skipped": "#475569"}
        icon, label, sub = stages[stage]
        s_icon  = icon_map.get(status, "⏳")
        color   = color_map.get(status, "#334155")
        detail_html = f"<br><span style='font-size:12px;color:#94A3B8'>{detail}</span>" if detail else ""
        placeholders[stage].markdown(
            f"<div style='padding:10px 14px;border-radius:8px;border-left:4px solid {color};"
            f"background:#1E293B;margin:4px 0;color:#E2E8F0'>"
            f"{s_icon} <b>{icon} {label}</b> <span style='color:#64748B;font-size:12px'>— {sub}</span>"
            f"{detail_html}</div>",
            unsafe_allow_html=True,
        )

    for s in stages:
        render_stage(s, "pending")

    render_stage("document", "running")
    with st.spinner("Processing…"):
        result = pipeline.run(file_path)

    if result.document.status == "FAILED":
        render_stage("document", "failed", result.document.errors[0] if result.document.errors else "")
        for s in ["processing", "validation", "invoice", "database"]:
            render_stage(s, "skipped")
    elif result.routed_to_review:
        render_stage("document",   "done",    f"Confidence: {result.document.confidence:.0%}")
        render_stage("processing", "done" if result.processing else "skipped")
        render_stage("validation", "failed",  f"Routed to review queue #{result.review_queue_id}")
        render_stage("invoice",    "skipped")
        render_stage("database",   "skipped")
    else:
        render_stage("document",   "done", f"Confidence: {result.document.confidence:.0%}")
        pd = result.processing.data if result.processing and result.processing.data else {}
        render_stage("processing", "done" if result.processing else "skipped",
                     f"Total: {pd.get('currency','')} {pd.get('total_amount',0):,.2f}" if pd else "")
        vd = result.validation.data if result.validation and result.validation.data else {}
        render_stage("validation", "done" if result.validation else "skipped",
                     f"{vd.get('passed',0)}/{vd.get('total_checks',0)} checks passed" if vd else "")
        render_stage("invoice",  "done"   if result.invoice and result.invoice.status == "SUCCESS" else "failed")
        render_stage("database", "done"   if result.success else "skipped")

    st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

    # ── Result ─────────────────────────────────────────────────────────────────
    if result.success:
        st.balloons()
        st.success(f"### ✅ Invoice Generated: **{result.invoice_number}**")

        inv = result.invoice.data if result.invoice and result.invoice.data else {}
        b   = inv.get("billing", {})

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Amount",  f"{b.get('currency','AED')} {b.get('total_amount',0):,.2f}")
        c2.metric("Total (INR)",   f"₹{b.get('total_amount_inr',0):,.2f}")
        c3.metric("Confidence",    f"{result.document.confidence:.0%}")

        st.markdown("<br>", unsafe_allow_html=True)
        dc1, dc2 = st.columns(2)
        if result.pdf_path and Path(result.pdf_path).exists():
            with open(result.pdf_path, "rb") as f:
                dc1.download_button("📄 Download PDF Invoice", data=f.read(),
                    file_name=Path(result.pdf_path).name, mime="application/pdf",
                    use_container_width=True)
        if result.excel_path and Path(result.excel_path).exists():
            with open(result.excel_path, "rb") as f:
                dc2.download_button("📊 Download ERP Excel", data=f.read(),
                    file_name=Path(result.excel_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True)

        st.session_state["last_invoice_number"] = result.invoice_number

        vd = result.validation.data if result.validation and result.validation.data else {}
        if vd.get("report"):
            with st.expander("🔍 Validation Report"):
                for check in vd["report"]:
                    icon = "✅" if check["passed"] else ("⚠️" if check.get("severity") == "WARNING" else "❌")
                    st.markdown(f"{icon} **{check['rule']}** — {check['message']}")

        pd = result.processing.data if result.processing and result.processing.data else {}
        if pd:
            with st.expander("💰 Billing Breakdown"):
                cols = st.columns(4)
                cols[0].metric("Regular Hours",  f"{pd.get('regular_hours',0)}h")
                cols[1].metric("Overtime Hours", f"{pd.get('overtime_hours',0)}h")
                cols[2].metric("Subtotal",       f"{pd.get('currency','')} {pd.get('subtotal',0):,.2f}")
                cols[3].metric("GST",            f"{pd.get('currency','')} {pd.get('gst_amount',0):,.2f}")
                for note in pd.get("billing_notes", []):
                    st.caption(f"• {note}")

    elif result.routed_to_review:
        st.warning(f"### 🔍 Routed to Human Review — Queue #{result.review_queue_id}")
        st.metric("Confidence Score", f"{result.document.confidence:.0%}")
        if result.document.ambiguous_fields:
            st.markdown("**Ambiguous Fields:**")
            for af in result.document.ambiguous_fields:
                st.error(f"**{af.field_name}** — {af.reason} (extracted: `{af.extracted_value}`)")
        st.info("Visit the **Review Queue** page to resolve and regenerate.")
    else:
        st.error("### ❌ Processing Failed")
        for err in result.summary().get("errors", []):
            st.error(err)
