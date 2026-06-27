import streamlit as st

st.set_page_config(
    page_title="Sentinel — Invoice Automation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS: hide default page nav, style sidebar & cards ──────────────────
st.markdown("""
<style>
/* Hide Streamlit's auto-generated page list in sidebar */
[data-testid="stSidebarNav"] { display: none !important; }

/* Sidebar background */
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }

/* Sidebar text */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption { color: #94A3B8 !important; }

/* Sidebar page_link buttons */
[data-testid="stSidebar"] a {
    color: #CBD5E1 !important;
    text-decoration: none;
    display: block;
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px 0;
    font-size: 14px;
}
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }

/* Feature cards — dark theme */
.feature-card {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 24px 16px;
    text-align: center;
    height: 150px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
.feature-card .icon  { font-size: 32px; line-height: 1; }
.feature-card .title { color: #F1F5F9; font-weight: 700; font-size: 15px; }
.feature-card .desc  { color: #94A3B8; font-size: 12px; }

/* Status colours */
.status-valid   { color: #4ADE80; font-weight: 700; }
.status-invalid { color: #F87171; font-weight: 700; }
.status-warn    { color: #FCD34D; font-weight: 700; }
.status-review  { color: #C084FC; font-weight: 700; }

/* Expander border */
div[data-testid="stExpander"] { border: 1px solid #334155; border-radius: 8px; }

/* Stage progress rows */
.stage-row {
    padding: 10px 14px;
    border-radius: 8px;
    border-left: 4px solid #334155;
    background: #1E293B;
    margin: 6px 0;
    font-size: 14px;
    color: #E2E8F0;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='padding:16px 8px 8px;'>"
        "<span style='font-size:22px;font-weight:800;color:#F1F5F9'>⚡ Sentinel</span><br>"
        "<span style='font-size:12px;color:#64748B'>Touchless Invoice Automation</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<hr style='border-color:#1E293B;margin:8px 0'>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:11px;color:#475569;padding:0 8px;margin:4px 0'>NAVIGATION</p>",
                unsafe_allow_html=True)
    st.page_link("app.py",                       label="🏠  Home")
    st.page_link("pages/01_upload.py",            label="📤  Upload & Process")
    st.page_link("pages/02_review_queue.py",      label="🔍  Review Queue")
    st.page_link("pages/03_invoice_preview.py",   label="📄  Invoice Preview")
    st.page_link("pages/04_dashboard.py",         label="📊  Dashboard")
    st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown(
        "<div style='padding:0 8px'>"
        "<p style='font-size:11px;color:#475569;margin:2px 0'>AI Model: Gemini 2.5 Flash</p>"
        "<p style='font-size:11px;color:#475569;margin:2px 0'>Engine: Pure Python</p>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Home page ──────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#F1F5F9;margin-bottom:4px'>⚡ Sentinel</h1>"
    "<p style='color:#94A3B8;font-size:18px;margin-top:0'>Touchless Invoice Automation Platform</p>",
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
cards = [
    ("📤", "Upload", "PDF · Excel · Image · Handwritten"),
    ("🤖", "AI Extract", "Gemini reads any document — once"),
    ("⚙️",  "Process", "14 validation rules · Pure Python"),
    ("📄", "Invoice", "PDF Invoice · SAP-compatible Excel"),
]
for col, (icon, title, desc) in zip([col1, col2, col3, col4], cards):
    col.markdown(
        f"<div class='feature-card'>"
        f"<div class='icon'>{icon}</div>"
        f"<div class='title'>{title}</div>"
        f"<div class='desc'>{desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

st.markdown(
    "<p style='color:#CBD5E1'><b>Get started:</b> Click <b>Upload & Process</b> in the sidebar.</p>"
    "<blockquote style='border-left:3px solid #2563EB;padding-left:12px;color:#64748B;font-style:italic'>"
    "AI understands documents. Our software understands the business.</blockquote>",
    unsafe_allow_html=True,
)

# ── Stats strip (if DB has data) ───────────────────────────────────────────────
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from services.database_service import DatabaseService
    stats = DatabaseService.get_stats()
    if stats["total_invoices"] > 0:
        st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)
        st.markdown("<p style='color:#64748B;font-size:12px'>LIVE STATS</p>", unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Invoices",  stats["total_invoices"])
        s2.metric("Total Billed",    f"₹{stats['total_billed_inr']:,.0f}")
        s3.metric("Pending Review",  stats["pending_review"])
        s4.metric("Paid",            stats["by_status"].get("PAID", 0))
except Exception:
    pass
