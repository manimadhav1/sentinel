import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService

st.set_page_config(page_title="Review Queue — Sentinel", page_icon="🔍", layout="wide")

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

st.markdown("<h2 style='color:#F1F5F9'>🔍 Human Review Queue</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#94A3B8'>Documents that need manual verification before invoicing.</p>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

# ── Queue stats + clear button ────────────────────────────────────────────────
pending  = DatabaseService.get_review_queue("PENDING")
resolved = DatabaseService.get_review_queue("RESOLVED")

c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
c1.metric("Pending Review",  len(pending))
c2.metric("Resolved",        len(resolved))
c3.metric("Total",           len(pending) + len(resolved))

with c4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ Clear All", type="secondary", use_container_width=True):
        import sqlite3, sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import config
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.execute("DELETE FROM review_queue")
        conn.commit()
        conn.close()
        st.success("Queue cleared.")
        st.rerun()

st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

if not pending:
    st.success("✅ No items pending review. All documents processed automatically.")
    if resolved:
        st.markdown("### Recently Resolved")
        for item in resolved[-5:]:
            emp = item.get("employee_name") or item.get("employee_id", "—")
            cli = item.get("client_name")   or item.get("client_id",   "—")
            st.markdown(
                f"✓ `{item['id']}` — Employee **{emp}** · "
                f"Client **{cli}** · Resolved: {item.get('resolved_at','—')}"
            )
    st.stop()

st.markdown(f"### {len(pending)} Item(s) Awaiting Review")

import json as _json

for item in pending:
    conf  = item.get("confidence", 0)
    stage = item.get("stage", "unknown")

    # Parse errors / ambiguous_fields from JSON strings if needed
    raw_errors = item.get("errors", "[]")
    errors = _json.loads(raw_errors) if isinstance(raw_errors, str) else (raw_errors or [])

    raw_af = item.get("ambiguous_fields", "[]")
    amb    = _json.loads(raw_af) if isinstance(raw_af, str) else (raw_af or [])

    emp_label = item.get("employee_name") or "Unknown Employee"
    cli_label = item.get("client_name")   or "Unknown Client"
    src_file  = item.get("source_file", "")
    fname     = src_file.split("/")[-1] if src_file else "—"

    # Human-readable reason
    if errors:
        top_error = errors[0]
        if "Duplicate" in top_error:
            reason_human = "⚠️ Duplicate — invoice already generated for this period"
            badge = "🔴 DUPLICATE"
        elif "mandatory" in top_error.lower() or "Missing" in top_error:
            reason_human = "⚠️ Missing required fields — document incomplete"
            badge = "🟡 INCOMPLETE"
        elif "outside contract" in top_error.lower() or "expired" in top_error.lower():
            reason_human = "⚠️ Contract issue — billing period outside contract dates"
            badge = "🟠 CONTRACT"
        elif "not found in master" in top_error.lower():
            reason_human = "⚠️ Unknown employee or client — not in master data"
            badge = "🔴 UNKNOWN ID"
        else:
            reason_human = f"⚠️ Validation failed"
            badge = "🟡 REVIEW"
    else:
        reason_human = f"⚠️ Low confidence ({conf:.0%}) — manual check required"
        badge = "🟡 LOW CONF"

    with st.expander(
        f"{badge}  Queue #{item['id']}  |  {fname}  |  Confidence: {conf:.0%}",
        expanded=True,
    ):
        col_info, col_action = st.columns([2, 1])

        with col_info:
            # Summary card
            st.markdown(
                f"<div style='background:#1E293B;border-radius:8px;padding:14px;margin-bottom:12px'>"
                f"<p style='color:#94A3B8;font-size:12px;margin:0'>WHAT HAPPENED</p>"
                f"<p style='color:#F1F5F9;font-size:15px;font-weight:600;margin:4px 0'>{reason_human}</p>"
                f"<p style='color:#64748B;font-size:12px;margin:0'>Stage: <b>{stage}</b> &nbsp;|&nbsp; "
                f"File: <b>{fname}</b> &nbsp;|&nbsp; Confidence: <b>{conf:.0%}</b></p>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Actual errors
            if errors:
                st.markdown("**What needs fixing:**")
                for e in errors:
                    st.error(e)

            # Ambiguous fields (only show if non-empty and meaningful)
            real_amb = [a for a in amb if isinstance(a, dict) and a.get("field_name")]
            if real_amb:
                st.markdown("**Uncertain fields extracted from document:**")
                for af in real_amb:
                    st.warning(
                        f"**{af.get('field_name')}** — {af.get('reason','')}\n\n"
                        f"Extracted: `{af.get('extracted_value','—')}` → "
                        f"Suggested: `{af.get('suggested_value','—')}`"
                    )

            st.caption(f"Created: {item.get('created_at','—')}")

        with col_action:
            st.markdown("**Action**")

            note = st.text_area(
                "Resolution note",
                key=f"note_{item['id']}",
                placeholder="e.g. Confirmed employee ID correct",
                height=80,
            )

            if st.button("✅ Approve", key=f"approve_{item['id']}", use_container_width=True, type="primary"):
                DatabaseService.resolve_review_item(
                    item["id"], "APPROVED",
                    resolver="reviewer@sentinel.ai",
                    notes=note or "Manually approved",
                )
                st.success("Approved — page will refresh.")
                st.rerun()

            if st.button("❌ Reject", key=f"reject_{item['id']}", use_container_width=True):
                DatabaseService.resolve_review_item(
                    item["id"], "REJECTED",
                    resolver="reviewer@sentinel.ai",
                    notes=note or "Manually rejected",
                )
                st.error("Rejected — page will refresh.")
                st.rerun()

        st.markdown(f"*Created: {item.get('created_at', '—')}*")

st.markdown("---")
if st.button("🔄 Refresh Queue"):
    st.rerun()
