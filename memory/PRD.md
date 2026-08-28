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
- **2026-06-21** **USD rebase** (user: convert prices so real-world price stays the same; keep the
  header switcher as display-only). `BASE_CURRENCY=USD`, `DEFAULT_CURRENCIES` rebased so USD = 1.0 and
  INR = 83.33, `settings.currency/base_currency/currencies` rewritten. Catalogue prices, coupons,
  commercial schedules, the hangout fee, credits/wallet top-ups and `REFERRAL_REWARD` (now 3) were all
  divided by 83.33 via `backend/scripts/rebase_currency_usd.py` (dry-run by default, `--apply` to
  commit). **Historical orders/payments/payouts/settlements keep their original currency** — each row
  carries its own currency and rewriting them would falsify the books.
  `POST /api/checkout` now **ignores** any `currency` in the payload and always charges
  `BASE_CURRENCY`; the header/checkout picker is display-only ("Billed in USD" + an FX hint).
  Every money aggregate converts row currencies to base before summing: `admin_ledger`,
  `admin_stats`, `admin_payouts`, `vendor_routes.settlement_totals`, `/vendor/settlements`,
  `partner_door_takings` and the commission-invoice builder all return a `currency` field.
  **Rule: never sum a money column across rows without dividing by its own currency's FX rate.**
- **2026-06-21** **Door takings report** (`GET /api/partner/door-takings`, `DoorTakings.jsx` in Partner
  → Revenue & payouts): what the organiser collected at the door, commission owed vs recovered,
  walk-in guest count, and a per-sale table in each sale's own currency.
  Verified: `/app/test_reports/iteration_44/45/46/47.json` (iteration 47: 50/50 backend, all six
  fixes confirmed) plus direct curl/screenshot checks of the vendor_routes INR literals removed
  afterwards.
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
- Platform currency is USD everywhere (rebased 2026-06-21). Historical pre-rebase rows stay INR by
  design; only aggregates are converted.

## 2026-08-23 — Journal in HTML, SEO & indexing, human support chat, 4-currency display
Shipped in Preview, tested (iteration 50 retest + iteration 51). **Needs Republish to reach buddilio.com.**
- **Crawlable Journal**: `frontend/scripts/prerender.js` runs as `postbuild` on every `yarn build` and
  writes real HTML for `/blog` and every published article into `build/blog/**` (title, description,
  canonical, JSON-LD, full article text inside `#root`), plus a fresh `build/sitemap.xml` and the
  IndexNow key file. React still hydrates over it. New posts need a republish to refresh static HTML.
- **Sitemap**: category URLs now use `+` encoding (matches the UI chips → one canonical URL);
  `<loc>` values are XML-escaped; canonicals/sitemap always name the live domain, never the preview
  host (`seo_site_base()`).
- **SEO & indexing panel** (Admin → Content → SEO & indexing, `content:manage`): indexable URL list +
  group counts, IndexNow submission to Bing/Yandex/Seznam/Naver (`POST /api/admin/seo/submit`,
  refuses preview hosts), key rotation (deletes superseded key files), live site URL + Google Search
  Console token (injected into the HTML by the prerender step). Backend: `seo.py`, `db.seo_settings`.
- **Human support chat**: Ask Buddy widget → "Talk to a real person" opens a real thread
  (`POST /api/support/threads`, guests give name+email, 5 threads/hour/IP). Staff read and reply in
  Admin → People → Support inbox (`support:respond`, granted to super_admin/operations/support).
  Members get a notification, guests get an email. Backend: `support.py`, `db.support_threads`.
- **Display currencies limited to USD, INR, GBP, EUR** (`DISPLAY_CURRENCIES` in `server.py`, surfaced
  via `/api/meta`). Charging currency stays USD; organiser pricing selects follow the same four.

### Open items from iteration 51
- P2: `_write_key_file()` writes into `frontend/public`, so a rotated IndexNow key only goes live after
  a republish (serving `/{key}.txt` from FastAPI would be cleaner).
- P2: guest support rate limit keys on client IP — behind a CDN confirm the real visitor IP resolves.
- P2: `Admin.jsx` keeps `NAV` and `GROUPS` as parallel lists; a new NAV entry vanishes from the sidebar
  unless added to GROUPS (caused a HIGH bug this iteration). Derive the sidebar from one list.

## 2026-08-23 (later) — Support alerts, canned replies, Journal newsletter, logo on PDFs
Shipped in Preview, tested (iteration 52: 24 backend tests pass, all UI checks pass).
- **Support alerts**: `notify_support_staff()` pings every admin holding `support:respond` (in-app
  notification type `support` + email) on a new human chat and on each visitor follow-up.
- **Canned replies**: `db.canned_replies` + `/api/admin/support-replies` CRUD; picked from chips in the
  support inbox, placeholders `{name} {first_name} {last_booking} {my_name}` filled client-side
  (`SupportInbox.fill()`); `last_booking` comes from the member's latest order.
- **Journal newsletter**: `NewsletterSignup` on `/blog` and article pages → `db.newsletter_subs`;
  per-story **Send to subscribers** (`POST /api/admin/blog/{id}/newsletter`, refuses drafts and
  double sends unless `?force=true`); one-click unsubscribe at `/unsubscribe?t=token`.
- **Logo on PDFs**: `pdfbrand.logo()` (asset at `backend/assets/logo.png`) heads the invoice/receipt,
  commission invoice, pass/voucher and vendor agreement PDFs, plus the printable invoice page.
  Verified by rendering page 1 of each. Fixed the long-standing ₹ tofu box — non-ASCII currency
  symbols now print as the currency code ("INR 2,359.00").

### Known / accepted
- Vendor agreements already accepted keep their **stored, hash-signed** PDF, so those downloads have no
  logo by design; new generations carry it.
- Emails cannot be delivered from Preview (Resend blocks unverifiable recipients); production sends
  from the live domain.
- P2 scale: support alerts and newsletter sends loop recipients inline in the request — fine at current
  volume, should move to a background job before large lists.

## 2026-08-24 — SEO panel split per engine + IndexNow 403 root cause
- **Root cause of the Bing/IndexNow `SiteVerificationNotCompleted` 403**: the production DB held a
  rotated IndexNow key (`b1f4d2…`) while the deployed key file was the older `89c2f6….txt`, so Bing
  could not verify. Fixed: `ensure_indexnow_key()` now treats the **key file shipped in
  `frontend/public/` as the source of truth** and self-heals the DB, and `/api/admin/seo/submit`
  pre-flights `{site}/{key}.txt` and refuses with a "republish first" message instead of a raw 403.
- **Google verification**: the token is now injected into the built `index.html` by the prerender step
  (the SPA shell is what every URL serves), and `/api/admin/seo` reports `gsc_live` by fetching the
  live site. Pasting a token still requires a republish before Search Console can verify. Saved tokens
  now also strip a leading `google-site-verification=`.
- **SEO panel** rebuilt as three separate sections — Google Search Console (step-by-step + URL
  inspection guidance), Bing Webmaster Tools (import-from-GSC + sitemap), IndexNow instant push with a
  live key-file status. `httpx` was missing from `server.py` imports (the live checks failed silently).
- **Open**: production still serves the SPA shell for `/blog` even though `build/sitemap.xml` shows the
  postbuild prerender ran, i.e. `build/blog/index.html` is not reaching/served by the deployed static
  host. Root-level real files (`offline.html`, `*.txt`) ARE served. Re-check after the next republish;
  if it persists, either Emergent Support must allow directory-index files or accept JS-rendered
  indexing (Google and Bing both render).

## 2026-08-24 — Journal readers report
- `db.blog_reads` daily buckets per slug written on each article view, with the traffic source derived
  from the referrer only (search / social / referral / direct — no cookies, no tracking IDs).
- `GET /api/admin/blog/insights?days=7|30|90` returns this period vs the previous one, per-story
  changes, source split and a daily series; rendered by `BlogInsights.jsx` at the top of
  Admin → Journal (blog). Verified on preview (desktop + 390px).
- **Still pending user action**: production had not been republished at the time of writing (prod DB
  still held the stale IndexNow key `b1f4d2…`, no Google tag in the served HTML, `/blog` still the SPA
  shell). Re-check all three right after the next republish.

## 2026-08-24 (evening) — production verification after republish
Checked https://buddilio.com directly:
- ✅ Prerendered **Journal index HTML is live** (`/blog` serves the real title, canonical and JSON-LD).
- ⚠️ **Production has zero published Journal stories** (`/api/blog` → `total: 0`) — blog content lives per
  environment and does NOT copy from preview. Hence no article pages and no article URLs in the live
  sitemap. The user must write/publish stories in the production admin.
- ⚠️ Google token was stored WITH its `google-site-verification=` prefix, so the injected meta tag was
  invalid. `seo_settings()` now strips the prefix on read as well as on save; needs one more republish.
- ⚠️ The deployed static host returns `index.html` (HTTP 200) for missing paths, so a rotated IndexNow
  key looked "present" but was not. Rotation now **stages** the key (`pending_key`) and only promotes it
  once `{site}/{key}.txt` really serves it; `ensure_indexnow_key()` falls back to the shipped key file.
  The live key file `89c2f6….txt` is confirmed reachable on production.
- SEO panel now warns when the site has no published stories and when a key rotation is pending.

## 2026-08-24 — Journal export / import
- `GET /api/admin/blog/export` returns every story in `blog.PostIn` shape; `POST /api/admin/blog/import`
  (`{posts, overwrite}`) upserts by slug, validates each item and reports added/updated/skipped.
- Admin → Journal (blog) has **Export stories** (downloads a JSON file) and **Import stories** (file
  picker, overwrite on). Intended use: export on preview, import on the live site, since blog content
  does not travel between environments.

## 2026-08-24 — Journal author profiles
- `db.blog_authors` (+ `blog.AuthorIn/author_doc/author_card/author_jsonld`); posts carry `author_slug`.
- Public: `GET /api/blog-authors`, `GET /api/blog-authors/{slug}` (author + their published stories +
  Person JSON-LD); page at `/blog/author/:slug` (`BlogAuthor.jsx`), byline with photo + author card on
  every article, author URLs in the sitemap and prerendered into static HTML.
- Admin: `BlogAuthors.jsx` inside Admin → Journal (blog) — add/edit/delete writers with photo, role,
  bio, city and social links; renaming a writer updates the byline on all their stories; deleting one
  leaves the stories published. The post editor has a **Writer** picker that fills the byline.
- Verified in preview: byline link, author card, author page with story grid, sitemap entry and the
  prerendered `build/blog/author/<slug>/index.html`.

## 2026-08-24 — Writer invites & house ads
**Writer invites** (`staff_role: writer`, permission `content:draft`)
- Invite from Admin → Journal → Writers → "Invite to write": creates/links an admin-scope account with
  only the **My stories** tab and emails the existing `team_invite` (password-reset) link. Author doc
  stores `user_id` + `email`.
- `/api/writer/posts*` — list/get/create/update own drafts, `POST .../submit` (min 80 words) sets
  `in_review` and notifies every editor with `content:manage`.
- Editors: `POST /api/admin/blog/{id}/approve` and `/request-changes` (note goes back to the writer,
  status `changes_requested`). Post statuses now: draft | in_review | changes_requested | published.
- Writers cannot publish, cannot edit a live story, cannot touch anyone else's story (verified 403s).

**Ads** (`ads.py`, `db.ads`, `db.ad_settings`)
- 7 placements: home, events, journal, article, membership, passes, footer strip. Per-ad placements,
  cities, priority (1-10), start/end dates, active/paused, view+click counters and CTR.
- `GET /api/ads?placement=&city=` serves a house banner first, then the AdSense fallback
  (`network_enabled`, `network_client`, `network_slots`), and hides everything for plans listed in
  `hide_for_plans` (user chose to hide only from Premium Annual). Empty slot renders nothing.
- `POST /api/ads/{id}/click` counts the click then redirects client-side.
- Admin → Content → **Ads** (`AdsAdmin.jsx`); `AdSlot.jsx` is the render component.
- **Advertise with us** page at `/advertise` (footer link) → `POST /api/advertise` creates a support
  thread and pings support staff, so enquiries land in the Support inbox.

### Ads addendum — pasted ad code (2026-08-24)
- Admin section renamed **"Google AdSense & other ad code"** with 3-step instructions, a **site-wide code**
  box (Auto ads / verification, served by `GET /api/ads/head`, injected by `AdsHead.jsx`) and a
  **per-slot code textarea** for each of the 7 placements. Publisher-id + unit-id fields moved into an
  "Advanced" details block.
- `ads.AdConfigIn` gained `code_slots` and `head_code`; `/api/ads` returns `network.code` when a snippet
  exists for that slot, else the client/slot pair, else nothing.
- `AdSlot.jsx` re-creates `<script>` tags from the pasted snippet (innerHTML never executes scripts) —
  this is what makes a copied AdSense block actually run. Verified with a probe snippet on /events.
- Caught and fixed a missing `AdSlot` import in `Events.jsx` that white-screened the events page.

### Publish button in Admin (2026-08-23, iteration 54)
- User asked for a Publish button inside the site instead of waiting for a redeploy.
- `GET /api/admin/publish` → `{available, site_url, last_publish}`; `POST /api/admin/publish` runs
  `node frontend/scripts/prerender.js`, which re-injects the AdSense `<head>` code, the Google
  verification tag, the IndexNow key file, a fresh sitemap and the static Journal/author HTML.
  Permission: `content:manage`. Stores `seo_settings.last_publish`, writes an audit entry.
- `PublishButton.jsx` (testids `publish-block/publish-btn/publish-note`) sits in Admin → Ads
  (head-code card) and Admin → SEO & indexing. Preview's dev server doesn't serve `build/`, so the
  button reports success there but only changes raw HTML on the deployed site.

### Hide paid companionship switch (2026-08-23, iteration 54)
- Admin → Settings → `hide_hangouts` checkbox (testid `setting-hide_hangouts`), `content:manage`.
- Backend `hangouts_hidden()` / `hangouts_open()` gate `premium_member` (covers `/companions`,
  `/companions/{id}`, bookings) plus `GET/POST /me/companion` → 404 "Hangouts aren't available on
  Buddilio right now." `GET /api/site-content` now returns `hangouts_enabled`.
- Frontend: `navFor()`/`footerGroups()` drop `/hangouts` links and relabel any "Companions" footer
  link to "Members" while off; `HangoutsOn` guard in `App.js` renders a "Not available" page
  (testid `hangouts-off`) for all four `/hangouts` routes. Admin data (hosts, bookings, ratings,
  fees) stays untouched — nothing is deleted. Default: OFF (hangouts visible).
- Iteration 54 also fixed: unknown ad placement keys returned 500 → now a 422 via a
  `field_validator` on `ads.AdIn.placements`.

### Brand positioning refresh (2026-08-28)
- New line: **"Leave the virtual. Live the social."** with hero **"Meet real people. / Share real
  experiences."** Voice rule: online connection isn't enough — never anti-internet.
- Changed: `DEFAULT_SITE_CONTENT["hero"]` (tagline/headline/highlight/subtext), `Home.jsx` hero
  fallbacks + `<SEO>` + "Real people. Real plans." section, `Layout.jsx` logo strapline
  ("Live the social") and footer blurb (keeps "Your Vibe, Your Buddy" as the opening phrase),
  `public/index.html` title/description/og:title, Membership intro in `Commerce.jsx`,
  About page copy (`scripts/seed_policies.py` default + preview `cms_pages.about.content`).
- Production About page text lives in its own DB, so it must be re-saved in Admin → Pages there
  (or reseeded); hero/nav/footer defaults ship with the code.

### Rebrand support pieces (2026-08-28)
- Journal launch story "Leave the virtual. Live the social." — seeded via
  `backend/scripts/seed_rebrand_story.py` (idempotent by slug, featured, published). Preview DB only;
  production needs the Journal export/import in Admin or a re-run of the script there.
- Social share card at `frontend/public/brand/og-cover.jpg` (1200x630, generated). `index.html` now
  carries og:description/og:image/og:image dimensions + full twitter:card set, and `SEO` in
  `Shared.jsx` sets og/twitter description + image per page (accepts an `image` prop override).
- `ProofStrip.jsx` — scrollable "last week on Buddilio" photo strip directly under the Home hero
  (testids `proof-strip`, `proof-shot-{i}`); stock imagery, swap for real member photos later.

## Notes
- Test credentials: `/app/memory/test_credentials.md` (login response field is `access_token`).
- CMS page body lives in `page['blocks']`; `content` is only the intro paragraph.
- City guide data is a free-form dict in `city_guides.data` (keys: intro, areas[[name,blurb,photo]],
  when, around, tip, venues[{name,type,area,note,url}], faqs, seo_title, seo_description).
- Admin sidebar is intentionally non-sticky. Max 5 platform crons — daily work is in
  `daily-maintenance`; the hourly `pass-reminders` cron carries pass reminders, doors-open nudges and
  city-waitlist openings.
