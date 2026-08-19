# Vendor agreement & commercial module — spec review (June 2026)

Reviewed: `backend/agreements.py`, `backend/vendor_routes.py`, `frontend/src/pages/VendorAgreement.jsx`,
`frontend/src/components/AgreementsAdmin.jsx`.

## Built and working
- Vendor onboarding for all three kinds (organiser, travel provider, paid companion) with statuses
  draft → submitted → under_review → documents_required → approved / rejected / suspended / terminated.
- Legal + business profile: legal name, trade name, PAN, GSTIN, registration details, addresses,
  licences, service category/description, city/country, contract end date, auto-renew, notice days.
- Banking for payment transfer (NEW): account holder, bank, branch, account number, account type,
  IFSC, SWIFT/BIC, UPI ID — printed as an annexure in the agreement PDF and shown in admin.
- Documents with review workflow. Mandatory: PAN, address proof and **one** bank proof —
  cancelled cheque or bank statement (NEW). Vendor cannot be approved until all are approved.
- Commercial schedule separate from the master agreement, versioned, never overwritten:
  net rate, pricing floor, commission (percentage/fixed/hybrid), separate platform charge %, fixed
  add-on, tax %, dynamic pricing flag, promotional discount + funding, settlement cycle,
  cancellation policy, refund responsibility, payment-processing charge, rate policy, effective dates.
- Agreement generation with agreement number + version (v1.0, amendments v1.1 …), frozen text and
  sha256 document hash.
- Email OTP acceptance with four confirmations, attempt limit, 10-minute expiry, immutable acceptance
  record (person, email, IP, device, timestamp, OTP reference, hash) and a frozen executed PDF.
- Amendments create a new schedule version; material changes require fresh acceptance; future-dated
  schedules wait as `scheduled` and are promoted automatically.
- Centralised pricing engine (`calculate_price`) is the single source for customer price and vendor
  settlement; `/api/pricing/quote` is access-controlled (vendor own only, staff any).
- Commercial snapshot frozen per booking + settlement row created with a due date from the cycle.
- Suspension / termination with reason codes; history closed, never deleted.
- Audit trail per agreement/schedule; admin dashboard (vendors + agreements) and vendor portal
  (profile, documents, agreement, terms, settlements, history).

## Gaps still open (not built)
1. **Bank account change re-verification flow** — the agreement now requires fresh proof on change,
   but there is no explicit "bank details changed → re-verify before next payout" state machine.
2. **Document expiry automation** — `expires_on` is stored, but nothing pauses listings or emails the
   vendor when a mandatory document expires.
3. **Settlement payout execution** — settlements are an internal ledger only. No bank remittance,
   UTR capture, payout file/NEFT export or reconciliation. Marked internal, not real transfers.
4. **Vendor-side invoices/credit notes** for commission and platform fees (GST-style documents).
5. **TDS / withholding** and 194-O style deductions are not modelled.
6. **Service-level commercial schedules per listing** are supported by `service_id` but there is no
   admin UI to set per-service terms — only vendor-level.
7. **Certified e-sign** (Aadhaar/DSC) is intentionally not integrated; acceptance is email OTP.
8. **Renewal automation** — `auto_renew` and `renewal_notice_days` are stored but no cron issues
   renewal notices or auto-extends the term.
9. **Vendor scorecard / SLA** (cancellation rate, response time) driving suspension thresholds.
10. **Legal review** — all agreement text still needs sign-off by an Indian legal professional
    before production reliance (the PDF carries that disclaimer).
