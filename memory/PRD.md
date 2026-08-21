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

- **2026-06-21** **Built-in captcha** (`backend/botguard.py`, `frontend/src/components/Captcha.jsx`):
  server-issued challenge (`GET /api/captcha`) + hidden honeypot (`website`) + per-IP rate limits
  (register 5/h, login 12/15min). Register always shows the check on the Confirm step; login shows it
  **progressively** after a failed/suspicious attempt. Captcha box has an error/retry state.
- **2026-06-21** **Buddilio Pass (QR voucher / m-token)** (`backend/passes.py`): every paid booking gets
  a QR + short code `BUD-XXXX-99`, printable A5 PDF voucher, listed under `/orders` → "My passes".
  Public `/verify` page checks and redeems a code — redeemable **once by anyone** (organiser, host,
  buddy); a second redeem is rejected with who/when. Passes are voided on cancellation/refund.
- **2026-06-21** **Cancellation & refunds**: tiers `CANCEL_TIERS` 30% (>7 days) / 50% (2-7 days) /
  100% (<48h) deduction; membership fees **non-refundable**. Member cancels via a styled sheet
  (`CancelBookingDialog`) showing paid / deduction / refundable and a refund-vs-credit(+10%) choice.
  Admin decides the money in **Admin → Cancellations & refunds** (`Cancellations.jsx`, wired to
  `/api/admin/cancellations` + `/settle-cancellation`). `POST /api/admin/orders/{id}/refund` now
  enforces the policy ceiling and blocks membership refunds unless `override_policy` + a reason is
  given (both audited).
- **2026-06-21** **Simulated-payment hole closed**: the public "pay" simulation that marked orders paid
  without a charge is disabled server-side and removed from checkout UI.
  Verified: `/app/test_reports/iteration_41.json` — backend 21/21, all frontend flows; the policy
  ceiling, admin cancellation screen and styled dialogs were added afterwards from its action items.

- **2026-06-21** **PayPal webhook self-setup**: `GET /api/admin/paypal/webhook` (status + webhooks
  registered on the account) and `POST /api/admin/paypal/webhook/setup` create/reuse the webhook for
  `{FRONTEND_URL}/api/webhook/paypal` and store its id in `settings.paypal_webhook_id`
  (env `PAYPAL_WEBHOOK_ID` still wins). Card lives in **Admin → Payments** (`PaypalWebhook.jsx`).
  Subscribes to 9 events (subscription activated/updated/cancelled/expired/suspended/payment-failed,
  sale + capture completed, capture refunded). Webhook handler still fails closed without an id.
  Setup must be clicked **in production** — running it in preview would register the preview URL.
- **2026-06-21** **Organiser door check-in** (`frontend/src/pages/Door.jsx`, route `/door?event=<id>`):
  camera QR scan (`html5-qrcode`) plus manual code entry, live "x of y arrived" counter and per-guest
  arrival list from `GET /api/partner/events/{id}/check-in` (organiser or `events:view` staff).
  Linked from Partner dashboard published events and from `/verify`.
- **2026-06-21** **Day-before pass reminder**: `send_pass_reminders()` in the `daily-maintenance` cron
  emails the QR + code for events starting tomorrow, once per pass (`passes.reminded`), using the new
  editable `pass_reminder` email template.
- **2026-06-21** **Door extras + reminder timing**: door list search box (name or code), `GET
  /api/partner/events/{id}/check-in.csv` CSV export with a totals row, and the pass reminder window is
  now the admin setting `pass_reminder_hours` (default 12, clamped 1-168h) instead of "the day
  before". Reminders run from the `pass-reminders` cron every 2 hours (which also carries the old
  city-openings work, keeping the 5-cron limit).
- **2026-06-21** **Walk-in door sales** (`POST /api/partner/events/{id}/walk-in`, `WalkInDialog.jsx`):
  organiser records a guest who turns up without a pass. Two routes — money collected in person
  (cash/UPI/card machine) creates a paid order (`gateway: "door"`, `collected_by_vendor: true`),
  issues the pass and checks the guest straight in; or a **PayPal link** is sent to a guest who
  already has a Buddilio account (order stays pending; pass issues on capture). Guest passes may have
  an empty `user_id` — every `pass.user_id` consumer must use `ObjectId.is_valid`.
  Door-sale money uses `door_sale_settlement()`: gross = amount collected, commission per the vendor's
  schedule, `net = -commission` (the vendor owes Buddilio, recovered from the next payout) — never
  `vendor_snapshot_hook`, which would book Buddilio as owing the vendor.
- **2026-06-21** **Doors-open nudges**: `send_doors_open_nudges()` in the hourly `pass-reminders` cron
  notifies every pass holder within an hour of the start and the organiser with the arrival count
  (once per pass, flag `doors_nudged`).
- **2026-06-21** Fixes from iteration 43: `send_pass_reminders()` can no longer be aborted by a guest
  pass (invalid ObjectId guard + per-pass try), `participant_count` increments by walk-in quantity,
  `/passes/{code}/redeem` returns 400 (not 500) when a pass has no valid booking, and walk-in orders
  use the event's currency instead of `BASE_CURRENCY`.
  Verified: `/app/test_reports/iteration_43.json` (22/22 backend, mobile door UI) plus direct
  re-checks of all four fixes.
- **2026-06-21** Fixes from iteration 42: `cancellation_deduction()` no longer 500s for past-dated
  events (tier fallback 100%), door list staff check uses `events:view` (`events:manage` never
  existed), admin cancellation/refund dialogs format money in the order's currency, member cancel
  sheet has an inline error + retry.
  Verified: `/app/test_reports/iteration_42.json` plus targeted re-checks of every fix above.

## Known gaps / backlog
P0
- After deploying, run Admin → Pages → "Fill missing policy pages" on buddilio.com (separate database).
- Create the PayPal **live webhook**: after publishing, open Admin → Payments on buddilio.com and hit
  **Connect webhook** (registers `https://buddilio.com/api/webhook/paypal` and saves the id). Until
  then renewals/cancellations are only picked up when the member returns to the site.
- Do one real low-value live PayPal purchase after deploy to confirm the end-to-end capture.
P1
- Vendor gaps in `/app/memory/vendor_spec_review.md`: TDS/withholding, per-service commercial
  schedules UI, agreement renewal automation, bank-file formats beyond the generic CSV.
- Legal review of policy + agreement text by an Indian legal professional before production reliance.
- PayPal **guest card checkout** depends on the merchant account: the user must switch on
  "PayPal account optional" in PayPal business account settings, and confirm with a live purchase.
  Subscriptions always require the payer to log into/create a PayPal account.
P2
- Register rate limit (5/h per IP) counts failed attempts too — could block shared/NAT IPs.
- UTR capture uses `window.prompt` — could become a styled dialog; no UI toggle for batching
  not-yet-due settlements (API supports `due_only:false`).
- `POST /api/vendor/profile` is full-replace; `expire_vendor_documents()` N+1 lookups;
  `/admin/vendor-documents/expiring` unpaginated.
- `server.py` ~8.7k lines and `vendor_routes.py` ~1.1k — modularisation candidates (walk-in/door/pass
  logic is the natural next module to split out).
- Platform currency is inconsistent: `BASE_CURRENCY` resolves to INR while Admin → Settings says USD
  and PayPal charges USD. Walk-in receipts now use the event's currency, the rest of the app does not.

## Notes
- Test credentials: `/app/memory/test_credentials.md` (login response field is `access_token`).
- CMS page body lives in `page['blocks']`; `content` is only the intro paragraph.
- City guide data is a free-form dict in `city_guides.data` (keys: intro, areas[[name,blurb,photo]],
  when, around, tip, venues[{name,type,area,note,url}], faqs, seo_title, seo_description).
- Admin sidebar is intentionally non-sticky. Max 5 platform crons — daily work is in
  `daily-maintenance`; the hourly `pass-reminders` cron carries pass reminders, doors-open nudges and
  city-waitlist openings.
