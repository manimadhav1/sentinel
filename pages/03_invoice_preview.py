"""
Invoice Browser — clean multi-client invoice viewer with inline preview and downloads.
"""
import json
import requests
import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService
from utils.invoice_html import render_invoice_html
from streamlit_mic_recorder import mic_recorder
import config

st.set_page_config(page_title="Invoices — Sentinel", page_icon="📄", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }

/* Clean invoice row */
.inv-row { display:flex; align-items:center; gap:12px; padding:12px 16px;
           border-radius:8px; margin:4px 0; cursor:pointer; }
.inv-row:hover { background:#1E3A5F; }
.inv-row.sel   { background:#1E3A5F; border-left:3px solid #2563EB; }

div[data-testid="stTabs"] button { color: #94A3B8 !important; font-size:13px; }
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #F1F5F9 !important; border-bottom-color: #2563EB !important; }
</style>
""", unsafe_allow_html=True)

_STATUS_COLOR = {
    "GENERATED":  ("#2563EB", "#172554"),
    "DISPATCHED": ("#7C3AED", "#2E1065"),
    "PAID":       ("#16A34A", "#052e16"),
    "FLAGGED":    ("#DC2626", "#450a0a"),
}

# ── Sidebar ────────────────────────────────────────────────────
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

# ── Load data ──────────────────────────────────────────────────
all_invoices = DatabaseService.list_invoices(limit=500)

st.markdown("<h2 style='color:#F1F5F9;margin:0 0 4px'>📄 Invoices</h2>", unsafe_allow_html=True)

if not all_invoices:
    st.info("No invoices yet. Upload a timesheet on the **Upload & Process** page.")
    st.stop()

# ── Top stats bar ──────────────────────────────────────────────
n_inv  = len(all_invoices)
n_cli  = len({i["client_id"] for i in all_invoices})
n_emp  = len({i["employee_id"] for i in all_invoices})
n_paid = sum(1 for i in all_invoices if i["status"] == "PAID")
total_billed = sum(i["total_amount"] for i in all_invoices)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Invoices",  n_inv)
c2.metric("Clients",         n_cli)
c3.metric("Employees",       n_emp)
c4.metric("Paid",            n_paid)
c5.metric("Total Billed",    f"AED {total_billed:,.0f}")

st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)

# ── Default selection ──────────────────────────────────────────
sess = st.session_state.get("sentinel_state", {})
default_num = (
    (sess.get("invoice_number") if sess.get("success") else None)
    or st.session_state.get("last_invoice_number")
    or all_invoices[0]["invoice_number"]
)
if "preview_selected" not in st.session_state:
    st.session_state["preview_selected"] = default_num

# ── Main layout ────────────────────────────────────────────────
left, right = st.columns([5, 8], gap="large")

# ══════════════════════════════════════════════════════════════
# LEFT: Filter + Invoice List
# ══════════════════════════════════════════════════════════════
with left:
    # ── Filters ────────────────────────────────────────────────
    search = st.text_input("🔍  Search client or employee", placeholder="Type to filter…",
                           key="inv_search", label_visibility="collapsed").strip().lower()

    f1, f2 = st.columns(2)
    client_ids   = sorted({i["client_id"] for i in all_invoices})
    client_names = {i["client_id"]: (i.get("client_name") or i["client_id"]) for i in all_invoices}
    client_opts  = ["All clients"] + [f"{cid} — {client_names[cid]}" for cid in client_ids]

    status_opts = ["All statuses"] + sorted({i["status"] for i in all_invoices})

    sel_client = f1.selectbox("Client", client_opts, key="f_client", label_visibility="collapsed")
    sel_status = f2.selectbox("Status", status_opts, key="f_status", label_visibility="collapsed")

    # Apply filters
    fil = all_invoices
    if sel_client != "All clients":
        cid_filter = sel_client.split(" — ")[0]
        fil = [i for i in fil if i["client_id"] == cid_filter]
    if sel_status != "All statuses":
        fil = [i for i in fil if i["status"] == sel_status]
    if search:
        fil = [i for i in fil if
               search in (i.get("client_name") or "").lower()
               or search in (i.get("employee_name") or "").lower()
               or search in i["invoice_number"].lower()]

    st.markdown(
        f"<p style='color:#475569;font-size:12px;margin:6px 0 4px'>"
        f"{len(fil)} invoice{'s' if len(fil)!=1 else ''} shown</p>",
        unsafe_allow_html=True,
    )

    # ── Invoice list ───────────────────────────────────────────
    if not fil:
        st.info("No invoices match the filter.")
    else:
        for inv_row in fil:
            num      = inv_row["invoice_number"]
            is_sel   = (st.session_state["preview_selected"] == num)
            sc, sbg  = _STATUS_COLOR.get(inv_row["status"], ("#64748B", "#1E293B"))
            emp      = inv_row.get("employee_name") or inv_row.get("employee_id", "—")
            cname    = inv_row.get("client_name") or inv_row.get("client_id", "—")
            cur      = inv_row.get("currency", "AED")
            amount   = inv_row.get("total_amount", 0)
            period   = inv_row.get("billing_period_start", "")[:7]
            bg       = "#1A2E47" if is_sel else "#1E293B"
            border_l = "border-left:3px solid #2563EB;" if is_sel else "border-left:3px solid transparent;"

            st.markdown(
                f"<div style='background:{bg};{border_l}border-radius:8px;"
                f"padding:10px 14px;margin:3px 0'>"
                f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                f"<div style='flex:1;min-width:0'>"
                f"<div style='display:flex;align-items:center;gap:8px'>"
                f"<span style='color:#93C5FD;font-size:11px;font-weight:700;white-space:nowrap'>{num}</span>"
                f"<span style='background:{sbg};color:{sc};border:1px solid {sc}44;"
                f"padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap'>"
                f"{inv_row['status']}</span></div>"
                f"<p style='color:#F1F5F9;font-size:13px;font-weight:600;margin:3px 0 1px;"
                f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{cname}</p>"
                f"<p style='color:#64748B;font-size:11px;margin:0'>{emp} · {period}</p>"
                f"</div>"
                f"<div style='text-align:right;margin-left:8px;flex-shrink:0'>"
                f"<p style='color:#4ADE80;font-size:14px;font-weight:700;margin:0'>"
                f"{cur} {amount:,.0f}</p>"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )
            if st.button("Open →", key=f"open_{num}",
                         use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state["preview_selected"] = num
                st.rerun()

# ══════════════════════════════════════════════════════════════
# RIGHT: Invoice Detail Panel
# ══════════════════════════════════════════════════════════════
with right:
    sel_num = st.session_state.get("preview_selected")
    if not sel_num:
        st.markdown(
            "<div style='background:#1E293B;border-radius:12px;padding:48px;text-align:center'>"
            "<p style='color:#475569;font-size:16px'>← Select an invoice to preview it here</p></div>",
            unsafe_allow_html=True,
        )
        st.stop()

    inv = DatabaseService.get_invoice(sel_num)
    if not inv:
        st.error(f"Invoice {sel_num} not found.")
        st.stop()

    # Reconstruct full data
    inv_json = {}
    if inv.get("invoice_json"):
        try:
            inv_json = json.loads(inv["invoice_json"])
        except Exception:
            pass

    billing = inv_json.get("billing", {}) or {
        "currency":         inv.get("currency", "AED"),
        "subtotal":         inv.get("total_amount", 0),
        "gst_amount":       inv.get("gst_amount", 0),
        "total_amount":     inv.get("total_amount", 0),
        "total_amount_inr": inv.get("total_amount_inr", 0),
        "line_items":       [],
        "billing_notes":    [],
    }
    full_inv = {**inv, **inv_json, "billing": billing}

    sc, sbg = _STATUS_COLOR.get(inv["status"], ("#64748B", "#1E293B"))
    cur = inv.get("currency", "AED")

    # ── Header ─────────────────────────────────────────────────
    h1, h2 = st.columns([3, 2])
    with h1:
        st.markdown(
            f"<p style='color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;margin:0'>INVOICE</p>"
            f"<h2 style='color:#F1F5F9;font-size:20px;margin:2px 0 6px'>{inv['invoice_number']}</h2>"
            f"<p style='color:#CBD5E1;font-size:14px;font-weight:600;margin:0'>"
            f"{inv.get('client_name') or inv.get('client_id','—')}</p>"
            f"<p style='color:#64748B;font-size:12px;margin:2px 0'>"
            f"{inv.get('employee_name','—')} · {inv.get('billing_period_start','')[:7]}</p>",
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            f"<div style='text-align:right'>"
            f"<span style='background:{sbg};color:{sc};border:1px solid {sc}44;"
            f"padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700'>"
            f"{inv['status']}</span>"
            f"<p style='color:#4ADE80;font-size:26px;font-weight:800;margin:8px 0 2px'>"
            f"{cur} {inv['total_amount']:,.2f}</p>"
            f"<p style='color:#475569;font-size:12px;margin:0'>₹{inv['total_amount_inr']:,.2f}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Download buttons (always visible) ──────────────────────
    pdf_path   = inv.get("pdf_path") or inv_json.get("pdf_path", "")
    excel_path = inv.get("excel_path") or inv_json.get("excel_path", "")

    da, db, dc = st.columns([3, 3, 2])

    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            da.download_button("📄 Download PDF", f.read(),
                file_name=Path(pdf_path).name, mime="application/pdf",
                use_container_width=True, type="primary", key=f"dl_pdf_{sel_num}")
    else:
        da.caption("PDF not available")

    if excel_path and Path(excel_path).exists():
        with open(excel_path, "rb") as f:
            db.download_button("📊 Download Excel", f.read(),
                file_name=Path(excel_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key=f"dl_xls_{sel_num}")
    else:
        db.caption("Excel not available")

    # Status update
    statuses = ["GENERATED", "DISPATCHED", "PAID", "FLAGGED"]
    cur_idx  = statuses.index(inv["status"]) if inv["status"] in statuses else 0
    new_st   = dc.selectbox("", statuses, index=cur_idx,
                             key=f"st_{sel_num}", label_visibility="collapsed")
    if new_st != inv["status"]:
        DatabaseService.update_invoice_status(sel_num, new_st)
        st.rerun()

    st.markdown("<hr style='border-color:#1E293B;margin:10px 0'>", unsafe_allow_html=True)

    # ── Tabs ───────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs(["📄  Preview", "📋  Details & Line Items", "🔎  Audit Log", "🎙️  Voice"])

    with t1:
        html = render_invoice_html(full_inv)
        st.components.v1.html(html, height=680, scrolling=True)

    with t2:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Billing Period**")
            st.markdown(f"From: {inv.get('billing_period_start','—')}")
            st.markdown(f"To: {inv.get('billing_period_end','—')}")
            st.markdown(f"Invoice Date: {inv.get('invoice_date','—')}")
            st.markdown(f"Due Date: {inv.get('due_date','—')}")
            st.markdown(f"Contract: `{inv.get('contract_id','—')}`")
        with col_b:
            st.markdown("**Financials**")
            sub = billing.get("subtotal", inv.get("total_amount", 0))
            gst = billing.get("gst_amount", inv.get("gst_amount", 0))
            tot = billing.get("total_amount", inv.get("total_amount", 0))
            st.markdown(f"Regular: {inv.get('regular_hours',0):.1f}h")
            st.markdown(f"Overtime: {inv.get('overtime_hours',0):.1f}h")
            st.markdown(f"Subtotal: {cur} {sub:,.2f}")
            st.markdown(f"GST: {cur} {gst:,.2f}")
            st.markdown(f"**Total: {cur} {tot:,.2f}**")

        items = billing.get("line_items", [])
        if items:
            st.markdown("**Line Items**")
            import pandas as pd
            df = pd.DataFrame(items)
            if "amount" in df.columns:
                df["amount"] = df["amount"].apply(lambda x: f"{cur} {float(x):,.2f}")
            if "rate" in df.columns:
                df["rate"] = df["rate"].apply(lambda x: f"{cur} {float(x):,.2f}")
            st.dataframe(df, use_container_width=True, hide_index=True)

        for note in billing.get("billing_notes", []):
            st.caption(f"• {note}")

    with t3:
        log = DatabaseService.get_audit_log(sel_num)
        if not log:
            st.info("No audit events for this invoice.")
        else:
            for entry in log:
                st.markdown(
                    f"`{entry.get('created_at','—')}` **{entry['event_type']}**"
                    + (f" — {entry['details']}" if entry.get("details") else "")
                )

    # ── Voice tab ───────────────────────────────────────────────
    with t4:
        if not config.SMALLEST_API_KEY:
            st.warning("Add `SMALLEST_API_KEY` to your `.env` file to enable voice features.")
        else:
            # ── TTS card ───────────────────────────────────────
            st.markdown(
                "<div style='background:#0F2027;border:1px solid #2563EB;border-radius:12px;"
                "padding:20px 22px;margin-bottom:16px'>"
                "<p style='color:#93C5FD;font-size:11px;font-weight:700;letter-spacing:1px;margin:0 0 4px'>"
                "INVOICE NARRATOR</p>"
                "<p style='color:#F1F5F9;font-size:15px;font-weight:600;margin:0 0 4px'>"
                "🔊 Read this invoice aloud</p>"
                "<p style='color:#64748B;font-size:12px;margin:0'>Smallest.ai generates a spoken "
                "summary using a natural voice.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

            narrative = (
                f"Invoice {inv.get('invoice_number')} for "
                f"{inv.get('client_name') or inv.get('client_id', 'the client')}. "
                f"Employee {inv.get('employee_name', 'unknown')} worked from "
                f"{inv.get('billing_period_start', '')} to {inv.get('billing_period_end', '')}. "
                f"Total amount due: {inv.get('currency', 'AED')} {inv['total_amount']:,.2f}, "
                f"equivalent to {inv['total_amount_inr']:,.2f} Indian Rupees. "
                f"Status: {inv.get('status', 'GENERATED')}."
            )
            st.caption(f"Will read: \"{narrative}\"")

            if st.button("🔊 Generate & Play", type="primary",
                         use_container_width=True, key=f"tts_{sel_num}"):
                with st.spinner("Generating speech via Smallest.ai…"):
                    try:
                        tts_resp = requests.post(
                            "https://api.smallest.ai/waves/v1/tts",
                            headers={
                                "Authorization": f"Bearer {config.SMALLEST_API_KEY}",
                                "Content-Type": "application/json",
                                "Accept": "audio/wav",
                            },
                            json={
                                "text": narrative,
                                "voice_id": "meher",
                                "model": "lightning_v3.1_pro",
                                "sample_rate": 24000,
                                "speed": 1.0,
                                "language": "en",
                                "output_format": "wav",
                            },
                            timeout=20,
                        )
                        if tts_resp.status_code == 200:
                            st.audio(tts_resp.content, format="audio/wav")
                            st.success("✅ Audio ready — press play above.")
                        else:
                            st.error(f"TTS error {tts_resp.status_code}: {tts_resp.text}")
                    except Exception as e:
                        st.error(f"TTS request failed: {e}")

            st.markdown("<hr style='border-color:#1E293B;margin:20px 0'>", unsafe_allow_html=True)

            # ── STT card ───────────────────────────────────────
            st.markdown(
                "<div style='background:#0F2027;border:1px solid #7C3AED;border-radius:12px;"
                "padding:20px 22px;margin-bottom:16px'>"
                "<p style='color:#C4B5FD;font-size:11px;font-weight:700;letter-spacing:1px;margin:0 0 4px'>"
                "VOICE QUERY</p>"
                "<p style='color:#F1F5F9;font-size:15px;font-weight:600;margin:0 0 4px'>"
                "🎤 Ask a question about this invoice</p>"
                "<p style='color:#64748B;font-size:12px;margin:0'>Record your question — "
                "Smallest.ai transcribes it, then Gemini answers using the invoice data.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

            st.markdown("<p style='color:#94A3B8;font-size:13px;margin:0 0 8px'>"
                        "Click the button below, speak your question, then click Stop.</p>",
                        unsafe_allow_html=True)

            voice_query = mic_recorder(
                start_prompt="🎤  Click to Start Recording",
                stop_prompt="⏹  Click to Stop",
                just_once=True,
                use_container_width=True,
                format="webm",
                key=f"stt_{sel_num}",
            )

            if voice_query and voice_query.get("bytes"):
                audio_bytes = voice_query["bytes"]
                st.markdown(
                    f"<p style='color:#475569;font-size:12px'>Recorded {len(audio_bytes):,} bytes</p>",
                    unsafe_allow_html=True,
                )

                if len(audio_bytes) < 1000:
                    st.warning("Recording too short — please speak clearly for at least 1 second.")
                else:
                    with st.spinner("Transcribing with Smallest.ai…"):
                        try:
                            stt_resp = requests.post(
                                "https://api.smallest.ai/waves/v1/pulse/get_text?language=en",
                                headers={
                                    "Authorization": f"Bearer {config.SMALLEST_API_KEY}",
                                    "Content-Type": "application/octet-stream",
                                },
                                data=audio_bytes,
                                timeout=15,
                            )
                            if stt_resp.status_code == 200:
                                transcribed = stt_resp.json().get("transcription", "").strip()
                            else:
                                transcribed = ""
                                st.error(f"Transcription error {stt_resp.status_code}: {stt_resp.text}")
                        except Exception as e:
                            transcribed = ""
                            st.error(f"Request failed: {e}")

                    if transcribed:
                        st.markdown(
                            f"<div style='background:#1E293B;border-left:3px solid #7C3AED;"
                            f"border-radius:6px;padding:10px 14px;margin:8px 0'>"
                            f"<p style='color:#C4B5FD;font-size:11px;font-weight:700;margin:0 0 2px'>"
                            f"YOU ASKED</p>"
                            f"<p style='color:#F1F5F9;font-size:14px;margin:0'>&ldquo;{transcribed}&rdquo;</p>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        with st.spinner("Gemini is answering…"):
                            try:
                                from services.gemini_service import _call_with_retry
                                answer = _call_with_retry(
                                    model=config.GEMINI_MODEL,
                                    contents=(
                                        f"You are a helpful assistant for invoice platform Sentinel.\n"
                                        f"Invoice data:\n{json.dumps(inv, default=str)}\n\n"
                                        f"Question: {transcribed}\n\n"
                                        f"Answer in 2-3 sentences, clearly and directly."
                                    ),
                                )
                                st.markdown(
                                    f"<div style='background:#0B2818;border-left:3px solid #16A34A;"
                                    f"border-radius:6px;padding:12px 14px;margin:8px 0'>"
                                    f"<p style='color:#4ADE80;font-size:11px;font-weight:700;margin:0 0 4px'>"
                                    f"SENTINEL ANSWER</p>"
                                    f"<p style='color:#E2E8F0;font-size:14px;margin:0'>{answer.text}</p>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                            except Exception as e:
                                st.error(f"Could not generate answer: {e}")
                    elif len(audio_bytes) >= 1000:
                        st.warning("No speech detected in the recording. Please try again and speak clearly.")
