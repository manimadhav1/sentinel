import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.database_service import DatabaseService
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Dashboard — Sentinel", page_icon="📊", layout="wide")

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


st.markdown("<h2 style='color:#F1F5F9'>📊 Dashboard</h2>", unsafe_allow_html=True)
st.markdown("<p style='color:#94A3B8'>Real-time overview of invoice processing activity.</p>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

stats    = DatabaseService.get_stats()
invoices = DatabaseService.list_invoices(limit=200)

# ── KPI strip ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Invoices",   stats["total_invoices"])
k2.metric("Total Billed",     f"₹{stats['total_billed_inr']:,.0f}")
k3.metric("Pending Review",   stats["pending_review"],
          delta="needs attention" if stats["pending_review"] > 0 else None,
          delta_color="inverse")
k4.metric("Auto-Processed",
          f"{stats['by_status'].get('GENERATED', 0) + stats['by_status'].get('PAID', 0)}")
k5.metric("Paid Invoices",    stats["by_status"].get("PAID", 0))

st.markdown("---")

if not invoices:
    st.info("No invoices yet. Upload a timesheet to see data here.")
    st.stop()

df = pd.DataFrame(invoices)

# ── Charts row 1 ──────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

# Status donut
with ch1:
    st.markdown("#### Invoice Status")
    status_counts = df["status"].value_counts()
    colors = {
        "GENERATED":  "#2563EB",
        "DISPATCHED": "#7C3AED",
        "PAID":       "#16A34A",
        "FLAGGED":    "#DC2626",
    }
    fig = go.Figure(go.Pie(
        labels=status_counts.index.tolist(),
        values=status_counts.values.tolist(),
        hole=0.55,
        marker_colors=[colors.get(s, "#94A3B8") for s in status_counts.index],
        textinfo="label+percent",
    ))
    fig.update_layout(
        margin=dict(t=20, b=20, l=20, r=20),
        height=280,
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# Top clients bar
with ch2:
    st.markdown("#### Top Clients by Billed INR")
    top = (
        df.groupby("client_id")["total_amount_inr"]
        .sum()
        .nlargest(8)
        .reset_index()
    )
    fig2 = px.bar(
        top, x="total_amount_inr", y="client_id",
        orientation="h",
        color="total_amount_inr",
        color_continuous_scale=["#DBEAFE", "#1D4ED8"],
        labels={"total_amount_inr": "Total (INR)", "client_id": "Client"},
    )
    fig2.update_layout(
        margin=dict(t=20, b=20, l=20, r=20),
        height=280,
        showlegend=False,
        coloraxis_showscale=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickfont=dict(size=11)),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Charts row 2 ──────────────────────────────────────────────────────────────
ch3, ch4 = st.columns(2)

# Billing over time
with ch3:
    st.markdown("#### Billing Over Time")
    if "created_at" in df.columns:
        ts = df.copy()
        ts["date"] = pd.to_datetime(ts["created_at"], errors="coerce").dt.date
        daily = ts.groupby("date")["total_amount_inr"].sum().reset_index()
        fig3 = px.area(
            daily, x="date", y="total_amount_inr",
            labels={"date": "Date", "total_amount_inr": "INR"},
            color_discrete_sequence=["#2563EB"],
        )
        fig3.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.caption("No date data available yet.")

# Per-employee breakdown
with ch4:
    st.markdown("#### Top Employees by Billed INR")
    emp_top = (
        df.groupby("employee_id")["total_amount_inr"]
        .sum()
        .nlargest(8)
        .reset_index()
    )
    fig4 = px.bar(
        emp_top, x="employee_id", y="total_amount_inr",
        color="total_amount_inr",
        color_continuous_scale=["#D1FAE5", "#065F46"],
        labels={"employee_id": "Employee", "total_amount_inr": "Total (INR)"},
    )
    fig4.update_layout(
        margin=dict(t=20, b=20, l=20, r=20),
        height=260,
        showlegend=False,
        coloraxis_showscale=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickangle=-30, tickfont=dict(size=10)),
    )
    st.plotly_chart(fig4, use_container_width=True)

# ── Invoice history table ──────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### Invoice History")

cols_show = [c for c in [
    "invoice_number", "employee_id", "client_id",
    "billing_period_start", "billing_period_end",
    "total_amount", "currency", "total_amount_inr", "status", "created_at"
] if c in df.columns]

display_df = df[cols_show].copy()
if "total_amount_inr" in display_df:
    display_df["total_amount_inr"] = display_df["total_amount_inr"].map(lambda x: f"₹{x:,.2f}")
if "total_amount" in display_df:
    display_df["total_amount"] = display_df["total_amount"].map(lambda x: f"{x:,.2f}")

st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── AI Assistant ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### 💬 Ask Sentinel")
st.caption("Get instant answers about your invoice data. (Powered by deterministic aggregations — no LLM call needed for stats.)")

query = st.text_input("Ask a question", placeholder="e.g. How many invoices are paid? What is total billed this month?")

if query:
    q = query.lower()
    if "paid" in q and ("how many" in q or "count" in q):
        n = stats["by_status"].get("PAID", 0)
        st.success(f"**{n}** invoice(s) have status PAID.")
    elif "total" in q and ("billed" in q or "amount" in q or "inr" in q):
        st.success(f"Total billed across all invoices: **₹{stats['total_billed_inr']:,.2f}**")
    elif "pending" in q or "review" in q:
        st.success(f"**{stats['pending_review']}** item(s) are pending human review.")
    elif "client" in q and ("top" in q or "most" in q or "highest" in q):
        top_c = stats.get("top_clients", [])
        if top_c:
            lines = "\n".join(f"- **{c['client_id']}**: ₹{c['total']:,.2f}" for c in top_c[:5])
            st.success(f"**Top Clients by Billed INR:**\n{lines}")
        else:
            st.info("Not enough data yet.")
    elif "invoices" in q and ("how many" in q or "total" in q or "count" in q):
        st.success(f"**{stats['total_invoices']}** total invoice(s) generated.")
    elif "generated" in q or "dispatched" in q or "flagged" in q:
        for status, count in stats["by_status"].items():
            if status.lower() in q:
                st.success(f"**{count}** invoice(s) with status **{status}**.")
                break
    else:
        # fallback: summarize all stats
        st.info(
            f"Here's a summary of your data:\n"
            f"- **{stats['total_invoices']}** total invoices\n"
            f"- **₹{stats['total_billed_inr']:,.2f}** total billed\n"
            f"- **{stats['pending_review']}** pending review\n"
            f"- Status breakdown: {', '.join(f'{k}: {v}' for k, v in stats['by_status'].items())}"
        )
