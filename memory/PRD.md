# Buddilio — PRD / working memory

Preview: https://lifestyle-connect-17.preview.emergentagent.com · Production: https://buddilio.com (user deploys)

## Product
Social discovery & experiences platform for adults 21+ (explicitly NOT dating/matchmaking).
React + FastAPI + MongoDB. Members, memberships, events, experience passes, companions/hangouts,
travel crew, vendors, payments/wallet/ledger, invoices, CMS/policies, admin console, vendor portal.

Legal entity: Buddilio (firm) · signatory Manish Kumar · info@buddilio.com · MSME UDYAM-HR-05-0203611 ·
Gurugram-122505, Haryana · no GST · grievance officer Manish.

## Delivered (latest last)
- Wallet, saved cards, ratings, free requests; dynamic countries/cities; ID verification; PII masking.
- Invoice + receipt PDFs and member ledger (`invoices.py`, `MyLedger.jsx`).
- Rich HTML (bleach-sanitised) content; modern design refresh; dynamic membership plans.
- Vendor agreement & commercial management module (`agreements.py`, `vendor_routes.py`,
  `VendorAgreement.jsx`, `AgreementsAdmin.jsx`).
- Legal/policy corpus (`scripts/seed_policies.py`), footer groups, 21+ signup consents, CMS versioning.
- **2026-06-19** Sidebar scrolls with page; footer dedupe + legible legal text; sidebar **search** and
  per-admin **favourites** (`/api/me/admin-nav`); vendor **banking details** + cancelled cheque/bank
  statement proof; content for thin policy pages; **"Fill missing policy pages"** admin action +
  missing-pages banner; **dynamic sitemap** `/api/sitemap.xml`.
- **2026-06-20** **Bank-change re-verification** with payout hold; **admin document review UI**;
  **document expiry automation** (30/7/1 reminders → expire → pause listings) via `daily-maintenance`
  cron; **city landing pages** with hosts + passes.
- **2026-06-20** **Vendor payout runs**: batch due settlements per vendor, quoted bank CSV export,
  UTR capture (batch or single settlement), reconciliation KPIs, held vendors skipped
  (`/admin/vendor-payout-runs*`, `/admin/vendor-settlements*`).
- **2026-06-20** **Monthly commission invoices**: `BUD-CI-YYYY-MM-NNNN`, idempotent generation
  (manual by month + auto on the 1st via cron), PDF for admin and vendor, "GST not applicable".
- **2026-06-20** **Vendor scorecards**: 0-100 from cancel rate, rating, complaints, documents and
  holds, red/amber/green flag, flag-only (no auto-suspend).
- **2026-06-20** **City SEO guide editor**: form-based intro/areas/when/around/tip, **top venues**
  list and per-city SEO title/description, rendered on `/city/<slug>` (`city-venues`).
- Verified: `/app/test_reports/iteration_38.json` — backend 79/79, all frontend flows, no blocking issues.

- **2026-06-21** **PayPal integration** (`backend/paypal.py`): one-time payments with **guest card
  checkout** (`landing_page=BILLING`, no PayPal login needed) and **PayPal subscriptions** for
  memberships (product+plan created once per plan, cached per env). Membership page offers both
  "Pay by card — N days" and "Subscribe with PayPal (auto-renews)". Cancel-auto-renewal endpoint
  `POST /api/me/membership/cancel`. Return pages `/payments/paypal/return` and
  `/payments/paypal/subscription-return`. Webhook `/api/webhook/paypal` **fails closed** without
  `PAYPAL_WEBHOOK_ID` and re-verifies each capture with PayPal before fulfilling.
  **PayPal is in LIVE mode** (`PAYPAL_ENV=live`, USD); sandbox keys kept as `PAYPAL_SANDBOX_*`.
  Verified: `/app/backend/tests/test_iteration39_paypal.py` 28/28 plus report iteration_39.

## Known gaps / backlog
P0
- After deploying, run Admin → Pages → "Fill missing policy pages" on buddilio.com (separate database).
- Create the PayPal **live webhook** (`https://buddilio.com/api/webhook/paypal`) and set
  `PAYPAL_WEBHOOK_ID` — until then renewals/cancellations are only picked up when the member returns
  to the site, and the webhook intentionally fulfils nothing.
- Do one real low-value live PayPal purchase after deploy to confirm the end-to-end capture.
P1
- Vendor gaps in `/app/memory/vendor_spec_review.md`: TDS/withholding, per-service commercial
  schedules UI, agreement renewal automation, bank-file formats beyond the generic CSV.
- Legal review of policy + agreement text by an Indian legal professional before production reliance.
P2
- UTR capture uses `window.prompt` — could become a styled dialog; no UI toggle for batching
  not-yet-due settlements (API supports `due_only:false`).
- `POST /api/vendor/profile` is full-replace; `expire_vendor_documents()` N+1 lookups;
  `/admin/vendor-documents/expiring` unpaginated.
- `server.py` ~7.6k lines and `vendor_routes.py` ~1.1k — modularisation candidates.

## Notes
- Test credentials: `/app/memory/test_credentials.md` (login response field is `access_token`).
- CMS page body lives in `page['blocks']`; `content` is only the intro paragraph.
- City guide data is a free-form dict in `city_guides.data` (keys: intro, areas[[name,blurb,photo]],
  when, around, tip, venues[{name,type,area,note,url}], faqs, seo_title, seo_description).
- Admin sidebar is intentionally non-sticky. Max 5 platform crons — daily work is in `daily-maintenance`.
