import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import SentinelPipeline
from utils.file_utils import save_upload
from utils.invoice_html import render_invoice_html

st.set_page_config(page_title="Upload — Sentinel", page_icon="📤", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] { background: #0F172A !important; }
[data-testid="stSidebar"] > div { background: #0F172A !important; }
[data-testid="stSidebar"] a { color: #CBD5E1 !important; text-decoration: none;
    display: block; padding: 8px 12px; border-radius: 6px; margin: 2px 0; font-size: 14px; }
[data-testid="stSidebar"] a:hover { background: #1E3A5F !important; color: #fff !important; }
.stage-card { padding: 10px 14px; border-radius: 8px; border-left: 4px solid;
              background: #1E293B; margin: 4px 0; color: #E2E8F0; }
div[data-testid="stTabs"] button { color: #94A3B8 !important; }
div[data-testid="stTabs"] button[aria-selected="true"] {
    color: #F1F5F9 !important; border-bottom-color: #2563EB !important; }
.reason-card { background: #1A1A2E; border: 1px solid #334155;
               border-radius: 10px; padding: 16px; margin: 8px 0; }
.reason-card h4 { color: #F1F5F9; margin: 0 0 4px; font-size: 14px; }
.reason-card p  { color: #94A3B8; font-size: 12px; margin: 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
CONF_FIELD_INFO = {
    "employee": {
        "label": "Employee Identity",
        "fields": "Name, Employee ID, Designation",
        "high": "Employee identity clearly extracted.",
        "mid":  "Employee identity mostly extracted — some fields inferred.",
        "low":  "Employee identity unclear. AI could not reliably read name or ID.",
    },
    "client": {
        "label": "Client Information",
        "fields": "Company Name, Client ID, Billing Address",
        "high": "Client details clearly identified.",
        "mid":  "Client partially identified — some details filled from master records.",
        "low":  "Client unclear. Company name or ID could not be reliably extracted.",
    },
    "contract": {
        "label": "Contract Terms",
        "fields": "Billing Rate, Contract ID, Billing Type, Dates",
        "high": "Contract terms clearly found in the document.",
        "mid":  "Contract terms partially found — remaining fields loaded from master data.",
        "low":  "Contract terms unclear. Billing rate or contract type missing.",
    },
    "timesheet": {
        "label": "Timesheet Data",
        "fields": "Dates, Hours Worked, Overtime Hours",
        "high": "Timesheet entries clearly extracted.",
        "mid":  "Timesheet partially clear — some entries synthesised from aggregate totals.",
        "low":  "Timesheet unclear. Daily entries or totals could not be reliably read.",
    },
}

RULE_LABELS = {
    "MANDATORY_FIELDS":           "Required Fields",
    "EMPLOYEE_EXISTS":            "Employee Verified",
    "CLIENT_EXISTS":              "Client Verified",
    "CONTRACT_ACTIVE":            "Contract Active",
    "CONTRACT_MASTER_MATCH":      "Contract Terms Match",
    "BILLING_PERIOD_IN_CONTRACT": "Billing Period Valid",
    "HOURS_VALIDITY":             "Hours Valid",
    "GST_CONSISTENCY":            "GST Correct",
    "CURRENCY_MATCH":             "Currency Match",
    "BILLING_RATE_INTEGRITY":     "Billing Rate Correct",
    "OVERTIME_COMPLIANCE":        "Overtime Compliant",
    "DUPLICATE_INVOICE":          "No Duplicate",
    "TIMESHEET_DATE_RANGE":       "Dates In Range",
    "LINKAGE_INTEGRITY":          "IDs Consistent",
}

RULE_FIX_GUIDE = {
    "MANDATORY_FIELDS":           ("Required data missing", "Ensure employee ID, client ID, billing rate, and timesheet hours are present in the document."),
    "EMPLOYEE_EXISTS":            ("Employee not in master records", "Confirm the correct employee ID with HR. The employee must be registered in the system before invoicing."),
    "CLIENT_EXISTS":              ("Client not in master records", "Confirm the client code with your account manager. New clients must be added to master data first."),
    "CONTRACT_ACTIVE":            ("Contract not active", "Confirm contract start/end dates. Renew or extend the contract before billing."),
    "CONTRACT_MASTER_MATCH":      ("Contract terms differ", "Billing rate or terms don't match the signed contract. Verify with the contract administrator."),
    "BILLING_PERIOD_IN_CONTRACT": ("Period outside contract dates", "Check pay period or contract dates — billing period must fall within the contract validity window."),
    "HOURS_VALIDITY":             ("Timesheet hours invalid", "One or more entries have 0, negative, or >24 hours. Correct the timesheet and re-upload."),
    "GST_CONSISTENCY":            ("GST mismatch", "GST amount doesn't match the rate in the contract. Recalculate manually before re-uploading."),
    "CURRENCY_MATCH":             ("Currency mismatch", "Billing currency doesn't match the contract. Confirm which currency applies."),
    "BILLING_RATE_INTEGRITY":     ("Billing rate mismatch", "Effective rate calculated from the invoice doesn't match the contract rate. Check for calculation errors."),
    "OVERTIME_COMPLIANCE":        ("Overtime not permitted", "Overtime hours claimed but contract does not allow overtime billing."),
    "DUPLICATE_INVOICE":          ("Duplicate invoice", "An invoice already exists for this employee/period. Check the Invoice Preview page."),
    "TIMESHEET_DATE_RANGE":       ("Dates outside billing period", "Some timesheet entries have dates outside the declared billing period."),
    "LINKAGE_INTEGRITY":          ("ID inconsistency", "Employee ID, client ID, and contract ID don't all match each other."),
}

STATUS_COLOR = {
    "done": "#16A34A", "failed": "#DC2626", "running": "#2563EB",
    "skipped": "#334155", "warn": "#D97706", "pending": "#1E293B",
}
STATUS_ICON = {
    "pending": "⏳", "running": "🔄", "done": "✅",
    "failed": "❌", "skipped": "⏭️", "warn": "⚠️",
}
PIPELINE_STAGES = {
    "document":   ("📄", "Document Engine",   "Reading & extracting with Gemini AI"),
    "processing": ("⚙️",  "Processing Engine", "Calculating billing & overtime"),
    "validation": ("✅", "Validation Engine", "Checking 14 business rules"),
    "invoice":    ("📋", "Invoice Engine",    "Generating PDF & ERP Excel"),
    "database":   ("💾", "Database",          "Saving to audit record"),
}


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────
def _conf_band(score):
    if score >= 0.90:
        return "high", "#16A34A"
    if score >= 0.75:
        return "mid", "#D97706"
    return "low", "#DC2626"


def _serialise(r):
    doc_  = r.document
    pd_   = r.processing
    vd_   = r.validation
    inv_  = r.invoice
    return {
        "_processed":        True,
        "success":           r.success,
        "is_duplicate":      r.is_duplicate,
        "routed_to_review":  r.routed_to_review,
        "review_queue_id":   r.review_queue_id,
        "invoice_number":    r.invoice_number,
        "pdf_path":          r.pdf_path,
        "excel_path":        r.excel_path,
        "doc_confidence":    doc_.confidence,
        "confidence_scores": doc_.metadata.get("confidence_scores", {}),
        "ambiguous_fields":  [a.model_dump() for a in doc_.ambiguous_fields],
        "extraction_notes":  doc_.metadata.get("extraction_notes", ""),
        "doc_errors":        doc_.errors,
        "doc_warnings":      doc_.warnings,
        "invoice_data":      inv_.data if inv_ else {},
        "billing_data":      pd_.data if pd_ else {},
        "validation_report": (vd_.data.get("report", []) if vd_ and vd_.data else []),
        "val_errors":        (vd_.errors if vd_ else []),
        "val_warnings":      (vd_.warnings if vd_ else []),
    }


# ─────────────────────────────────────────────────────────────
# RENDER HELPERS — all defined before any calls
# ─────────────────────────────────────────────────────────────
def _render_confidence_breakdown(s: dict):
    scores   = s.get("confidence_scores", {})
    doc_conf = s.get("doc_confidence", 0)
    notes    = s.get("extraction_notes", "")

    _, overall_color = _conf_band(doc_conf)
    above = doc_conf >= 0.75

    st.markdown(
        f"<div style='background:#1E293B;border-radius:10px;padding:16px 20px;margin-bottom:16px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div><p style='color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;margin:0'>OVERALL AI CONFIDENCE</p>"
        f"<p style='font-size:28px;font-weight:800;color:{overall_color};margin:4px 0 0'>{doc_conf:.0%}</p></div>"
        f"<div style='text-align:right'>"
        f"<p style='color:#94A3B8;font-size:12px;margin:0'>75% = auto-proceed threshold</p>"
        f"<p style='color:{'#4ADE80' if above else '#F87171'};font-size:13px;font-weight:600;margin:4px 0 0'>"
        f"{'✅ Above threshold' if above else '❌ Below threshold'}</p>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    for field, info in CONF_FIELD_INFO.items():
        if field not in scores:
            continue
        try:
            score = float(scores[field])
        except Exception:
            continue
        band, color = _conf_band(score)
        pct = int(score * 100)
        st.markdown(
            f"<div style='background:#1E293B;border-radius:8px;padding:14px 16px;margin:8px 0;border-left:3px solid {color}'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'>"
            f"<div><span style='color:#F1F5F9;font-weight:600;font-size:14px'>{info['label']}</span>"
            f"<span style='color:#475569;font-size:11px;margin-left:8px'>({info['fields']})</span></div>"
            f"<span style='color:{color};font-weight:700;font-size:16px'>{pct}%</span></div>"
            f"<div style='background:#334155;border-radius:4px;height:6px;margin-bottom:8px'>"
            f"<div style='background:{color};border-radius:4px;height:6px;width:{pct}%'></div></div>"
            f"<p style='color:#94A3B8;font-size:12px;margin:0'>{info[band]}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    ambiguous = [a for a in s.get("ambiguous_fields", []) if isinstance(a, dict) and a.get("field_name")]
    if ambiguous:
        st.markdown("<p style='color:#94A3B8;font-size:12px;font-weight:600;margin:12px 0 6px'>"
                    "FIELDS THE AI WAS UNCERTAIN ABOUT</p>", unsafe_allow_html=True)
        for af in ambiguous:
            st.warning(
                f"**{af.get('field_name')}** — {af.get('reason','')}\n\n"
                f"Extracted: `{af.get('extracted_value','—')}` → Suggested: `{af.get('suggested_value','—')}`"
            )

    if notes:
        st.caption(f"🤖 AI observation: {notes}")


def _render_validation_report(s: dict):
    report = s.get("validation_report", [])
    if not report:
        st.info("Validation report not available.")
        return

    passed  = sum(1 for c in report if c["passed"])
    total   = len(report)
    pct     = int(passed / total * 100) if total else 0
    bar_col = "#16A34A" if pct == 100 else "#D97706" if pct >= 70 else "#DC2626"

    st.markdown(
        f"<div style='background:#1E293B;border-radius:10px;padding:14px 18px;margin-bottom:16px'>"
        f"<div style='display:flex;justify-content:space-between;margin-bottom:8px'>"
        f"<span style='color:#F1F5F9;font-weight:600'>Validation Score</span>"
        f"<span style='color:{bar_col};font-weight:700'>{passed}/{total} passed</span></div>"
        f"<div style='background:#334155;border-radius:4px;height:8px'>"
        f"<div style='background:{bar_col};border-radius:4px;height:8px;width:{pct}%'></div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for chk in report:
        if chk["passed"]:
            icon, color = "✅", "#16A34A"
        elif chk.get("severity") == "WARNING":
            icon, color = "⚠️", "#D97706"
        else:
            icon, color = "❌", "#DC2626"
        label = RULE_LABELS.get(chk["rule"], chk["rule"])
        st.markdown(
            f"<div style='padding:8px 12px;border-bottom:1px solid #1E293B;display:flex;"
            f"gap:10px;align-items:flex-start'>"
            f"<span>{icon}</span>"
            f"<div><span style='color:{color};font-weight:600;font-size:13px'>{label}</span>"
            f"<span style='color:#64748B;font-size:12px'> — {chk['message']}</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_billing_breakdown(s: dict):
    bd = s.get("billing_data", {})
    if not bd:
        st.info("Billing data not available.")
        return
    cur = bd.get("currency", "AED")
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.metric("Regular Hours",  f"{bd.get('regular_hours', 0):,.1f}h")
    bc2.metric("Overtime Hours", f"{bd.get('overtime_hours', 0):,.1f}h")
    bc3.metric("Subtotal",       f"{cur} {bd.get('subtotal', 0):,.2f}")
    bc4.metric("GST",            f"{cur} {bd.get('gst_amount', 0):,.2f}")

    items = bd.get("line_items", [])
    if items:
        import pandas as pd
        df = pd.DataFrame(items)
        if "amount" in df.columns:
            df["amount"] = df["amount"].apply(lambda x: f"{cur} {float(x):,.2f}")
        if "rate" in df.columns:
            df["rate"] = df["rate"].apply(lambda x: f"{cur} {float(x):,.2f}")
        st.dataframe(df, use_container_width=True, hide_index=True)

    for note in bd.get("billing_notes", []):
        st.caption(f"• {note}")


def _render_failure_reasons(s: dict):
    report  = s.get("validation_report", [])
    errors  = s.get("val_errors", []) or s.get("doc_errors", [])
    failed  = [c for c in report if not c["passed"] and c.get("severity") == "ERROR"]
    warned  = [c for c in report if not c["passed"] and c.get("severity") == "WARNING"]

    if not failed and not errors:
        st.info("No specific failure reasons recorded.")
        return

    if failed:
        st.markdown(
            "<p style='color:#F87171;font-weight:600;margin-bottom:8px'>"
            "BLOCKING ISSUES — must be resolved before invoice can generate</p>",
            unsafe_allow_html=True,
        )
        for chk in failed:
            title, guide = RULE_FIX_GUIDE.get(chk["rule"], (chk["rule"], chk["message"]))
            st.markdown(
                f"<div class='reason-card' style='border-color:#7F1D1D'>"
                f"<h4>❌ {title}</h4>"
                f"<p style='color:#FCA5A5;font-size:13px;margin:4px 0 6px'>{chk['message']}</p>"
                f"<p style='color:#94A3B8;font-size:12px'>💡 <b>Action:</b> {guide}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if warned:
        st.markdown(
            "<p style='color:#FCD34D;font-weight:600;margin:16px 0 8px'>"
            "WARNINGS — reviewer should confirm before approving</p>",
            unsafe_allow_html=True,
        )
        for chk in warned:
            title, guide = RULE_FIX_GUIDE.get(chk["rule"], (chk["rule"], chk["message"]))
            st.markdown(
                f"<div class='reason-card' style='border-color:#92400E'>"
                f"<h4>⚠️ {title}</h4>"
                f"<p style='color:#FCD34D;font-size:13px;margin:4px 0 6px'>{chk['message']}</p>"
                f"<p style='color:#94A3B8;font-size:12px'>💡 <b>Note:</b> {guide}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if errors and not failed:
        for e in errors:
            st.error(f"⛔ {e}")


def _render_fix_guidance(s: dict):
    conf = s.get("doc_confidence", 0)
    report = s.get("validation_report", [])
    failed_rules = {c["rule"] for c in report if not c["passed"] and c.get("severity") == "ERROR"}
    steps = []

    if conf < 0.75:
        steps.append(("Improve document quality for higher confidence", [
            "Ensure the document is not blurry, skewed, or low-contrast.",
            "For handwritten timesheets: use dark ink and print clearly.",
            "For Excel: use standard column headers (Employee_ID, Customer_Code, Days_Worked, Basic_Salary).",
            "Include explicit billing period dates (e.g. '01-Jun-2026 to 30-Jun-2026').",
        ]))

    if "MANDATORY_FIELDS" in failed_rules:
        steps.append(("Add missing required fields to the document", [
            "Employee ID must be present (e.g. EMP001 or CUST001 format).",
            "Client/customer code must be present (e.g. CUST002).",
            "Billing rate or monthly salary must be specified.",
            "At least one timesheet row with hours worked must be included.",
        ]))

    if "EMPLOYEE_EXISTS" in failed_rules or "CLIENT_EXISTS" in failed_rules:
        steps.append(("Verify employee/client master records", [
            "Confirm the employee ID with HR — they must be registered in the system.",
            "Confirm the client code with your account manager.",
            "If new, ask an administrator to add them before re-uploading.",
        ]))

    if "CONTRACT_ACTIVE" in failed_rules or "BILLING_PERIOD_IN_CONTRACT" in failed_rules:
        steps.append(("Check contract and billing dates", [
            "Confirm the contract start and end dates are correct.",
            "Ensure the billing period falls within the contract validity window.",
            "Contact the contract administrator if the contract needs to be extended.",
        ]))

    if not steps:
        steps.append(("Awaiting manual review", [
            "A reviewer on the Review Queue page will inspect the extracted data.",
            "They can approve the document to trigger invoice generation.",
            "Or reject it with notes explaining what needs to be corrected.",
        ]))

    for i, (title, bullets) in enumerate(steps, 1):
        st.markdown(
            f"<div style='background:#1E293B;border-radius:10px;padding:16px;margin:10px 0;"
            f"border-left:3px solid #2563EB'>"
            f"<p style='color:#93C5FD;font-weight:700;font-size:14px;margin:0 0 10px'>"
            f"Step {i}: {title}</p>",
            unsafe_allow_html=True,
        )
        for b in bullets:
            st.markdown(f"<p style='color:#94A3B8;font-size:13px;margin:4px 0 4px 8px'>→ {b}</p>",
                        unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_success(s: dict):
    inv   = s.get("invoice_data", {})
    b     = s.get("billing_data", {}) or inv.get("billing", {})
    cur   = b.get("currency", "AED")
    total = b.get("total_amount", inv.get("total_amount", 0))
    inr   = b.get("total_amount_inr", inv.get("total_amount_inr", 0))
    conf  = s.get("doc_confidence", 0)

    if s.get("is_duplicate"):
        st.warning("**Duplicate document** — this invoice already exists. Showing the existing record.")

    st.markdown(
        f"<div style='background:linear-gradient(135deg,#0B2818,#0F2027);border:1px solid #16A34A;"
        f"border-radius:12px;padding:20px 24px;margin:0 0 16px'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div>"
        f"<p style='color:#4ADE80;font-size:11px;font-weight:700;letter-spacing:1px;margin:0'>INVOICE GENERATED</p>"
        f"<h2 style='color:#F1F5F9;margin:4px 0;font-size:22px'>{s.get('invoice_number','—')}</h2>"
        f"<p style='color:#64748B;font-size:12px;margin:0'>"
        f"Employee: {inv.get('employee_name','')} &nbsp;|&nbsp; "
        f"Client: {inv.get('client_name','')} &nbsp;|&nbsp; "
        f"Period: {inv.get('billing_period_start','')} → {inv.get('billing_period_end','')}</p>"
        f"</div>"
        f"<div style='text-align:right'>"
        f"<p style='color:#4ADE80;font-size:24px;font-weight:800;margin:0'>{cur} {total:,.2f}</p>"
        f"<p style='color:#475569;font-size:12px;margin:2px 0'>≈ INR {inr:,.2f}</p>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("AI Confidence",  f"{conf:.0%}")
    k2.metric("Total Amount",   f"{cur} {total:,.2f}")
    k3.metric("INR Equivalent", f"₹{inr:,.2f}")
    k4.metric("Status", "DUPLICATE" if s.get("is_duplicate") else "✅ GENERATED")

    t_preview, t_dl, t_conf, t_val, t_billing = st.tabs(
        ["📄 Invoice Preview", "📥 Downloads", "🎯 Confidence", "✅ Validation", "💰 Billing"]
    )

    with t_preview:
        st.markdown(
            "<p style='color:#94A3B8;font-size:12px;margin-bottom:8px'>"
            "Invoice as it will appear in the PDF. Download for the official signed copy.</p>",
            unsafe_allow_html=True,
        )
        html = render_invoice_html({**inv, "billing": b})
        st.components.v1.html(html, height=720, scrolling=True)

    with t_dl:
        st.markdown("<br>", unsafe_allow_html=True)
        dc1, dc2 = st.columns(2)
        pdf_p = s.get("pdf_path", "") or inv.get("pdf_path", "")
        xls_p = s.get("excel_path", "") or inv.get("excel_path", "")

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
            dc2.caption("ERP Excel not available")

        st.session_state["last_invoice_number"] = s.get("invoice_number", "")

    with t_conf:
        _render_confidence_breakdown(s)

    with t_val:
        _render_validation_report(s)

    with t_billing:
        _render_billing_breakdown(s)


def _render_review(s: dict):
    conf       = s.get("doc_confidence", 0)
    val_errors = s.get("val_errors", [])

    if val_errors:
        reason = "Document failed data validation — required fields are missing or incorrect"
        detail = "The document was read but did not pass all validation checks."
    elif conf < 0.75:
        reason = f"AI extraction confidence too low ({conf:.0%} < 75% threshold)"
        detail = "The document was unclear, ambiguous, or missing too many fields for automatic processing."
    else:
        reason = "Manual verification required"
        detail = "This document has been flagged for human review before the invoice can be generated."

    st.markdown(
        f"<div style='background:#1C1408;border:2px solid #D97706;border-radius:12px;padding:20px 24px;margin:0 0 16px'>"
        f"<div style='display:flex;gap:12px;align-items:flex-start'>"
        f"<span style='font-size:24px'>🔍</span>"
        f"<div>"
        f"<p style='color:#FCD34D;font-size:15px;font-weight:700;margin:0 0 4px'>"
        f"NEEDS HUMAN REVIEW — Queue #{s.get('review_queue_id','—')}</p>"
        f"<p style='color:#F59E0B;font-size:13px;font-weight:600;margin:0 0 4px'>{reason}</p>"
        f"<p style='color:#94A3B8;font-size:12px;margin:0'>{detail}</p>"
        f"</div></div></div>",
        unsafe_allow_html=True,
    )

    k1, k2 = st.columns(2)
    k1.metric("AI Confidence Score", f"{conf:.0%}",
              help="Score reflects how clearly the AI could read and extract data")
    k2.metric("Review Queue #", s.get("review_queue_id", "—"))

    t_why, t_conf, t_fix = st.tabs(["❓ Why It Failed", "🎯 Confidence Breakdown", "🔧 How to Fix"])

    with t_why:
        _render_failure_reasons(s)

    with t_conf:
        _render_confidence_breakdown(s)

    with t_fix:
        _render_fix_guidance(s)

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👉 Go to the **Review Queue** page to approve or reject this document after manual review.")


def _render_failed(s: dict):
    errors = s.get("doc_errors", []) or s.get("val_errors", [])
    st.markdown(
        "<div style='background:#1C0808;border:2px solid #DC2626;border-radius:12px;padding:20px 24px;margin:0 0 16px'>"
        "<p style='color:#F87171;font-size:15px;font-weight:700;margin:0 0 4px'>❌ PROCESSING FAILED</p>"
        "<p style='color:#94A3B8;font-size:13px;margin:0'>The document could not be processed. See details below.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    for e in errors:
        st.error(f"⛔ {e}")
    st.warning("Ensure the file is not corrupted, is a supported format, and contains readable timesheet data.")


def _render_result(s: dict):
    if s.get("success"):
        _render_success(s)
    elif s.get("routed_to_review"):
        _render_review(s)
    else:
        _render_failed(s)


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
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

    if "sentinel_state" in st.session_state:
        s = st.session_state["sentinel_state"]
        st.markdown("<hr style='border-color:#1E293B;margin:16px 0 8px'>", unsafe_allow_html=True)
        st.markdown("<p style='color:#475569;font-size:11px;padding:0 8px;margin:0'>LAST PROCESSED</p>",
                    unsafe_allow_html=True)
        if s.get("success"):
            st.markdown(
                f"<p style='color:#4ADE80;font-size:12px;padding:0 8px'>✅ {s.get('invoice_number','')}</p>",
                unsafe_allow_html=True,
            )
        elif s.get("routed_to_review"):
            st.markdown(
                f"<p style='color:#FCD34D;font-size:12px;padding:0 8px'>🔍 Queue #{s.get('review_queue_id','')}</p>",
                unsafe_allow_html=True,
            )

# ─────────────────────────────────────────────────────────────
# PAGE HEADER
# ─────────────────────────────────────────────────────────────
col_hdr, col_reset = st.columns([4, 1])
col_hdr.markdown("<h2 style='color:#F1F5F9;margin:0'>📤 Upload & Process</h2>", unsafe_allow_html=True)
col_hdr.markdown(
    "<p style='color:#94A3B8;margin:0'>Upload any timesheet. Sentinel auto-generates the invoice if confidence ≥ 75%.</p>",
    unsafe_allow_html=True,
)

if "sentinel_state" in st.session_state:
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 New Upload", use_container_width=True):
            del st.session_state["sentinel_state"]
            st.rerun()

st.markdown("<hr style='border-color:#1E293B;margin:12px 0'>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CASE A: Persisted result — show it without re-processing
# ─────────────────────────────────────────────────────────────
if "sentinel_state" in st.session_state and st.session_state["sentinel_state"].get("_processed"):
    _render_result(st.session_state["sentinel_state"])
    st.markdown("<hr style='border-color:#1E293B;margin:24px 0 12px'>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#475569;font-size:13px;text-align:center'>"
        "↑ Showing persisted result. Click <b>🔄 New Upload</b> (top-right) to process a new document.</p>",
        unsafe_allow_html=True,
    )
    st.stop()

# ─────────────────────────────────────────────────────────────
# CASE B: Upload form
# ─────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Drop your timesheet here",
    type=["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg"],
    help="Supports PDF, Excel, CSV, and images (handwritten or typed)",
)

if not uploaded:
    st.markdown("""
    <div style='background:#1E293B;border-radius:12px;padding:32px;text-align:center;
                border:2px dashed #334155;margin-top:16px'>
      <div style='font-size:44px;margin-bottom:12px'>📂</div>
      <p style='color:#94A3B8;font-size:15px;margin:0'>Drop any timesheet document above to get started</p>
      <p style='color:#475569;font-size:13px;margin:10px 0 0'>
        PDF &nbsp;·&nbsp; Excel (XLSX/XLS) &nbsp;·&nbsp; CSV &nbsp;·&nbsp; PNG/JPG (typed or handwritten)
      </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.markdown(
    f"<div style='background:#0F2027;border:1px solid #2563EB;border-radius:8px;padding:12px 18px;"
    f"color:#93C5FD;margin:4px 0'>"
    f"📎 <b>{uploaded.name}</b> &nbsp; <span style='color:#475569'>({uploaded.size/1024:.1f} KB)</span>"
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

file_bytes = uploaded.read()

# ── Detect multi-row Excel BEFORE saving ────────────────────────────────────
from utils.excel_batch import is_multi_row_excel as _is_batch
import tempfile, os as _os
_tmp_path = None
_is_batch_mode = False

if uploaded.name.lower().endswith((".xlsx", ".xls")):
    # Peek at row count without saving permanently yet
    import io
    _tmp = tempfile.NamedTemporaryFile(suffix=Path(uploaded.name).suffix, delete=False)
    _tmp.write(file_bytes)
    _tmp.flush()
    _tmp_path = _tmp.name
    _tmp.close()
    _is_batch_mode = _is_multi_row_excel(_tmp_path) if 'is_multi_row_excel' in dir() else _is_batch(_tmp_path)

if _is_batch_mode:
    import pandas as _pd_check
    _row_count = len(_pd_check.read_excel(_tmp_path).dropna(how="all"))
    st.markdown(
        f"<div style='background:#0D2240;border:1px solid #2563EB;border-radius:8px;"
        f"padding:12px 18px;color:#93C5FD;margin:4px 0'>"
        f"📊 <b>Batch mode detected</b> — {_row_count} employee rows found. "
        f"Sentinel will generate an invoice for each employee.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

if not st.button("⚡ Process Document", type="primary", use_container_width=True):
    st.stop()

file_path = save_upload(file_bytes, uploaded.name)
if _tmp_path:
    try: _os.unlink(_tmp_path)
    except Exception: pass

st.markdown("<hr style='border-color:#1E293B'>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# BATCH MODE — multi-row Excel
# ════════════════════════════════════════════════════════════════
if _is_batch_mode:
    st.markdown("<h3 style='color:#F1F5F9;margin-bottom:12px'>Batch Processing</h3>", unsafe_allow_html=True)
    prog_bar    = st.progress(0)
    status_area = st.empty()

    with st.spinner("Processing all employees…"):
        pipeline = SentinelPipeline()
        batch_results = pipeline.run_batch(file_path)

    prog_bar.progress(1.0)
    status_area.empty()

    # ── Batch summary card ─────────────────────────────────────
    n_ok  = sum(1 for r in batch_results if r.success or r.is_duplicate)
    n_rev = sum(1 for r in batch_results if r.routed_to_review)
    n_dup = sum(1 for r in batch_results if r.is_duplicate)
    n_tot = len(batch_results)

    st.markdown(
        f"<div style='background:#0F2027;border:1px solid #2563EB;border-radius:12px;"
        f"padding:16px 22px;margin:0 0 16px;display:flex;gap:32px;align-items:center'>"
        f"<div><p style='color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:1px;margin:0'>BATCH COMPLETE</p>"
        f"<p style='color:#F1F5F9;font-size:18px;font-weight:800;margin:4px 0'>{n_tot} employees processed</p></div>"
        f"<div style='display:flex;gap:20px'>"
        f"<div><p style='color:#4ADE80;font-size:22px;font-weight:800;margin:0'>{n_ok}</p>"
        f"<p style='color:#94A3B8;font-size:11px;margin:0'>Invoices</p></div>"
        f"<div><p style='color:#FCD34D;font-size:22px;font-weight:800;margin:0'>{n_rev}</p>"
        f"<p style='color:#94A3B8;font-size:11px;margin:0'>Review</p></div>"
        f"<div><p style='color:#64748B;font-size:22px;font-weight:800;margin:0'>{n_dup}</p>"
        f"<p style='color:#94A3B8;font-size:11px;margin:0'>Duplicate</p></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── Per-row results ────────────────────────────────────────
    for i, r in enumerate(batch_results):
        doc_data = r.document.data or {}
        emp = (doc_data.get("employee") or {})
        cli = (doc_data.get("client") or {})
        emp_name = emp.get("name", f"Row {i+2}")
        cli_name = cli.get("company_name", "—")

        if r.success:
            inv_data = r.invoice.data or {}
            billing  = inv_data.get("billing", {})
            cur      = billing.get("currency", "AED")
            total    = billing.get("total_amount", 0)
            icon, border, label = "✅", "#16A34A", f"{r.invoice_number} — {cur} {total:,.2f}"
        elif r.is_duplicate:
            icon, border, label = "♻️", "#475569", f"{r.invoice_number} — already exists"
        elif r.routed_to_review:
            icon, border, label = "🔍", "#D97706", f"Sent to Review Queue #{r.review_queue_id}"
        else:
            icon, border, label = "❌", "#DC2626", "Processing failed"

        with st.expander(f"{icon} {emp_name} → {cli_name}   {label}", expanded=False):
            if r.success:
                inv_data = r.invoice.data or {}
                billing  = inv_data.get("billing", {})
                from utils.invoice_html import render_invoice_html
                html = render_invoice_html({**inv_data, "billing": billing})
                st.components.v1.html(html, height=600, scrolling=True)
                pdf_p = r.pdf_path
                if pdf_p and Path(pdf_p).exists():
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 Download PDF", f.read(),
                            file_name=Path(pdf_p).name, mime="application/pdf",
                            key=f"batch_pdf_{i}", type="primary")
            elif r.routed_to_review:
                st.warning(f"Sent to Review Queue #{r.review_queue_id}. Confidence: {r.pipeline_confidence:.0%}")
                if r.validation and r.validation.errors:
                    for e in r.validation.errors:
                        st.error(f"⛔ {e}")
            elif r.is_duplicate:
                st.info(f"Invoice {r.invoice_number} already generated for this employee/period.")
            else:
                st.error("Processing failed.")
                for e in r.document.errors:
                    st.error(f"⛔ {e}")

    # Store batch state
    st.session_state["sentinel_state"] = {
        "_processed": True,
        "_batch": True,
        "batch_count": n_tot,
        "invoices_generated": n_ok,
        "review_count": n_rev,
    }
    st.info("👉 Go to **Invoice Preview** to see all generated invoices across clients.")
    st.stop()

# ════════════════════════════════════════════════════════════════
# SINGLE FILE MODE — pipeline progress
# ════════════════════════════════════════════════════════════════
st.markdown("<h3 style='color:#F1F5F9;margin-bottom:12px'>Pipeline Progress</h3>", unsafe_allow_html=True)

_ph = {k: st.empty() for k in PIPELINE_STAGES}


def _stage(key, status, detail=""):
    icon, label, sub = PIPELINE_STAGES[key]
    col = STATUS_COLOR.get(status, "#1E293B")
    si  = STATUS_ICON.get(status, "⏳")
    det = (f"<br><span style='font-size:12px;color:#94A3B8;margin-left:24px'>{detail}</span>"
           if detail else "")
    _ph[key].markdown(
        f"<div class='stage-card' style='border-left-color:{col}'>"
        f"{si} <b>{icon} {label}</b>"
        f"<span style='color:#475569;font-size:12px'> — {sub}</span>{det}</div>",
        unsafe_allow_html=True,
    )


for _k in PIPELINE_STAGES:
    _stage(_k, "pending")

_stage("document", "running")
with st.spinner("Sentinel is processing your document…"):
    pipeline = SentinelPipeline()
    result   = pipeline.run(file_path)

doc_ = result.document
pd_  = result.processing
vd_  = result.validation
inv_ = result.invoice

if doc_.status == "FAILED":
    _stage("document", "failed", doc_.errors[0] if doc_.errors else "Extraction failed")
    for _k in ["processing", "validation", "invoice", "database"]:
        _stage(_k, "skipped")
else:
    conf = doc_.confidence
    cc   = "#16A34A" if conf >= 0.90 else "#D97706" if conf >= 0.75 else "#DC2626"
    _stage("document", "done", f"Confidence: <b style='color:{cc}'>{conf:.0%}</b>")

    if pd_:
        amt = pd_.data.get("total_amount", 0) if pd_.data else 0
        cr  = pd_.data.get("currency", "") if pd_.data else ""
        _stage("processing", "done" if pd_.status == "SUCCESS" else "failed",
               f"Total: <b>{cr} {amt:,.2f}</b>")
    else:
        _stage("processing", "skipped")

    if vd_:
        chk = vd_.data or {}
        if vd_.status == "SUCCESS":
            _stage("validation", "done",
                   f"{chk.get('passed', 0)}/{chk.get('total_checks', 0)} checks passed")
        elif result.is_duplicate:
            _stage("validation", "warn", "Duplicate — existing invoice returned")
        else:
            _stage("validation", "failed", vd_.errors[0] if vd_.errors else "Validation failed")
    else:
        _stage("validation", "skipped")

    if result.success:
        _stage("invoice",  "done")
        _stage("database", "skipped" if result.is_duplicate else "done",
               "Already saved" if result.is_duplicate else "")
    else:
        _stage("invoice",  "skipped")
        _stage("database", "skipped")

# ─────────────────────────────────────────────────────────────
# PERSIST & RENDER
# ─────────────────────────────────────────────────────────────
st.session_state["sentinel_state"] = _serialise(result)
st.markdown("<hr style='border-color:#1E293B;margin:16px 0'>", unsafe_allow_html=True)
_render_result(st.session_state["sentinel_state"])
