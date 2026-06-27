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

# ── Queue stats ────────────────────────────────────────────────────────────────
pending  = DatabaseService.get_review_queue("PENDING")
resolved = DatabaseService.get_review_queue("RESOLVED")

c1, c2, c3 = st.columns(3)
c1.metric("Pending Review",  len(pending))
c2.metric("Resolved Today",  len(resolved))
c3.metric("Total Processed", len(pending) + len(resolved))

st.markdown("---")

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

for item in pending:
    conf   = item.get("confidence", 0)
    reason = item.get("reason", "")
    stage  = item.get("stage", "unknown")

    color = "#DC2626" if conf < 0.60 else "#D97706"
    badge = "🔴 HIGH PRIORITY" if conf < 0.60 else "🟡 NEEDS REVIEW"

    emp_label = item.get("employee_name") or item.get("employee_id", "—")
    cli_label = item.get("client_name")   or item.get("client_id",   "—")

    with st.expander(
        f"{badge}  Queue #{item['id']} — {emp_label} / {cli_label}  "
        f"| Conf: {conf:.0%} | Stage: {stage}",
        expanded=conf < 0.60,
    ):
        col_info, col_action = st.columns([2, 1])

        with col_info:
            st.markdown(f"**Confidence:** `{conf:.2f}` ({conf:.0%})")
            st.markdown(f"**Failed at stage:** `{stage}`")
            st.markdown(f"**Reason:**\n> {reason}")

            if item.get("ambiguous_fields"):
                st.markdown("**Ambiguous Fields:**")
                for af in item["ambiguous_fields"]:
                    field = af if isinstance(af, str) else af.get("field_name", af.get("field", "?"))
                    reason_af = "" if isinstance(af, str) else af.get("reason", "")
                    extracted = "" if isinstance(af, str) else af.get("extracted_value", "")
                    suggested = "" if isinstance(af, str) else af.get("suggested_value", "")
                    st.warning(
                        f"**{field}** — {reason_af}  \n"
                        f"Extracted: `{extracted}` → Suggested: `{suggested}`"
                    )

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
