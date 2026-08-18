"""Invoice + receipt PDFs. One template per kind of money we take, so a hangout receipt doesn't read
like a store invoice."""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
ACCENT = colors.HexColor("#be185d")

# Per-kind wording: heading, what the line item is called, and the footnote that matters for that product.
TEMPLATES = {
    "membership": {"heading": "Membership invoice", "line": "Membership plan",
                   "note": "Your membership renews only if you choose to renew it. Manage it any time under "
                           "Membership in your account."},
    "product": {"heading": "Store invoice", "line": "Item",
                "note": "Store orders follow the return window shown at checkout."},
    "event": {"heading": "Ticket receipt", "line": "Event ticket",
              "note": "Carry this receipt to the venue. Cancellation follows the organiser's policy on the "
                      "event page."},
    "companion": {"heading": "Hangout receipt", "line": "Paid hangout",
                  "note": "Hangouts are company only. Request fees are non-refundable; declines and no-shows "
                          "are settled as Buddilio credit."},
    "wallet": {"heading": "Wallet top-up receipt", "line": "Wallet credit",
               "note": "This is stored credit, not a service charge. It never expires and is spent on your "
                       "next booking."},
    "travel": {"heading": "Travel service receipt", "line": "Travel service",
               "note": "Paid through Buddilio. Your provider is paid after the service, minus the Buddilio "
                       "service fee shown in your ledger."},
    "provider_fee": {"heading": "Registration invoice", "line": "Travel provider registration",
                     "note": "One-time listing fee for travel crew. It is not a commission and is not "
                             "refundable once your profile is reviewed."},
}
DEFAULT_TEMPLATE = {"heading": "Invoice", "line": "Item", "note": ""}


def template_for(kind: str) -> dict:
    return TEMPLATES.get(kind, DEFAULT_TEMPLATE)


def _p(text, size=9.5, colour=INK, bold=False, align=0, leading=None):
    style = ParagraphStyle(f"s{size}{bold}{align}", parent=getSampleStyleSheet()["BodyText"],
                           fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                           leading=leading or size * 1.35, textColor=colour, alignment=align)
    return Paragraph(text, style)


def invoice_pdf(inv: dict, symbol: str = "") -> bytes:
    """Renders the same data the invoice API returns, using the template for that kind."""
    tpl = template_for(inv.get("kind", ""))
    paid = inv.get("status") == "paid"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=inv.get("receipt_no") or inv.get("invoice_no"), author="Buddilio")

    def money(v):
        return f"{symbol}{float(v or 0):,.2f}"

    flow = [
        Table([[_p("BUDDILIO", 17, ACCENT, bold=True),
                _p(f"{'RECEIPT' if paid else 'INVOICE'}<br/>"
                   f"<font size=11>{inv.get('receipt_no') if paid else inv.get('invoice_no')}</font>",
                   8, MUTED, bold=True, align=2)]],
              colWidths=[95 * mm, 79 * mm]),
        Spacer(1, 4 * mm),
        _p(tpl["heading"], 13, INK, bold=True),
        _p(f"Issued {str(inv.get('issued_at', ''))[:10]}"
           + (f" · Paid {str(inv.get('paid_at', ''))[:10]}" if paid else "")
           + f" · Order {inv.get('order_no', '')}", 8.5, MUTED),
        Spacer(1, 6 * mm),
        Table([[_p("<b>From</b><br/>" + inv["seller"]["name"] + "<br/>" + inv["seller"]["site"]
                   + "<br/>" + inv["seller"]["email"], 9, MUTED),
                _p("<b>Billed to</b><br/>" + (inv["buyer"]["name"] or "Guest") + "<br/>"
                   + (inv["buyer"]["email"] or "") + "<br/>"
                   + ", ".join([x for x in [inv["buyer"].get("city"), inv["buyer"].get("country")] if x]),
                   9, MUTED)]],
              colWidths=[87 * mm, 87 * mm]),
        Spacer(1, 7 * mm),
    ]

    rows = [[_p(tpl["line"], 8.5, MUTED, bold=True), _p("QTY", 8.5, MUTED, bold=True, align=2),
             _p("AMOUNT", 8.5, MUTED, bold=True, align=2)]]
    for line in inv.get("lines", []):
        rows.append([_p(line.get("description", ""), 9.5),
                     _p(str(line.get("quantity", 1)), 9.5, align=2),
                     _p(money(line.get("amount")), 9.5, align=2)])
    table = Table(rows, colWidths=[112 * mm, 20 * mm, 42 * mm])
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, LINE),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    flow.append(table)

    totals = []
    if float(inv.get("discount") or 0) > 0:
        totals.append(["Discount", "− " + money(inv["discount"])])
    if float(inv.get("credit_applied") or 0) > 0:
        totals.append(["Buddilio credit", "− " + money(inv["credit_applied"])])
    tax_label = inv.get("tax_label") or "Tax"
    if inv.get("tax_percent"):
        tax_label += f" ({inv['tax_percent']}%)"
    totals.append([tax_label, money(inv.get("tax"))])
    if float(inv.get("commission") or 0) > 0 and inv.get("kind") in ("companion", "travel"):
        totals.append(["Buddilio service fee (included)", money(inv["commission"])])
    totals.append(["TOTAL", money(inv.get("total"))])

    tt = Table([[_p(l, 9.5, MUTED if l != "TOTAL" else INK, bold=(l == "TOTAL")),
                 _p(v, 9.5 if l != "TOTAL" else 12, INK, bold=(l == "TOTAL"), align=2)] for l, v in totals],
               colWidths=[112 * mm, 62 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.6, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    flow += [Spacer(1, 4 * mm), tt, Spacer(1, 8 * mm)]

    status = (f"Paid via {inv.get('gateway') or 'Buddilio'}"
              + (f" · {inv.get('transaction_id')}" if inv.get("transaction_id") else "")) if paid \
        else f"Status: {inv.get('status', 'pending')}"
    if inv.get("refund_status", "none") not in ("none", ""):
        status += f" · refund {inv['refund_status']}"
    flow.append(_p(status, 9, INK, bold=True))
    if tpl["note"]:
        flow += [Spacer(1, 3 * mm), _p(tpl["note"], 8.5, MUTED)]
    flow += [Spacer(1, 6 * mm),
             _p("Buddilio · buddilio.com · This document was generated automatically for the transaction "
                "above.", 7.5, MUTED)]

    doc.build(flow)
    return buf.getvalue()
