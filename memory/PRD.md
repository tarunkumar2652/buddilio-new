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
  `VendorAgreement.jsx`, `AgreementsAdmin.jsx`).
- Legal/policy corpus (`scripts/seed_policies.py`), footer groups, 21+ signup consents, CMS versioning.
- **2026-06-19** Admin sidebar scrolls with the page; footer duplicate "Safety Centre" removed and
  legal text made legible.
- **2026-06-19** Admin sidebar **search** + **favourites** per admin account (`/api/me/admin-nav`).
- **2026-06-19** Vendor **banking details for payment transfer** + **cancelled cheque OR bank
  statement** as mandatory proof; banking annexure in agreement text and PDF.
- **2026-06-19** Content for thin policy pages; admin **"Fill missing policy pages"**
  (`POST /api/admin/cms/seed-policies?mode=missing`) + warning banner listing missing pages;
  **dynamic sitemap** `/api/sitemap.xml` (pages, cities, published events) + robots/sitemap index.
- **2026-06-20** **Bank-change re-verification**: editing any bank field supersedes the old bank
  proof, sets `payout_hold`, notifies admins, blocks `POST /admin/payouts/{id}/pay`; cleared via
  `POST /admin/vendor-profiles/{vid}/bank-verify` only with proof uploaded AFTER the change.
- **2026-06-20** **Admin document review UI** (Vendor agreements → "Review docs"): approve/reject
  every vendor document with reason, mandatory-set summary.
- **2026-06-20** **Document expiry automation**: `expire_vendor_documents()` emails 30/7/1 days out
  (`vendor_document_expiring` template), then expires the doc, sets vendor `documents_required` and
  pauses listings. Runs from the `daily-maintenance` cron (`/api/cron/daily-maintenance`, also
  `/api/cron/vendor-doc-expiry`). Admin "expiring documents" panel + `/admin/vendor-documents/expiring`.
- **2026-06-20** **City landing pages** enriched: local hosts teaser (count, rate range, avatars) and
  experience passes alongside events, guide, FAQ, JSON-LD; hosts CTA is auth-aware.
- Verified: `/app/test_reports/iteration_37.json` — backend 60/60, frontend all flows, no blocking issues.

## Known gaps / backlog
P0
- After deploying, run Admin → Pages → "Fill missing policy pages" on buddilio.com (separate database).
P1
- Vendor gaps in `/app/memory/vendor_spec_review.md`: real payout execution/UTR, vendor commission
  invoices, TDS, per-service commercial schedules UI, renewal automation, vendor scorecard/SLA.
- Legal review of policy + agreement text by an Indian legal professional before production reliance.
P2
- `POST /api/vendor/profile` is full-replace — consider PATCH-merge.
- `expire_vendor_documents()` does an N+1 vendor lookup and caps at 1000 docs; `/admin/vendor-documents/expiring`
  caps at 200 rows with no pagination.
- Certified e-sign (currently email OTP by design). `server.py` ~7.6k lines — modularisation candidate.

## Notes
- Test credentials: `/app/memory/test_credentials.md` (login response field is `access_token`).
- CMS page body lives in `page['blocks']`; `content` is only the intro paragraph.
- Admin sidebar is intentionally non-sticky (user's choice). Max 5 platform crons — daily work is
  bundled into `daily-maintenance`.
