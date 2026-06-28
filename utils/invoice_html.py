"""
Render an Invoice as a self-contained HTML string for inline Streamlit preview.
All styling is embedded so the iframe is fully portable.
"""
from __future__ import annotations


def render_invoice_html(inv: dict) -> str:
    """
    inv  — dict from DatabaseService.get_invoice() OR invoice_engine result.data
    Returns a complete HTML document string.
    """
    b       = inv.get("billing", {})
    cur     = b.get("currency", inv.get("currency", "AED"))
    items   = b.get("line_items", [])
    notes   = b.get("billing_notes", [])

    def fmt(amt):
        try:
            return f"{cur} {float(amt):,.2f}"
        except Exception:
            return str(amt)

    def row(label, value, bold=False):
        style = "font-weight:700;" if bold else ""
        return f"<tr><td style='color:#64748B;padding:6px 12px;font-size:13px'>{label}</td><td style='padding:6px 12px;font-size:13px;{style}'>{value}</td></tr>"

    # Line items
    item_rows = ""
    for it in items:
        hrs  = f"{float(it.get('hours',0)):,.1f}h" if it.get("hours") else "—"
        rate = fmt(it.get("rate", 0))
        amt  = fmt(it.get("amount", 0))
        item_rows += f"""
        <tr style='border-bottom:1px solid #E2E8F0'>
          <td style='padding:10px 14px;font-size:13px;color:#1E293B'>{it.get('description','')}</td>
          <td style='padding:10px 14px;font-size:13px;text-align:right;color:#475569'>{hrs}</td>
          <td style='padding:10px 14px;font-size:13px;text-align:right;color:#475569'>{rate}</td>
          <td style='padding:10px 14px;font-size:13px;text-align:right;font-weight:600;color:#1E293B'>{amt}</td>
        </tr>"""

    gst_pct = 0
    if b.get("subtotal") and b.get("gst_amount"):
        try:
            gst_pct = round(float(b["gst_amount"]) / float(b["subtotal"]) * 100)
        except Exception:
            pass

    notes_html = ""
    if notes:
        notes_html = "<div style='margin-top:18px;padding:12px 16px;background:#F8FAFC;border-radius:8px;border-left:3px solid #2563EB'>"
        notes_html += "<p style='font-size:11px;color:#94A3B8;margin:0 0 6px;font-weight:600;letter-spacing:.5px'>BILLING NOTES</p>"
        for n in notes:
            notes_html += f"<p style='font-size:12px;color:#475569;margin:2px 0'>• {n}</p>"
        notes_html += "</div>"

    inr_row = ""
    if cur != "INR":
        inr_val = b.get("total_amount_inr", inv.get("total_amount_inr", 0))
        inr_row = f"<tr><td style='padding:8px 14px;color:#94A3B8;font-size:12px'>INR Equivalent</td><td colspan='3' style='padding:8px 14px;text-align:right;color:#94A3B8;font-size:12px'>INR {float(inr_val):,.2f}</td></tr>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #F1F5F9; padding: 20px; }}
  .page {{ max-width: 860px; margin: 0 auto; background: white; border-radius: 12px;
           box-shadow: 0 4px 24px rgba(0,0,0,.10); overflow: hidden; }}
  .hdr {{ background: #0F172A; padding: 28px 36px; display: flex;
          justify-content: space-between; align-items: center; }}
  .hdr-left h1 {{ font-size: 26px; color: white; font-weight: 800; letter-spacing: -0.5px; }}
  .hdr-left p  {{ font-size: 11px; color: #2563EB; font-weight: 600; letter-spacing: 1px; margin-top: 2px; }}
  .hdr-right {{ text-align: right; }}
  .hdr-right .inv-label {{ font-size: 11px; color: #94A3B8; letter-spacing: 1px; }}
  .hdr-right .inv-num   {{ font-size: 18px; color: white; font-weight: 700; }}
  .hdr-right .inv-dates {{ font-size: 11px; color: #64748B; margin-top: 4px; line-height: 1.8; }}
  .stripe {{ height: 4px; background: linear-gradient(90deg, #2563EB, #7C3AED); }}
  .body {{ padding: 28px 36px; }}
  .parties {{ display: flex; gap: 16px; margin-bottom: 20px; }}
  .party {{ flex: 1; padding: 16px; border-radius: 8px; }}
  .party.from {{ background: #F8FAFC; }}
  .party.to   {{ background: #EFF6FF; }}
  .party-label {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; color: #2563EB; margin-bottom: 6px; }}
  .party-name  {{ font-size: 15px; font-weight: 700; color: #0F172A; }}
  .party-sub   {{ font-size: 12px; color: #64748B; margin-top: 2px; line-height: 1.6; }}
  .meta {{ background: #F8FAFC; border-radius: 8px; margin-bottom: 20px; overflow: hidden; }}
  .meta table {{ width: 100%; border-collapse: collapse; }}
  .meta tr:nth-child(even) {{ background: white; }}
  .items-table {{ width: 100%; border-collapse: collapse; border-radius: 8px; overflow: hidden;
                  margin-bottom: 0; border: 1px solid #E2E8F0; }}
  .items-table thead tr {{ background: #0F172A; }}
  .items-table thead th {{ padding: 10px 14px; color: white; font-size: 12px; font-weight: 600;
                           text-align: right; letter-spacing: .3px; }}
  .items-table thead th:first-child {{ text-align: left; }}
  .totals-table {{ width: 100%; border-collapse: collapse; margin-top: 0;
                   border: 1px solid #E2E8F0; border-top: none; }}
  .totals-table tr td {{ padding: 8px 14px; font-size: 13px; }}
  .totals-table .total-row td {{ background: #2563EB; color: white; font-weight: 700;
                                  font-size: 15px; padding: 12px 14px; }}
  .footer {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid #E2E8F0;
             display: flex; justify-content: space-between; align-items: center; }}
  .footer p {{ font-size: 11px; color: #94A3B8; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px;
            font-size: 11px; font-weight: 700; background: #DCFCE7; color: #166534; }}
</style>
</head>
<body>
<div class="page">

  <div class="hdr">
    <div class="hdr-left">
      <h1>SENTINEL</h1>
      <p>TOUCHLESS INVOICE AUTOMATION</p>
    </div>
    <div class="hdr-right">
      <div class="inv-label">INVOICE</div>
      <div class="inv-num">{inv.get('invoice_number','—')}</div>
      <div class="inv-dates">
        Issued:&nbsp;&nbsp;{inv.get('invoice_date','—')}<br>
        Due By:&nbsp;&nbsp;{inv.get('due_date','—')}
      </div>
    </div>
  </div>
  <div class="stripe"></div>

  <div class="body">
    <div class="parties">
      <div class="party from">
        <div class="party-label">FROM</div>
        <div class="party-name">TASC Outsourcing</div>
        <div class="party-sub">billing@tasc.ae<br>Dubai, UAE</div>
      </div>
      <div class="party to">
        <div class="party-label">BILL TO</div>
        <div class="party-name">{inv.get('client_name','—')}</div>
        <div class="party-sub">Client ID: {inv.get('client_id','—')}</div>
      </div>
    </div>

    <div class="meta">
      <table>
        {row('Billing Period', f"{inv.get('billing_period_start','—')} &nbsp;to&nbsp; {inv.get('billing_period_end','—')}")}
        {row('Employee', f"{inv.get('employee_name','—')} &nbsp;({inv.get('employee_id','—')})")}
        {row('Contract Reference', inv.get('contract_id','—'))}
        {row('Currency', cur)}
        {row('Payment Terms', f"Due by {inv.get('due_date','—')}")}
      </table>
    </div>

    <table class="items-table">
      <thead>
        <tr>
          <th>Description</th>
          <th>Hours</th>
          <th>Rate</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>
        {item_rows if item_rows else '<tr><td colspan="4" style="padding:14px;text-align:center;color:#94A3B8">No line items</td></tr>'}
      </tbody>
    </table>

    <table class="totals-table">
      <tr style='background:#F8FAFC'>
        <td colspan='3' style='text-align:right;color:#64748B'>Subtotal</td>
        <td style='text-align:right;font-weight:600'>{fmt(b.get('subtotal',0))}</td>
      </tr>
      <tr>
        <td colspan='3' style='text-align:right;color:#64748B'>GST ({gst_pct}%)</td>
        <td style='text-align:right'>{fmt(b.get('gst_amount',0))}</td>
      </tr>
      <tr class='total-row'>
        <td colspan='3' style='text-align:right'>TOTAL DUE</td>
        <td style='text-align:right'>{fmt(b.get('total_amount', inv.get('total_amount',0)))}</td>
      </tr>
      {inr_row}
    </table>

    {notes_html}

    <div class="footer">
      <p>Please remit payment by <strong>{inv.get('due_date','—')}</strong>. Queries: billing@tasc.ae</p>
      <span class="badge">GENERATED</span>
    </div>
  </div>

</div>
</body>
</html>"""
