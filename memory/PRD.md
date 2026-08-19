# Buddilio — PRD / working memory

Preview: https://lifestyle-connect-17.preview.emergentagent.com · Production: https://buddilio.com (user deploys)

## Product
Social discovery & experiences platform for adults 21+ (explicitly NOT dating/matchmaking).
React + FastAPI + MongoDB. Members, memberships, events, experience passes, companions/hangouts,
travel crew, vendors, payments/wallet/ledger, invoices, CMS/policies, admin console, vendor portal.

Legal entity: Buddilio (firm) · signatory Manish Kumar · info@buddilio.com · MSME UDYAM-HR-05-0203611 ·
Gurugram-122505, Haryana · no GST · grievance officer Manish.

## Delivered (chronological, latest last)
- Wallet, saved cards, ratings, free requests; dynamic countries/cities; ID verification; PII masking.
- Invoice + receipt PDFs (ReportLab) and member ledger (`MyLedger.jsx`, `backend/invoices.py`).
- Rich HTML (bleach-sanitised) content rendering across public surfaces.
- Modern design refresh (`design_guidelines.json`) + dynamic membership plans (`PlansAdmin.jsx`).
- Vendor agreement & commercial management module (`agreements.py`, `vendor_routes.py`,
  `VendorAgreement.jsx`, `AgreementsAdmin.jsx`): onboarding, documents, versioned commercial
  schedules, agreement generation, email-OTP acceptance, executed PDF, amendments, snapshots,
  settlements, audit.
- Legal/policy corpus seeded (`scripts/seed_policies.py`), footer groups, 21+ signup consents,
  CMS versioning + policy acceptance.
- **2026-06-19** Admin sidebar scrolls with the page (no longer frozen); footer duplicate
  "Safety Centre" removed and legal text made legible.
- **2026-06-19** Admin sidebar **search** (Enter opens first match) and **favourites** pinned per
  admin account (`GET/PUT /api/me/admin-nav`).
- **2026-06-19** Vendor **banking details for payment transfer** (holder, bank, branch, account no,
  account type, IFSC, SWIFT, UPI) + **cancelled cheque OR bank statement** as the mandatory bank
  proof; banking annexure in the agreement text and PDF; shown in admin agreement detail.
- **2026-06-19** Content depth for thin pages (cookies, cities, insights, trust, grievance);
  admin action **POST /api/admin/cms/seed-policies?mode=missing** + Pages button
  "Fill missing policy pages" (never overwrites existing pages); **dynamic sitemap** at
  `/api/sitemap.xml` (pages, cities, published events), robots.txt + sitemap index updated.
- Verified by testing agent: `/app/test_reports/iteration_35.json` — backend 25/25, frontend 10/10.

## Known gaps / backlog
P0 (user-facing next)
- Production content: after redeploy, run Admin → Pages → "Fill missing policy pages" on
  buddilio.com so live footer pages get content (preview and production have separate databases).
P1
- Vendor module gaps documented in `/app/memory/vendor_spec_review.md`: bank-change re-verification
  flow, document expiry automation, real payout execution/UTR, vendor commission invoices, TDS,
  per-service commercial schedules UI, renewal automation, vendor scorecard/SLA.
- Legal review of all policy + agreement text by an Indian legal professional before production
  reliance.
P2
- Certified e-sign (currently email OTP by design).
- `server.py` is ~7.5k lines — candidate for modularisation.

## Notes
- Test credentials: `/app/memory/test_credentials.md` (login response field is `access_token`).
- CMS page body lives in `page['blocks']`; `content` is only the intro paragraph.
- Admin sidebar is intentionally non-sticky (user's choice).
