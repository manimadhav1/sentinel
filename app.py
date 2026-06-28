import streamlit as st

st.set_page_config(
    page_title="Sentinel — Invoice Automation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }

/* Clickable feature cards */
div[data-testid="column"] .nav-card {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 28px 16px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    height: 160px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
}
div[data-testid="column"] .nav-card:hover {
    border-color: #2563EB;
    background: #1e3a5f;
    transform: translateY(-2px);
}
.nav-card .c-icon  { font-size: 36px; line-height: 1; }
.nav-card .c-title { color: #F1F5F9; font-weight: 700; font-size: 15px; }
.nav-card .c-desc  { color: #94A3B8; font-size: 12px; }

/* Hide default button styling for card buttons */
div[data-testid="column"] .stButton > button {
    background: #1E293B !important;
    border: 1px solid #334155 !important;
    border-radius: 12px !important;
    padding: 28px 16px !important;
    width: 100% !important;
    height: 160px !important;
    color: #F1F5F9 !important;
    font-size: 14px !important;
    transition: all 0.2s !important;
}
div[data-testid="column"] .stButton > button:hover {
    border-color: #2563EB !important;
    background: #1e3a5f !important;
    transform: translateY(-2px) !important;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<div style='padding:16px 8px 8px'><span style='font-size:22px;font-weight:800;color:#F1F5F9'>⚡ Sentinel</span><br><span style='font-size:11px;color:#475569'>Touchless Invoice Automation</span></div>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#1E293B;margin:8px 0'>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:11px;color:#475569;padding:0 8px;margin:4px 0'>NAVIGATION</p>", unsafe_allow_html=True)
    st.page_link("app.py",                       label="🏠  Home")
    st.page_link("pages/01_upload.py",            label="📤  Upload & Process")
    st.page_link("pages/02_review_queue.py",      label="🔍  Review Queue")
    st.page_link("pages/03_invoice_preview.py",   label="📄  Invoice Preview")
    st.page_link("pages/04_dashboard.py",         label="📊  Dashboard")
    st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("<div style='padding:0 8px'><p style='font-size:11px;color:#475569;margin:2px 0'>AI: Gemini 2.5 Flash</p><p style='font-size:11px;color:#475569;margin:2px 0'>Engine: Pure Python</p></div>", unsafe_allow_html=True)

# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#F1F5F9;margin-bottom:4px'>⚡ Sentinel</h1>"
    "<p style='color:#94A3B8;font-size:18px;margin-top:0'>Touchless Invoice Automation Platform</p>",
    unsafe_allow_html=True,
)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

# ── Clickable feature cards ────────────────────────────────────────────────────
cards = [
    ("📤", "Upload & Process", "PDF · Excel · CSV · Image · Handwritten", "pages/01_upload.py"),
    ("🤖", "AI Extract",       "Gemini reads any document — once",         "pages/01_upload.py"),
    ("⚙️",  "Validate",         "14 business rules · Pure Python",          "pages/02_review_queue.py"),
    ("📄", "Invoice",          "PDF Invoice · SAP-compatible Excel",        "pages/03_invoice_preview.py"),
]

col1, col2, col3, col4 = st.columns(4)
for col, (icon, title, desc, page) in zip([col1, col2, col3, col4], cards):
    with col:
        st.markdown(
            f"<div class='nav-card'>"
            f"<div class='c-icon'>{icon}</div>"
            f"<div class='c-title'>{title}</div>"
            f"<div class='c-desc'>{desc}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # Invisible full-width link overlay using page_link
        st.page_link(page, label=f"Go to {title}", use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#CBD5E1'><b>Get started:</b> Click any card or use the sidebar to navigate.</p>"
    "<blockquote style='border-left:3px solid #2563EB;padding-left:12px;color:#64748B;font-style:italic'>"
    "AI understands documents. Our software understands the business.</blockquote>",
    unsafe_allow_html=True,
)

# ── Live stats ─────────────────────────────────────────────────────────────────
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from services.database_service import DatabaseService
    stats = DatabaseService.get_stats()
    if stats["total_invoices"] > 0:
        st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;font-size:11px;letter-spacing:1px'>LIVE STATS</p>", unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Invoices",  stats["total_invoices"])
        s2.metric("Total Billed",    f"₹{stats['total_billed_inr']:,.0f}")
        s3.metric("Pending Review",  stats["pending_review"])
        s4.metric("Paid",            stats["by_status"].get("PAID", 0))
except Exception:
    pass
