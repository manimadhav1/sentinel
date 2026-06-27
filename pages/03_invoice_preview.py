import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService
import config

st.set_page_config(page_title="Invoice Preview — Sentinel", page_icon="📄", layout="wide")

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

st.markdown("<h2 style='color:#F1F5F9'>📄 Invoice Preview</h2>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

# ── Invoice selector ───────────────────────────────────────────────────────────
invoices = DatabaseService.list_invoices(limit=50)

if not invoices:
    st.info("No invoices generated yet. Upload a timesheet to get started.")
    st.stop()

default_num = st.session_state.get("last_invoice_number")
inv_numbers = [i["invoice_number"] for i in invoices]
default_idx = inv_numbers.index(default_num) if default_num in inv_numbers else 0

selected = st.selectbox("Select Invoice", inv_numbers, index=default_idx)
inv = DatabaseService.get_invoice(selected)

if not inv:
    st.error("Invoice not found.")
    st.stop()

# ── Header ─────────────────────────────────────────────────────────────────────
col_title, col_status = st.columns([3, 1])
col_title.markdown(f"## {inv['invoice_number']}")

status_colors = {
    "GENERATED":  "#2563EB",
    "DISPATCHED": "#7C3AED",
    "PAID":       "#16A34A",
    "FLAGGED":    "#DC2626",
}
col_status.markdown(
    f"<div style='background:{status_colors.get(inv['status'],'#64748B')};"
    f"color:white;padding:8px 16px;border-radius:20px;text-align:center;"
    f"font-weight:700;margin-top:8px'>{inv['status']}</div>",
    unsafe_allow_html=True,
)

# ── Key metrics ────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Employee",   inv["employee_id"])
m2.metric("Client",     inv["client_id"])
m3.metric("Total",      f"{inv.get('currency','AED')} {inv['total_amount']:,.2f}")
m4.metric("Total (INR)",f"₹{inv['total_amount_inr']:,.2f}")

st.markdown("---")

# ── Details ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("#### Billing Period")
    st.markdown(f"**From:** {inv.get('billing_period_start','—')}")
    st.markdown(f"**To:**   {inv.get('billing_period_end','—')}")
    st.markdown(f"**Generated:** {inv.get('created_at','—')}")

with col_right:
    st.markdown("#### Financials")
    st.markdown(f"**Subtotal:** {inv.get('currency','AED')} {inv.get('subtotal',0):,.2f}")
    st.markdown(f"**GST:**      {inv.get('currency','AED')} {inv.get('gst_amount',0):,.2f}")
    st.markdown(f"**Total:**    {inv.get('currency','AED')} {inv['total_amount']:,.2f}")
    st.markdown(f"**INR Total:** ₹{inv['total_amount_inr']:,.2f}")

# ── Line items ─────────────────────────────────────────────────────────────────
if inv.get("line_items"):
    st.markdown("#### Line Items")
    import pandas as pd
    df = pd.DataFrame(inv["line_items"])
    cols_show = [c for c in ["description", "hours", "rate", "currency", "amount"] if c in df.columns]
    st.dataframe(df[cols_show] if cols_show else df, use_container_width=True, hide_index=True)

st.markdown("---")

# ── Downloads ──────────────────────────────────────────────────────────────────
st.markdown("#### Downloads")
dc1, dc2, dc3 = st.columns(3)

pdf_path   = inv.get("pdf_path")
excel_path = inv.get("excel_path")

if pdf_path and Path(pdf_path).exists():
    with open(pdf_path, "rb") as f:
        dc1.download_button(
            "📄 Download PDF",
            data=f.read(),
            file_name=Path(pdf_path).name,
            mime="application/pdf",
            use_container_width=True,
        )
else:
    dc1.caption("PDF not available")

if excel_path and Path(excel_path).exists():
    with open(excel_path, "rb") as f:
        dc2.download_button(
            "📊 Download ERP Excel",
            data=f.read(),
            file_name=Path(excel_path).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
else:
    dc2.caption("Excel not available")

# ── Status update ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Update Status")
new_status = st.selectbox(
    "Mark as",
    ["GENERATED", "DISPATCHED", "PAID", "FLAGGED"],
    index=["GENERATED", "DISPATCHED", "PAID", "FLAGGED"].index(inv["status"]),
)
if new_status != inv["status"]:
    if st.button(f"Update to {new_status}", type="primary"):
        DatabaseService.update_invoice_status(selected, new_status)
        st.success(f"Status updated to {new_status}")
        st.rerun()

# ── Audit log ──────────────────────────────────────────────────────────────────
log = DatabaseService.get_audit_log(selected)
if log:
    with st.expander(f"📋 Audit Log ({len(log)} events)"):
        for entry in log:
            st.markdown(
                f"`{entry.get('created_at','—')}` — **{entry['event_type']}**"
                + (f": {entry['details']}" if entry.get("details") else "")
            )
