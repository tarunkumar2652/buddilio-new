"""Buddilio Pass — the voucher / m-token issued for every paid booking.

A pass carries a QR code plus a short human code, is redeemable exactly once by whoever the
member is meeting, and is voided the moment the booking is refunded or cancelled.
"""
import io
import random
import string

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdfbrand import logo

ACCENT = colors.HexColor("#C2185B")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")

KIND_LABELS = {"event": "Event ticket", "product": "Experience pass", "hangout": "Paid hangout",
               "travel": "Travel booking", "membership": "Membership"}
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no look-alikes


def new_code() -> str:
    """Human-readable, phone-friendly: BUD-4F7K-92."""
    block = "".join(random.choice(ALPHABET) for _ in range(4))
    tail = "".join(random.choice(string.digits) for _ in range(2))
    return f"BUD-{block}-{tail}"


def qr_png(payload: str, box: int = 8) -> bytes:
    import qrcode
    img = qrcode.make(payload, box_size=box, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _p(text, size=10, colour=INK, bold=False, align=0, leading=None):
    style = ParagraphStyle("s", fontName="Helvetica-Bold" if bold else "Helvetica",
                           fontSize=size, textColor=colour, leading=leading or size * 1.35,
                           alignment=align)
    return Paragraph(text, style)


def pass_pdf(v: dict, verify_url: str) -> bytes:
    """A5 print-friendly voucher with the QR, the code and the terms."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=13 * mm, bottomMargin=13 * mm,
                            title=v.get("code", "Buddilio Pass"), author="Buddilio")
    widget = qr.QrCodeWidget(verify_url)
    b = widget.getBounds()
    size = 42 * mm
    drawing = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]),
                                             -b[0] * size / (b[2] - b[0]), -b[1] * size / (b[3] - b[1])])
    drawing.add(widget)

    head = Table([[logo(13 * mm) or _p("BUDDILIO", 15, ACCENT, bold=True),
                   _p(KIND_LABELS.get(v.get("kind", ""), "Booking").upper(), 8, MUTED, bold=True, align=2)]],
                 colWidths=[60 * mm, 52 * mm])
    rows = [("Guest", v.get("user_name") or "—"),
            ("What", v.get("item_name") or "—"),
            ("When", str(v.get("starts_at") or "As booked")[:16].replace("T", " ")),
            ("Where", v.get("city") or "—"),
            ("Host / vendor", v.get("vendor_name") or "Buddilio"),
            ("Order", f"#{v.get('order_no', '')}"),
            ("Paid", v.get("amount_label") or "—"),
            ("Guests", str(v.get("quantity") or 1))]
    detail = Table([[_p(k, 8, MUTED, bold=True), _p(str(val), 9.5)] for k, val in rows],
                   colWidths=[30 * mm, 82 * mm])
    detail.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                                ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    code_block = Table([[drawing, _p(f"<b>Verification code</b><br/>"
                                     f"<font size=17 color='#0F172A'>{v.get('code', '')}</font><br/><br/>"
                                     f"<font size=7.5 color='#64748B'>Scan the QR or type this code at "
                                     f"buddilio.com/verify. Valid for one entry.</font>", 9, MUTED)]],
                       colWidths=[46 * mm, 66 * mm])
    terms = ("Show this pass to your organiser, host or companion. It can be redeemed once and becomes "
             "invalid if the booking is cancelled or refunded. Carry a government photo ID — Buddilio is "
             "an 18+/21+ social discovery platform and entry stays at the organiser's discretion. "
             "Never share this code publicly.")
    flow = [head, Spacer(1, 5 * mm), code_block, Spacer(1, 5 * mm), detail, Spacer(1, 5 * mm),
            _p(terms, 7.5, MUTED),
            Spacer(1, 4 * mm),
            _p(f"Issued {str(v.get('created_at', ''))[:10]} · {verify_url}", 7, MUTED)]
    doc.build(flow)
    return buf.getvalue()
