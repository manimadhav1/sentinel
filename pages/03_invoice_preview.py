"""
Invoice Browser — view, preview, and download invoices for all clients.
"""
import json
import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService
from utils.invoice_html import render_invoice_html

st.set_page_config(page_title="Invoice Preview — Sentinel", page_icon="📄", layout="wide")

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }
div[data-testid="stTabs"] button { color: #94A3B8 !important; }
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #F1F5F9 !important; border-bottom-color: #2563EB !important; }

/* Invoice card */
.inv-card { background: #1E293B; border-radius: 8px; padding: 12px 14px;
            margin-bottom: 8px; border-left: 3px solid #334155; cursor: pointer;
            transition: border-color 0.15s; }
.inv-card:hover { border-left-color: #2563EB; }
.inv-card.active { border-left-color: #2563EB; background: #1A2E47; }
.inv-card .inv-num  { color: #93C5FD; font-size: 12px; font-weight: 700; }
.inv-card .inv-name { color: #F1F5F9; font-size: 13px; font-weight: 600; margin: 2px 0; }
.inv-card .inv-sub  { color: #64748B; font-size: 11px; }
.inv-card .inv-amt  { color: #4ADE80; font-size: 13px; font-weight: 700; text-align: right; }

/* Stat pill */
.stat-pill { display:inline-block; padding:3px 10px; border-radius:20px;
             font-size:11px; font-weight:700; margin-right:4px; }
</style>
""", unsafe_allow_html=True)

STATUS_COLORS = {
    "GENERATED":  "#2563EB",
    "DISPATCHED": "#7C3AED",
    "PAID":       "#16A34A",
    "FLAGGED":    "#DC2626",
}
STATUS_BG = {
    "GENERATED":  "#172554",
    "DISPATCHED": "#2E1065",
    "PAID":       "#052e16",
    "FLAGGED":    "#450a0a",
}

# ── Sidebar nav ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='padding:16px 8px 8px'>"
        "<span style='font-size:22px;font-weight:800;color:#F1F5F9'>⚡ Sentinel</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<hr style='border-color:#1E293B;margin:8px 0'>", unsafe_allow_html=True)
    st.page_link("app.py",                     label="🏠  Home")
    st.page_link("pages/01_upload.py",          label="📤  Upload & Process")
    st.page_link("pages/02_review_queue.py",    label="🔍  Review Queue")
    st.page_link("pages/03_invoice_preview.py", label="📄  Invoice Preview")
    st.page_link("pages/04_dashboard.py",       label="📊  Dashboard")

# ── Load all invoices ──────────────────────────────────────────────────────────
all_invoices = DatabaseService.list_invoices(limit=500)

# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("<h2 style='color:#F1F5F9;margin:0'>📄 Invoice Browser</h2>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#94A3B8;margin:0 0 8px'>Browse, preview, and download invoices for all clients.</p>",
    unsafe_allow_html=True,
)

if not all_invoices:
    st.info("No invoices generated yet. Upload a timesheet on the **Upload & Process** page.")
    st.stop()

# ── Summary strip ──────────────────────────────────────────────────────────────
total_invoices = len(all_invoices)
unique_clients = len({i["client_id"] for i in all_invoices})
unique_employees = len({i["employee_id"] for i in all_invoices})
total_aed = sum(i["total_amount"] for i in all_invoices if i.get("currency") == "AED")

s1, s2, s3, s4 = st.columns(4)
s1.metric("Total Invoices",  total_invoices)
s2.metric("Clients Covered", unique_clients)
s3.metric("Employees",       unique_employees)
s4.metric("Total Billed",    f"AED {total_aed:,.2f}")

st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)

# ── Determine default selection ────────────────────────────────────────────────
sess = st.session_state.get("sentinel_state", {})
default_num = None
if sess.get("success") and sess.get("invoice_number"):
    default_num = sess["invoice_number"]
elif st.session_state.get("last_invoice_number"):
    default_num = st.session_state["last_invoice_number"]
if not default_num and all_invoices:
    default_num = all_invoices[0]["invoice_number"]

if "preview_selected" not in st.session_state:
    st.session_state["preview_selected"] = default_num

# ── MAIN LAYOUT: left filter+list | right preview ─────────────────────────────
col_list, col_preview = st.columns([1, 2], gap="medium")

# ══════════════════════════════════════════════════════════════════════════════
# LEFT PANEL — Filters + Invoice List
# ══════════════════════════════════════════════════════════════════════════════
with col_list:
    st.markdown("<p style='color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;margin:0 0 8px'>FILTER & SELECT</p>",
                unsafe_allow_html=True)

    # ── Client filter ──────────────────────────────────────────────────────────
    client_options = sorted({(i["client_id"], i.get("client_name") or i["client_id"])
                              for i in all_invoices}, key=lambda x: x[0])
    client_labels  = ["All Clients"] + [f"{cid} — {cname}" for cid, cname in client_options]
    client_ids     = [None] + [cid for cid, _ in client_options]

    sel_client_label = st.selectbox("Client", client_labels, key="filter_client")
    sel_client_id    = client_ids[client_labels.index(sel_client_label)]

    # ── Status filter ──────────────────────────────────────────────────────────
    status_options = ["All Statuses"] + sorted({i["status"] for i in all_invoices})
    sel_status     = st.selectbox("Status", status_options, key="filter_status")
    sel_status_val = None if sel_status == "All Statuses" else sel_status

    # ── Employee search ────────────────────────────────────────────────────────
    emp_search = st.text_input("Search employee", placeholder="Type name…", key="filter_emp").strip().lower()

    # ── Apply filters ──────────────────────────────────────────────────────────
    filtered = all_invoices
    if sel_client_id:
        filtered = [i for i in filtered if i["client_id"] == sel_client_id]
    if sel_status_val:
        filtered = [i for i in filtered if i["status"] == sel_status_val]
    if emp_search:
        filtered = [i for i in filtered if emp_search in (i.get("employee_name") or "").lower()]

    st.markdown(
        f"<p style='color:#475569;font-size:12px;margin:8px 0 6px'>"
        f"Showing <b style='color:#F1F5F9'>{len(filtered)}</b> of {total_invoices} invoices</p>",
        unsafe_allow_html=True,
    )

    # ── Invoice cards ──────────────────────────────────────────────────────────
    if not filtered:
        st.info("No invoices match the current filters.")
    else:
        for inv_row in filtered:
            num      = inv_row["invoice_number"]
            is_sel   = (st.session_state["preview_selected"] == num)
            s_color  = STATUS_COLORS.get(inv_row["status"], "#64748B")
            cur      = inv_row.get("currency", "AED")
            amount   = inv_row.get("total_amount", 0)
            emp      = inv_row.get("employee_name") or inv_row.get("employee_id", "—")
            cname    = inv_row.get("client_name") or inv_row.get("client_id", "—")
            period   = f"{inv_row.get('billing_period_start','')[:7]}"  # YYYY-MM
            bg       = "#1A2E47" if is_sel else "#1E293B"
            border   = "#2563EB" if is_sel else "#334155"

            # Render card as HTML for styling
            st.markdown(
                f"<div style='background:{bg};border-radius:8px;padding:10px 12px;"
                f"margin-bottom:6px;border-left:3px solid {border}'>"
                f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                f"<div>"
                f"<span style='color:#93C5FD;font-size:11px;font-weight:700'>{num}</span>"
                f"<span style='float:right;background:{s_color}22;color:{s_color};"
                f"border:1px solid {s_color}55;padding:1px 8px;border-radius:10px;"
                f"font-size:10px;font-weight:700'>{inv_row['status']}</span><br>"
                f"<span style='color:#F1F5F9;font-size:13px;font-weight:600'>{cname}</span><br>"
                f"<span style='color:#94A3B8;font-size:11px'>{emp}</span>"
                f"<span style='color:#475569;font-size:11px'> · {period}</span>"
                f"</div></div>"
                f"<div style='margin-top:6px;display:flex;justify-content:space-between;align-items:center'>"
                f"<span style='color:#475569;font-size:11px'>{inv_row.get('contract_id','—')}</span>"
                f"<span style='color:#4ADE80;font-size:14px;font-weight:800'>{cur} {amount:,.2f}</span>"
                f"</div></div>",
                unsafe_allow_html=True,
            )
            if st.button("View →", key=f"sel_{num}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state["preview_selected"] = num
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# RIGHT PANEL — Invoice Preview
# ══════════════════════════════════════════════════════════════════════════════
with col_preview:
    sel_num = st.session_state.get("preview_selected")
    if not sel_num:
        st.info("Select an invoice from the list on the left.")
        st.stop()

    inv = DatabaseService.get_invoice(sel_num)
    if not inv:
        st.error(f"Invoice {sel_num} not found in database.")
        st.stop()

    # ── Reconstruct full invoice dict from invoice_json ────────────────────────
    inv_json = {}
    if inv.get("invoice_json"):
        try:
            inv_json = json.loads(inv["invoice_json"])
        except Exception:
            pass

    billing = inv_json.get("billing", {})
    if not billing:
        billing = {
            "currency":         inv.get("currency", "AED"),
            "subtotal":         inv.get("total_amount", 0),
            "gst_amount":       inv.get("gst_amount", 0),
            "total_amount":     inv.get("total_amount", 0),
            "total_amount_inr": inv.get("total_amount_inr", 0),
            "line_items":       [],
            "billing_notes":    [],
        }

    full_inv = {**inv, **inv_json, "billing": billing}

    # ── Invoice header card ────────────────────────────────────────────────────
    _sb   = STATUS_COLORS.get(inv["status"], "#64748B")
    _sbbg = STATUS_BG.get(inv["status"], "#1E293B")
    cur   = inv.get("currency", "AED")

    st.markdown(
        f"<div style='background:linear-gradient(135deg,#0F1F3D,#0F2027);"
        f"border:1px solid {_sb}55;border-radius:12px;padding:18px 22px;margin-bottom:14px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
        f"<div>"
        f"<p style='color:#94A3B8;font-size:10px;font-weight:700;letter-spacing:1px;margin:0'>INVOICE</p>"
        f"<h2 style='color:#F1F5F9;font-size:20px;margin:2px 0'>{inv['invoice_number']}</h2>"
        f"<p style='color:#64748B;font-size:12px;margin:2px 0'>"
        f"<b style='color:#CBD5E1'>{inv.get('client_name') or inv.get('client_id','—')}</b>"
        f" &nbsp;·&nbsp; {inv.get('employee_name','—')}"
        f" &nbsp;·&nbsp; {inv.get('billing_period_start','')[:7]}"
        f"</p>"
        f"<p style='color:#475569;font-size:11px;margin:2px 0'>"
        f"Contract: {inv.get('contract_id','—')} &nbsp;·&nbsp; "
        f"Issued: {inv.get('invoice_date','—')} &nbsp;·&nbsp; "
        f"Due: {inv.get('due_date','—')}</p>"
        f"</div>"
        f"<div style='text-align:right'>"
        f"<span style='background:{_sbbg};color:{_sb};border:1px solid {_sb}55;"
        f"padding:4px 14px;border-radius:20px;font-size:11px;font-weight:700'>"
        f"{inv['status']}</span>"
        f"<p style='color:#4ADE80;font-size:26px;font-weight:800;margin:8px 0 0'>"
        f"{cur} {inv['total_amount']:,.2f}</p>"
        f"<p style='color:#475569;font-size:12px;margin:0'>≈ ₹{inv['total_amount_inr']:,.2f}</p>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    # ── Quick KPIs ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Regular Hrs",  f"{inv.get('regular_hours', 0):,.1f}h")
    k2.metric("OT Hrs",       f"{inv.get('overtime_hours', 0):,.1f}h")
    k3.metric("GST",          f"{cur} {inv.get('gst_amount', 0):,.2f}")
    k4.metric("Total",        f"{cur} {inv['total_amount']:,.2f}")
    k5.metric("INR Total",    f"₹{inv['total_amount_inr']:,.2f}")

    # ── Download buttons (always visible, above tabs) ──────────────────────────
    st.markdown("<p style='color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;margin:10px 0 6px'>DOWNLOAD</p>",
                unsafe_allow_html=True)
    dl1, dl2, dl3 = st.columns([2, 2, 1])

    pdf_path   = inv.get("pdf_path") or inv_json.get("pdf_path")
    excel_path = inv.get("excel_path") or inv_json.get("excel_path")

    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            dl1.download_button(
                "📄 Download PDF",
                data=f.read(),
                file_name=Path(pdf_path).name,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
                key=f"pdf_{sel_num}",
            )
    else:
        dl1.caption("PDF not on disk")

    if excel_path and Path(excel_path).exists():
        with open(excel_path, "rb") as f:
            dl2.download_button(
                "📊 Download ERP Excel",
                data=f.read(),
                file_name=Path(excel_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"xls_{sel_num}",
            )
    else:
        dl2.caption("Excel not on disk")

    # Status update
    statuses = ["GENERATED", "DISPATCHED", "PAID", "FLAGGED"]
    cur_idx  = statuses.index(inv["status"]) if inv["status"] in statuses else 0
    new_status = dl3.selectbox("Status", statuses, index=cur_idx,
                                key=f"status_{sel_num}", label_visibility="collapsed")
    if new_status != inv["status"]:
        DatabaseService.update_invoice_status(sel_num, new_status)
        st.success(f"Status updated to {new_status}")
        st.rerun()

    st.markdown("<hr style='border-color:#1E293B;margin:10px 0'>", unsafe_allow_html=True)

    # ── Tabs: Preview | Line Items | Audit ────────────────────────────────────
    t_prev, t_lines, t_audit = st.tabs(["📄 Invoice Preview", "📋 Line Items & Details", "🔎 Audit Log"])

    with t_prev:
        st.markdown(
            "<p style='color:#64748B;font-size:11px;margin:0 0 8px'>"
            "Inline preview — identical to the PDF output.</p>",
            unsafe_allow_html=True,
        )
        html = render_invoice_html(full_inv)
        st.components.v1.html(html, height=700, scrolling=True)

    with t_lines:
        line_items = billing.get("line_items", [])
        if line_items:
            import pandas as pd
            df = pd.DataFrame(line_items)
            if "amount" in df.columns:
                df["amount"] = df["amount"].apply(lambda x: f"{cur} {float(x):,.2f}")
            if "rate" in df.columns:
                df["rate"] = df["rate"].apply(lambda x: f"{cur} {float(x):,.2f}")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No line items on record for this invoice.")

        st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)

        # Financial summary
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown("**Billing Period**")
            st.markdown(f"From: `{inv.get('billing_period_start','—')}`")
            st.markdown(f"To: `{inv.get('billing_period_end','—')}`")
            st.markdown(f"Invoice Date: `{inv.get('invoice_date','—')}`")
            st.markdown(f"Due Date: `{inv.get('due_date','—')}`")
        with fc2:
            st.markdown("**Financial Summary**")
            subtotal = billing.get("subtotal", inv.get("total_amount", 0))
            gst      = billing.get("gst_amount", inv.get("gst_amount", 0))
            total    = billing.get("total_amount", inv.get("total_amount", 0))
            st.markdown(f"Subtotal: `{cur} {subtotal:,.2f}`")
            st.markdown(f"GST: `{cur} {gst:,.2f}`")
            st.markdown(f"**Total: `{cur} {total:,.2f}`**")
            st.markdown(f"INR: `₹{inv.get('total_amount_inr', 0):,.2f}`")

        for note in billing.get("billing_notes", []):
            st.caption(f"• {note}")

    with t_audit:
        log = DatabaseService.get_audit_log(sel_num)
        if not log:
            st.info("No audit events recorded for this invoice.")
        else:
            for entry in log:
                st.markdown(
                    f"`{entry.get('created_at','—')}` — **{entry['event_type']}**"
                    + (f": {entry['details']}" if entry.get("details") else "")
                )
