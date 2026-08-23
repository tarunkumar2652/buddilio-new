"""Vendor agreements: the legal text, the commercial maths and the executed PDF.

Nothing here touches the database — server.py owns persistence and the routes, this module owns the
wording, the pricing engine and the document, so the executed text can be frozen at acceptance.
"""
import hashlib
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from pdfbrand import logo

# Buddilio's own details. Editable in Admin → Settings (keys mirrored below).
ENTITY = {
    "legal_name": "Buddilio",
    "entity_type": "Registered firm",
    "signatory": "Manish Kumar",
    "signatory_title": "Authorised Signatory",
    "email": "info@buddilio.com",
    "msme": "UDYAM-HR-05-0203611",
    "gstin": "",
    "site": "buddilio.com",
    "jurisdiction": "Gurugram, Haryana, India",
}

VENDOR_KINDS = {
    "organiser": "Event organiser",
    "travel_provider": "Travel service provider",
    "companion": "Paid companion host",
}

VENDOR_STATUSES = ["draft", "submitted", "under_review", "documents_required", "approved",
                   "rejected", "suspended", "terminated"]
AGREEMENT_STATUSES = ["draft", "pending_vendor_acceptance", "active", "amendment_pending",
                      "suspended", "terminated"]
SETTLEMENT_CYCLES = ["T+1", "T+3", "T+7", "T+15", "custom"]
COMMISSION_TYPES = ["percentage", "fixed", "hybrid"]
RATE_POLICIES = {
    "none": "No parity requirement",
    "notify": "Vendor notifies Buddilio of materially different public pricing",
    "parity_law": "Commercial parity, subject to applicable law",
    "custom": "Custom contractual policy",
}
REFUND_RESPONSIBILITY = {"vendor": "Vendor", "buddilio": "Buddilio", "shared": "Shared"}
DISCOUNT_FUNDING = {"buddilio": "Buddilio", "vendor": "Vendor", "shared": "Shared"}
DOC_TYPES = [
    {"key": "pan", "label": "PAN", "required": True},
    {"key": "gst", "label": "GST certificate", "required": False},
    {"key": "registration", "label": "Business registration", "required": False},
    {"key": "trade_license", "label": "Trade licence", "required": False},
    {"key": "service_license", "label": "Service-specific licence", "required": False},
    {"key": "insurance", "label": "Insurance", "required": False},
    {"key": "cancelled_cheque", "label": "Cancelled cheque", "required": False,
     "hint": "Cancelled cheque or bank statement is mandatory for payment transfer."},
    {"key": "bank_statement", "label": "Bank statement", "required": False,
     "hint": "Recent statement showing account name, number and IFSC."},
    {"key": "bank_proof", "label": "Other bank proof", "required": False},
    {"key": "address_proof", "label": "Address proof", "required": True},
    {"key": "other", "label": "Other document", "required": False},
]
REQUIRED_DOCS = [d["key"] for d in DOC_TYPES if d["required"]]
# Any one of these satisfies the mandatory bank-proof requirement for payment transfer.
BANK_PROOF_DOCS = ["cancelled_cheque", "bank_statement", "bank_proof"]
BANK_FIELDS = ["bank_account_name", "bank_account_number", "bank_ifsc"]
TERMINATION_REASONS = ["vendor_request", "buddilio_decision", "compliance", "fraud", "safety",
                       "repeated_cancellation", "poor_service", "non_payment", "breach",
                       "business_closure", "other"]
MATERIAL_FIELDS = ["commission_type", "commission_value", "vendor_net_rate", "pricing_floor",
                   "platform_fee_percent", "platform_fee_fixed", "settlement_cycle",
                   "cancellation_policy", "refund_responsibility"]


def money(v, currency="INR") -> str:
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "SGD": "S$"}.get(currency, currency + " ")
    return f"{sym}{float(v or 0):,.2f}"


def commission_label(s: dict) -> str:
    t = s.get("commission_type", "percentage")
    if t == "percentage":
        return f"{float(s.get('commission_value') or 0):g}%"
    if t == "fixed":
        return f"{money(s.get('commission_value'), s.get('currency', 'INR'))} per transaction"
    return (f"{float(s.get('commission_value') or 0):g}% + "
            f"{money(s.get('commission_fixed'), s.get('currency', 'INR'))}")


def platform_fee_label(s: dict) -> str:
    parts = []
    if float(s.get("platform_fee_percent") or 0) > 0:
        parts.append(f"{float(s['platform_fee_percent']):g}%")
    if float(s.get("platform_fee_fixed") or 0) > 0:
        parts.append(money(s["platform_fee_fixed"], s.get("currency", "INR")))
    return " + ".join(parts) or "None"


# ---------------- pricing engine ----------------
def calculate_price(schedule: dict, *, quantity: int = 1, dynamic_adjustment: float = 0,
                    discount: float = 0, tax_percent: float | None = None) -> dict:
    """The one place customer price and vendor settlement are worked out.

    Commission is charged on the vendor net rate. The platform fee is Buddilio's own charge on top and
    never eats into the vendor's settlement, which is floored at the pricing floor.
    """
    cur = schedule.get("currency", "INR")
    qty = max(int(quantity or 1), 1)
    net = round(float(schedule.get("vendor_net_rate") or 0) * qty, 2)
    floor = round(float(schedule.get("pricing_floor") or 0) * qty, 2)

    ctype = schedule.get("commission_type", "percentage")
    cval = float(schedule.get("commission_value") or 0)
    if ctype == "percentage":
        commission = net * cval / 100
    elif ctype == "fixed":
        commission = cval * qty
    else:
        commission = net * cval / 100 + float(schedule.get("commission_fixed") or 0) * qty
    commission = round(commission, 2)

    dyn = round(float(dynamic_adjustment or 0), 2) if schedule.get("dynamic_pricing_enabled") else 0.0
    disc = round(float(discount or 0), 2)
    base = round(net + commission + dyn - disc, 2)
    fee = round(base * float(schedule.get("platform_fee_percent") or 0) / 100
                + float(schedule.get("platform_fee_fixed") or 0), 2)
    tax_pct = float(schedule.get("tax_percent") if tax_percent is None else tax_percent or 0)
    tax = round((base + fee) * tax_pct / 100, 2)
    customer_price = round(base + fee + tax, 2)

    # The vendor is paid their net rate, never below the floor, less any discount they fund.
    vendor_share = 1.0 if schedule.get("discount_funding") == "vendor" else (
        0.5 if schedule.get("discount_funding") == "shared" else 0.0)
    settlement = round(max(net - disc * vendor_share, floor), 2)
    return {"currency": cur, "quantity": qty, "vendor_net_rate": net, "pricing_floor": floor,
            "commission_type": ctype, "commission_value": cval, "commission": commission,
            "dynamic_adjustment": dyn, "discount": disc, "platform_fee": fee,
            "tax_percent": tax_pct, "tax": tax, "customer_price": customer_price,
            "vendor_settlement": settlement, "buddilio_earning": round(commission + fee, 2),
            "commercial_schedule_id": str(schedule.get("id") or schedule.get("_id") or ""),
            "commercial_schedule_version": schedule.get("version", 1)}


def resolve_commission(*, service: dict | None, vendor: dict | None, category: dict | None,
                       global_percent: float) -> dict:
    """Most specific rule wins: service → vendor → category → platform default."""
    for source, doc in (("service", service), ("vendor", vendor), ("category", category)):
        if doc and doc.get("commission_value") not in (None, ""):
            return {"source": source, "commission_type": doc.get("commission_type", "percentage"),
                    "commission_value": float(doc["commission_value"]),
                    "commission_fixed": float(doc.get("commission_fixed") or 0)}
    return {"source": "global", "commission_type": "percentage",
            "commission_value": float(global_percent or 0), "commission_fixed": 0.0}


# ---------------- agreement text ----------------
def commercial_rows(s: dict) -> list[tuple[str, str]]:
    cur = s.get("currency", "INR")
    return [
        ("Vendor service", s.get("service_name") or "All listed services"),
        ("Vendor net rate", money(s.get("vendor_net_rate"), cur)),
        ("Pricing floor", money(s.get("pricing_floor"), cur)),
        ("Buddilio commission", commission_label(s)),
        ("Customer platform fee", platform_fee_label(s)),
        ("Dynamic pricing", "Enabled" if s.get("dynamic_pricing_enabled") else "Disabled"),
        ("Promotional discount", money(s.get("promotion_discount"), cur)
         + f" · funded by {DISCOUNT_FUNDING.get(s.get('discount_funding', 'buddilio'), 'Buddilio')}"),
        ("Settlement cycle", s.get("settlement_cycle", "T+7")),
        ("Cancellation policy", s.get("cancellation_policy") or "As published on the listing"),
        ("Refund responsibility", REFUND_RESPONSIBILITY.get(s.get("refund_responsibility", "vendor"), "Vendor")),
        ("Payment processing charges", s.get("payment_processing") or "Borne by Buddilio"),
        ("Rate policy", RATE_POLICIES.get(s.get("rate_policy", "none"), RATE_POLICIES["none"])),
        ("Effective from", str(s.get("effective_from", ""))[:10]),
    ]


def mask_account(number: str) -> str:
    num = (number or "").strip()
    return f"{'•' * max(len(num) - 4, 0)}{num[-4:]}" if len(num) > 4 else (num or "—")


def banking_rows(v: dict, *, mask: bool = False) -> list[tuple[str, str]]:
    acc = v.get("bank_account_number") or ""
    return [
        ("Account holder name", v.get("bank_account_name") or "—"),
        ("Bank name", v.get("bank_name") or "—"),
        ("Branch", v.get("bank_branch") or "—"),
        ("Account number", mask_account(acc) if mask else (acc or "—")),
        ("Account type", (v.get("bank_account_type") or "current").title()),
        ("IFSC", v.get("bank_ifsc") or "—"),
        ("SWIFT / BIC", v.get("bank_swift") or "—"),
        ("UPI ID", v.get("upi_id") or "—"),
    ]


def agreement_sections(vendor: dict, s: dict, entity: dict) -> list[tuple[str, list[str]]]:
    """The master agreement. Every commercial number is read from the schedule, never hard-coded."""
    cur = s.get("currency", "INR")
    v_name = vendor.get("legal_name") or vendor.get("trade_name") or "the Vendor"
    return [
        ("Parties", [
            f"This Vendor Agreement is entered into between {entity['legal_name']} "
            f"({entity['entity_type']}, MSME registration {entity['msme'] or 'not applicable'}, "
            f"notices to {entity['email']}) (\"Buddilio\") and {v_name}, trading as "
            f"{vendor.get('trade_name') or v_name}, having its registered address at "
            f"{vendor.get('registered_address') or 'the address on record'} "
            f"(PAN {vendor.get('pan') or 'on record'}; GSTIN {vendor.get('gstin') or 'not registered'}) "
            "(\"Vendor\"), acting through its authorised representative "
            f"{vendor.get('contact_person') or 'as notified'}.",
        ]),
        ("Purpose", [
            "Buddilio provides a digital platform through which customers can discover, compare, enquire "
            "about, reserve and/or purchase Vendor Services. The Vendor authorises Buddilio to list and "
            "promote its services subject to this Agreement.",
        ]),
        ("Vendor authorisation", [
            "The Vendor authorises Buddilio to list Vendor Services; display Vendor information, "
            "photographs, videos and logos; market Vendor Services; receive customer enquiries; facilitate "
            "bookings; facilitate customer payments where enabled; calculate customer-facing prices "
            "according to the agreed commercial rules; apply approved promotions; and communicate booking "
            "information to customers.",
        ]),
        ("Vendor listing", [
            "Listings are published from the information the Vendor supplies. The Vendor is responsible for "
            "keeping descriptions, inclusions, photographs, availability and inventory accurate and current.",
        ]),
        ("Commercial terms", [
            "The commercial terms applicable to this Agreement are set out in the Commercial Schedule "
            f"(version {s.get('version', 1)}) reproduced in this document. Buddilio may issue a revised "
            "Commercial Schedule in accordance with the Commercial amendments section below.",
        ]),
        ("Buddilio commission", [
            f"Buddilio's commission is {commission_label(s)} on qualifying transactions originating through "
            "the platform. Commission is calculated on the Vendor Net Rate and is retained by Buddilio from "
            "amounts collected from customers.",
        ]),
        ("Vendor net rate", [
            f"The Vendor Net Rate is {money(s.get('vendor_net_rate'), cur)}. This is the amount the Vendor is "
            "contractually entitled to receive for a completed qualifying transaction, subject to applicable "
            "refunds, cancellations, chargebacks, taxes, agreed deductions, payment processing adjustments "
            "and other contractually permitted deductions.",
        ]),
        ("Pricing floor", [
            f"The Pricing Floor for the Vendor Service is {money(s.get('pricing_floor'), cur)}. The pricing "
            "engine will not calculate a Vendor settlement below the Vendor Net Rate unless an expressly "
            "authorised exception applies.",
        ]),
        ("Dynamic pricing", [
            ("Dynamic pricing is enabled. Buddilio may vary the customer-facing price by date, time, day of "
             "week, weekend, holiday, season, demand, inventory, capacity, advance booking window, special "
             "event, campaign or vendor/category rule. The Vendor's contractual Net Rate remains protected "
             "in accordance with this Commercial Schedule."
             if s.get("dynamic_pricing_enabled")
             else "Dynamic pricing is disabled for this Vendor Service. The customer-facing price is derived "
                  "from the Vendor Net Rate, commission and fees set out in the Commercial Schedule."),
        ]),
        ("Promotional discounts", [
            f"Approved promotional discounts of up to {money(s.get('promotion_discount'), cur)} may be applied, "
            f"funded by {DISCOUNT_FUNDING.get(s.get('discount_funding', 'buddilio'), 'Buddilio')}. Discounts "
            "funded by Buddilio do not reduce the Vendor's settlement.",
        ]),
        ("Customer-facing pricing", [
            "Customer-facing pricing is calculated by Buddilio's centralised pricing engine from the "
            "Commercial Schedule. Mandatory charges, fees and taxes are disclosed to the customer before "
            "payment.",
        ]),
        ("Payment collection", [
            "Where payment collection is enabled, Buddilio collects customer payments as the Vendor's "
            "limited collection agent for the purpose of the booking.",
        ]),
        ("Settlement", [
            f"Settlement runs on a {s.get('settlement_cycle', 'T+7')} cycle after the qualifying transaction "
            "is completed, net of commission, platform fees where borne by the Vendor, refunds, chargebacks "
            "and permitted deductions. Statements are available in the Vendor portal.",
        ]),
        ("Banking and payment transfer details", [
            "Settlements are transferred only to the Vendor bank account recorded below: "
            + " · ".join(f"{k}: {val}" for k, val in banking_rows(vendor)) + ".",
            "The Vendor must support these details with a cancelled cheque or a recent bank statement in the "
            "name of the account holder. Buddilio may withhold settlement until that proof is verified. Any "
            "change of bank account must be notified through the Vendor portal with fresh proof and is "
            "re-verified before the next transfer.",
        ]),
        ("Taxes", [
            "Each party is responsible for its own taxes. The Vendor is responsible for all taxes applicable "
            "to its business and for issuing any invoices its customers or the law require.",
        ]),
        ("Availability", [
            "The Vendor keeps availability current and honours published availability. Repeated unavailability "
            "after confirmation may lead to suspension.",
        ]),
        ("Confirmed bookings", [
            "A confirmed booking is binding on the Vendor on the terms recorded at the time of confirmation, "
            "including the commercial snapshot stored with that booking.",
        ]),
        ("Cancellation and refunds", [
            f"Cancellation policy: {s.get('cancellation_policy') or 'as published on the listing'}. Refund "
            f"responsibility rests with "
            f"{REFUND_RESPONSIBILITY.get(s.get('refund_responsibility', 'vendor'), 'Vendor')}. Bookings retain "
            "the cancellation policy applicable when they were made.",
        ]),
        ("Customer experience", [
            "The Vendor will deal with customers professionally and safely, and will not discriminate against "
            "customers who book through Buddilio.",
        ]),
        ("Licences and compliance", [
            "The Vendor holds and maintains all licences, permits, registrations and insurance required for "
            "its services, and will provide evidence on request. Expired mandatory documents may result in "
            "listings being paused.",
        ]),
        ("Intellectual property", [
            "Each party retains its own intellectual property. The Vendor grants Buddilio a non-exclusive "
            "licence to use its name, marks and media for listing and marketing during the term.",
        ]),
        ("Customer data", [
            "Customer data shared for fulfilment may be used only to deliver the booking, and not for "
            "unrelated marketing. Both parties will comply with applicable data protection law.",
        ]),
        ("Non-circumvention", [
            "For transactions originating through Buddilio, the Vendor will not intentionally redirect "
            "customers away from the platform, cancel Buddilio bookings in order to complete the same "
            "transaction directly, provide misleading information to avoid commission, or encourage customers "
            "to bypass the platform to avoid applicable fees. This applies subject to applicable law.",
        ]),
        ("Rate policy", [
            f"Rate policy: {RATE_POLICIES.get(s.get('rate_policy', 'none'), RATE_POLICIES['none'])}. Nothing in "
            "this Agreement requires the Vendor to act contrary to applicable competition law.",
        ]),
        ("Customer complaints", [
            "The Vendor will respond to complaints routed by Buddilio without undue delay and cooperate in "
            "good faith to resolve them.",
        ]),
        ("Suspension", [
            "Buddilio may suspend listings or settlements where there is a compliance, safety, fraud or "
            "material breach concern, and will notify the Vendor of the reason.",
        ]),
        ("Confidentiality", [
            "Commercial terms, platform data and customer information are confidential and may not be "
            "disclosed except as required by law.",
        ]),
        ("Vendor representations", [
            "The Vendor represents that its information is true, that it is authorised to enter into this "
            "Agreement, and that it will comply with applicable law.",
        ]),
        ("Indemnification", [
            "The Vendor indemnifies Buddilio against claims arising from its services, its breach of this "
            "Agreement or its failure to comply with law.",
        ]),
        ("Limitation of liability", [
            "Buddilio is a platform and is not liable for the performance of Vendor Services. To the extent "
            "permitted by law, Buddilio's aggregate liability is limited to the commission it received on the "
            "transaction in question.",
        ]),
        ("Term", [
            f"This Agreement is effective from {str(s.get('effective_from', ''))[:10]} and continues "
            + (f"until {str(vendor.get('agreement_end_date'))[:10]}."
               if vendor.get("agreement_end_date") else "until terminated in accordance with its terms."),
        ]),
        ("Termination", [
            "Either party may terminate on notice as recorded in the Vendor portal. Termination does not "
            "affect confirmed bookings, accrued settlements or records Buddilio must retain.",
        ]),
        ("Commercial amendments", [
            "Buddilio may issue a revised Commercial Schedule with a stated effective date. Material changes "
            "require the Vendor's acceptance before they apply to new bookings. Confirmed bookings continue "
            "under the commercial snapshot recorded at confirmation.",
        ]),
        ("Electronic acceptance", [
            "The Vendor accepts this Agreement electronically. Acceptance is recorded with the accepting "
            "person, timestamp, IP address, device information, verification reference and a hash of the "
            "executed document. The parties agree that this electronic record is valid and admissible.",
        ]),
        ("Governing law", [
            f"This Agreement is governed by the laws of India, and the courts at {entity['jurisdiction']} have "
            "exclusive jurisdiction.",
        ]),
        ("Entire agreement", [
            "This Agreement together with the applicable Commercial Schedule is the entire agreement between "
            "the parties for the listed services.",
        ]),
        ("Vendor declaration", [
            "The Vendor confirms it has read and understood this Agreement and the Commercial Schedule, and "
            "that the person accepting is authorised to do so on the Vendor's behalf.",
        ]),
    ]


def agreement_text(vendor: dict, schedule: dict, entity: dict | None = None) -> str:
    """Plain-text rendering used for the hash and for the read-only web view fallback."""
    ent = {**ENTITY, **(entity or {})}
    out = [f"BUDDILIO VENDOR AGREEMENT — {vendor.get('agreement_number', '')} v{vendor.get('version', '1.0')}", ""]
    out.append("COMMERCIAL SCHEDULE")
    out += [f"  {k}: {v}" for k, v in commercial_rows(schedule)]
    out.append("")
    for i, (title, paras) in enumerate(agreement_sections(vendor, schedule, ent), start=1):
        out.append(f"{i}. {title.upper()}")
        out += [f"   {p}" for p in paras]
        out.append("")
    return "\n".join(out)


def document_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------- executed PDF ----------------
INK = colors.HexColor("#1A0F1E")
MUTED = colors.HexColor("#685B6D")
LINE = colors.HexColor("#EAE6EA")
ACCENT = colors.HexColor("#E81E7C")


def _p(text, size=9, colour=INK, bold=False, align=0, leading=None):
    style = ParagraphStyle(f"a{size}{bold}{align}", parent=getSampleStyleSheet()["BodyText"],
                           fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                           leading=leading or size * 1.45, textColor=colour, alignment=align)
    return Paragraph(text, style)


def agreement_pdf(agreement: dict, vendor: dict, schedule: dict, acceptance: dict | None = None,
                  entity: dict | None = None) -> bytes:
    ent = {**ENTITY, **(entity or {})}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=agreement.get("agreement_number", "Vendor agreement"), author="Buddilio")
    flow = [
        Table([[logo(16 * mm) or _p("BUDDILIO", 16, ACCENT, bold=True),
                _p(f"VENDOR AGREEMENT<br/><font size=10>{agreement.get('agreement_number', '')} · "
                   f"v{agreement.get('version', '1.0')}</font>", 8, MUTED, bold=True, align=2)]],
              colWidths=[95 * mm, 79 * mm]),
        Spacer(1, 5 * mm),
        _p(f"{ent['legal_name']} · {ent['entity_type']} · MSME {ent['msme'] or '—'} · {ent['email']}", 8.5, MUTED),
        _p(f"Vendor: {vendor.get('legal_name', '')} ({vendor.get('trade_name', '')}) · "
           f"PAN {vendor.get('pan') or '—'} · GSTIN {vendor.get('gstin') or 'not registered'}", 8.5, MUTED),
        _p(f"Status {agreement.get('status', '')} · effective {str(agreement.get('effective_date', ''))[:10]}", 8.5, MUTED),
        Spacer(1, 6 * mm),
        _p("Commercial schedule", 12, INK, bold=True),
        Spacer(1, 2 * mm),
    ]
    rows = [[_p(k, 8.5, MUTED, bold=True), _p(str(v), 8.5)] for k, v in commercial_rows(schedule)]
    table = Table(rows, colWidths=[62 * mm, 112 * mm])
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    flow += [table, Spacer(1, 6 * mm), _p("Banking details for payment transfer", 12, INK, bold=True),
             Spacer(1, 2 * mm)]
    brows = [[_p(k, 8.5, MUTED, bold=True), _p(str(val), 8.5)] for k, val in banking_rows(vendor)]
    btable = Table(brows, colWidths=[62 * mm, 112 * mm])
    btable.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    flow += [btable, Spacer(1, 2 * mm),
             _p("Supported by a cancelled cheque or recent bank statement held on file.", 7.5, MUTED),
             Spacer(1, 7 * mm)]

    for i, (title, paras) in enumerate(agreement_sections(vendor, schedule, ent), start=1):
        flow.append(_p(f"{i}. {title}", 10, INK, bold=True))
        flow.append(Spacer(1, 1.5 * mm))
        for para in paras:
            flow.append(_p(para, 8.8, MUTED))
        flow.append(Spacer(1, 3.5 * mm))

    if acceptance:
        flow += [Spacer(1, 4 * mm), _p("Electronic acceptance", 12, INK, bold=True), Spacer(1, 2 * mm)]
        arows = [("Accepted by", f"{acceptance.get('accepted_by', '')} · {acceptance.get('email', '')}"),
                 ("Method", acceptance.get("acceptance_method", "otp_email")),
                 ("Verification", acceptance.get("otp_reference", "") or acceptance.get("signature_reference", "")),
                 ("Accepted at", f"{acceptance.get('accepted_at', '')} ({acceptance.get('time_zone', 'UTC')})"),
                 ("IP address", acceptance.get("ip_address", "")),
                 ("Device", (acceptance.get("user_agent", "") or "")[:120]),
                 ("Document hash", acceptance.get("document_hash", "")),
                 ("Schedule version", str(acceptance.get("commercial_schedule_version", "")))]
        at = Table([[_p(k, 8.5, MUTED, bold=True), _p(str(v), 8.5)] for k, v in arows],
                   colWidths=[62 * mm, 112 * mm])
        at.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        flow += [at, Spacer(1, 5 * mm),
                 _p("This Agreement was accepted electronically. No wet signature is required and none is "
                    "implied. This document is a certified record of the accepted version, not a "
                    "certificate-based digital signature.", 8, MUTED)]
    else:
        flow += [Spacer(1, 4 * mm), _p("Awaiting vendor acceptance.", 9, ACCENT, bold=True)]

    flow += [Spacer(1, 6 * mm),
             _p(f"For Buddilio: {ent['signatory']}, {ent['signatory_title']} · {ent['email']}", 8.5, MUTED),
             _p("This document is subject to Buddilio's internal legal review before production reliance.",
                7.5, MUTED)]
    doc.build(flow)
    return buf.getvalue()
