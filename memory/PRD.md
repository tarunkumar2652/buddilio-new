# Buddilio — Product Requirements & Build Log

## Original problem statement
Build a production-ready full-stack web app + mobile-first PWA for **Buddilio.com** — a premium social discovery and companionship platform for adults (21–50, India, Delhi NCR focus) to find people to attend parties, dining, nightlife, concerts, festivals, sports, travel and lifestyle experiences with. Must feel premium, trustworthy, safe, mobile-first and explicitly NOT a dating app. Required: public website, auth, profiles, event discovery & participation, companion discovery, chat, memberships, passes/products, partner portal, super-admin backend, payments & orders, notifications, moderation/safety, analytics, CMS, SEO, demo data.

## User choices (this session)
- Scope: Phase 1–4 core delivered first
- Payments: simulated Razorpay-ready gateway (server-side verification), no live keys
- Auth: JWT email/password **and** Emergent-managed Google login
- Stack: React (CRA) + FastAPI + MongoDB (platform constraint; APIs reusable by future native apps)
- Uploads: base64 stored on the user/event record

## Architecture
- `backend/server.py` — FastAPI, all `/api` routes, JWT (7d access token, httpOnly cookie + Bearer), bcrypt, RBAC via `require_role`, audit logging, MongoDB indexes on startup, admin seeding from env.
- `backend/seed_data.py` — demo data generator.
- `frontend/src` — React Router 7, Tailwind, shadcn primitives, sonner toasts, recharts for admin analytics. `context/AuthContext.jsx` holds session; `Protected` gates routes by role.
- Design: bone-white (#FAFAFA) + midnight navy (#0F172A), Outfit headings / Manrope body, rounded cards, glass sticky nav, mobile bottom nav.

## User personas
1. **Guest** — browses home, events, passes, membership, safety, CMS pages.
2. **Registered user** — profile, discover companions, join events, chat, buy passes/membership, orders, privacy, block/report.
3. **Premium member** — plan-based discounts auto-applied at checkout, premium badge.
4. **Event partner** — org profile, create/submit events, participants, revenue & payouts.
5. **Super admin** — full platform control and moderation authority.

## Core requirements (static)
Adults only (21+ enforced server-side); auth required for private features; partners cannot publish without admin approval; payments verified server-side only; membership derived from payment records; suspended/banned users blocked; reports enter a moderation queue; refund status tracked separately; all admin actions audit-logged.

## Implemented (June 2026)
- JWT auth: register (4-step), login, logout, /me, forgot/reset password, brute-force lockout (per-email, 5 attempts → 15 min), Google session exchange.
- Profiles: public/private views, interests, event categories, lifestyle, privacy + notification prefs, base64 photo.
- Discover: city/interest/category/age/name filters, pagination, connect, message, invite-to-event, block, report.
- Events: filters (search/city/category/price/upcoming/popular), detail page with gallery, rules, cancellation policy, participants, join/cancel/save/share/report; approval modes instant/organizer/admin.
- Partner portal: dashboard stats, event CRUD, draft → submitted → approved/published, participants, revenue & payout view.
- Commerce: membership plans, products/passes, coupons (percent/fixed, min order, members-only, usage limit, expiry), checkout with GST + member discount, simulated payment success/failure, orders, admin refunds.
- Messaging: 1:1 conversations, polling refresh (5s), read receipts, unread counts, delete, report.
- Notifications: in-app feed, unread badge, mark-all-read, prefs.
- Admin: 14 sections — overview with charts + date ranges, users, partners, events moderation, memberships/products/coupons CRUD, orders, payments, reports/moderation (dismiss/suspend/ban), CMS editor, settings, audit logs.
- Content: Safety Center, CMS-driven about/terms/privacy/refund/guidelines/contact/faq.
- SEO: dynamic titles/description/OG/canonical, robots.txt (dashboards disallowed), sitemap.xml.
- Demo data: 22 users, 17 events, 2 partners, 3 plans, 5 products, 3 coupons, memberships, orders, conversations, reports, 8 CMS pages.

## Implemented — iteration 2 (June 2026)
- **Transactional email** via Emergent-managed Resend (`backend/emailer.py`): welcome, password reset link, booking confirmation with venue/time/cancellation policy, membership activation, purchase receipt, refund notice, and 24h event reminders. Respects each user's `notification_prefs.email`; send failures are logged and never break the request.
- **Realtime chat** over WebSocket `/api/ws?token=` (`backend/realtime.py` hub): instant message delivery, typing indicators, online presence, read receipts, auto-reconnect, `ws-status` badge. Polling removed.
- **Event group chats** restricted to paid ticket holders + the organiser; created automatically on successful payment, 403 with a clear message otherwise.
- **Live Razorpay**: `/api/payments/config`, `/api/payments/razorpay/order|verify` (signature + amount + status verified server-side), `/api/payments/razorpay/webhook` (HMAC-verified, idempotent fulfilment), gateway refunds from the admin panel. Falls back to the simulated path while keys are absent.
- Shared `fulfil_order()` is now the single fulfilment path for both simulated and live payments.

## Implemented — iteration 3 (June 2026)
- **Global payments**: Stripe hosted checkout for every non-INR currency (session create → hosted page → server-side status polling + signed webhook → idempotent fulfilment). Razorpay still owns INR. Multi-currency layer: INR base with configurable FX rates (INR, USD, EUR, GBP, AED, SGD), navbar currency picker, per-order `charge_*` amounts + `fx_rate`, and optional admin `price_overrides` per plan/product that beat the auto-conversion. `/payment/success` polls until the bank confirms; `/payment/cancel` handled.
- **Object storage uploads**: `POST /api/uploads` (auth, 5MB, image types only) → Emergent object storage, served via `GET /api/files/{path}` with immutable cache headers. Used by registration, profile, partner event covers and admin product images; base64 storage removed.
- **Event reviews**: confirmed attendees only, after the event ends, one per member, updates event + partner ratings, "Top rated" sort, ratings on cards/detail, dashboard "rate your recent experiences" prompt.
- **Partner payouts**: hourly job marks finished events complete and creates one ledger row per event 48h later (15% platform fee, unique index on `event_id` so it can't duplicate). Partner sees pending/settled ledger + member rating; admin Payouts tab filters, runs settlement on demand, and marks paid with a UTR reference (audited + partner notified).

## Implemented — iteration 4 (June 2026)
- **Installable PWA**: `public/manifest.json` (standalone, navy/bone theme, 192+512 `any` and `maskable` icons generated from the Buddilio monogram, app shortcuts for Events / Discover / Messages), `public/sw.js` service worker (network-first navigations + same-origin assets, cache-first for images and `/api/files/*`, never caches other `/api` calls, versioned cache cleanup), branded `public/offline.html` fallback, iOS + Android meta tags in `index.html`, registration via `src/lib/pwa.js` from `index.js`, and a dismissible `InstallPrompt` (native `beforeinstallprompt` on Android/desktop, "Share → Add to Home Screen" hint on iOS, dismissal snoozed 30 days).
- **Review moderation**: reviews now carry `status` (published/hidden), `flag_count` and `reply`. Members can flag a review from the event page (`POST /api/reviews/{id}/report`, one report per member, own reviews excluded); admin gets a **Reviews** tab with Flagged / Published / Hidden / All filters, reporter reasons, and Hide / Restore / Delete (`GET /api/admin/reviews`, `POST /api/admin/reviews/{id}/moderate`) — hidden reviews disappear from public listings and event/partner ratings are recomputed via `recompute_ratings()`. Admin overview shows a "Flagged reviews" stat.
- **Organiser replies**: partners get a **Reviews** tab (`GET /api/partner/reviews`) with average / count / awaiting-reply stats and a public reply editor (`POST /api/reviews/{id}/reply`, own events only — 403 otherwise). Replies render under the review on the event page and notify the reviewer.
- Admin sub-tab strip now shows a scroll affordance on mobile; `seed_past_events.py` seeds one organiser reply and one flagged review so both queues are demoable after a reseed.

## Implemented — iteration 5 (June 2026): push, referrals, review highlights
- **Web push notifications** (standards-based VAPID, no third-party SaaS): `backend/push.py` (pywebpush, prunes
  404/410 subscriptions), endpoints `GET /api/push/config`, `POST /api/push/subscribe|unsubscribe|test`,
  `sw.js` push + notificationclick handlers that deep-link into the app, `src/lib/push.js` and a `PushToggle`
  on /profile (iOS gets an "add to Home Screen first" hint). `notify()` fans out to push for `message` and
  `reminder` types, respecting `notification_prefs.push` — i.e. new direct messages and the 24h event reminder.
- **Referral invites + wallet credit**: every member gets a referral code (`/api/me/referrals`,
  `/api/referrals/{code}`), signup accepts `referral_code` (inviter banner on /register?ref=CODE), the inviter
  earns ₹250 base-currency credit the moment the invitee's first booking is paid (`award_referral` inside
  `fulfil_order`), and credit is auto-applied at the next checkout (`use_credit`, `credit_applied`,
  ledger in `db.credits`, consumed only on successful payment). New `/referrals` page + dashboard card.
- **Review highlights**: `GET /api/events` returns `top_review {rating, comment, user_name}` (hidden/moderated
  reviews excluded) and event cards render the quote with stars.

## Implemented — iteration 5b (June 2026): global launch
- **12 countries / 27 cities** registry in `server.py` (`COUNTRIES`, `country_for_city`, `with_country`):
  India, UAE, Singapore, UK, USA, Canada, Australia, Germany, Spain, France, Thailand, Japan.
- **10 currencies** (INR, USD, EUR, GBP, AED, SGD, CAD, AUD, THB, JPY) with `BASE_CURRENCY` env; the frontend
  auto-detects the visitor's currency from locale/timezone and remembers the choice.
- **Per-country tax**: `tax_for(currency, fallback, country_code)` → GST 18% India, VAT 5% UAE, GST 9% Singapore,
  VAT 20% UK, Sales tax 8.875% US, HST 13% Canada, GST 10% Australia, VAT 19/21/20% DE/ES/FR, VAT 7% Thailand,
  Consumption tax 10% Japan. Orders store `tax_label` + `tax_percent`; the checkout UI shows them.
- **Country filters** on events, discover, passes; country selects on signup, profile and the partner event form
  (city list follows the country, profile city change re-derives the country).
- **Global content**: 8 international events with city imagery, 6 international members, globalised products,
  CMS pages, safety/emergency guidance, footer/hero/FAQ copy, locale-aware dates and `Intl` money formatting.
  Migration script `backend/globalize.py`; `seed_data.py` produces the same shape on a fresh seed.

## Implemented — iteration 6 (June 2026): brand identity
- Adopted the user's chosen logo (gradient heart with two facing profiles + italic "Buddilio" wordmark +
  tagline **"Your Vibe, Your Buddy"**). Assets extracted from the supplied collage into
  `public/brand/mark.png` (transparent heart), `public/brand/lockup.png` and regenerated PWA icons.
- **New palette**: plum ink `#2A0836`, blush white `#FDF8FB`, brand coral `#FF9A62` → magenta `#E81E7C` →
  violet `#6B34CD`, plum `#52146F`. Applied app-wide by overriding Tailwind's `slate` scale with plum-tinted
  neutrals plus named `brand-*` tokens; gradient is reserved for primary CTAs, the mark and thin accents.
- **Redesigned header**: gradient top rule, glass sticky bar, logo lockup with tagline, animated gradient
  nav underlines, currency picker, gradient "Join Buddilio" CTA, mobile menu and brand-magenta bottom nav.
- **Redesigned footer**: plum panel with aurora + grain, reversed logo, "Live in 27 cities · 12 countries" chip,
  three link columns, social buttons and an animated city marquee.
- Hero refresh (tagline chip, gradient headline, gradient CTA), branded offline page and install prompt.
- Verified by testing agent iteration 6: 19 routes swept, zero UI bugs, zero console errors, 100% of scope.

## Implemented — iteration 7 (June 2026): city SEO pages, leaderboard, local pricing
- **Real social profiles** in the footer: Instagram `/buddilio`, Facebook `/Buddilio/`, X `/buddilio_`
  (LinkedIn/YouTube placeholders removed).
- **City pages for SEO**: `GET /api/cities` (27 cities × events/members counts) and `GET /api/cities/{slug}`
  (hero image, upcoming events, categories, member faces, top review quotes, local currency + tax + emergency
  number, nearby cities). Frontend `/cities` index grouped by country and `/city/:slug` landing pages with
  per-city `<title>`/meta description/canonical + `CollectionPage` JSON-LD. Cities with no events show an email
  waitlist (`POST /api/cities/{slug}/waitlist`, unique per city+email). `sitemap.xml` lists `/cities` and all 27
  `/city/*` URLs; the footer city marquee and an Explore → Cities link feed internal links.
- **Monthly referral leaderboard**: `GET /api/referrals/leaderboard?month=YYYY-MM` ranks rewarded invites for the
  month (top 10), returns each inviter as *First L.* only, their city, invites, credit earned and lifetime badge
  (Starter 1 → Connector 3 → Ambassador 5 → Legend 10). `/referrals` renders the board with crown/trophy/medal
  ranks, your own row highlighted, a "you are #N" summary with next-badge progress and a 3-month picker.
  `backend/seed_referrals.py` seeds a demo ladder (6/4/3/2/1 invites).
- **Organiser local pricing**: `EventIn.price_currency`; `price_event()` stores the organiser's exact amount in
  `price_input` + `price_overrides[currency]` and the converted base amount in `price`, so locals pay the typed
  figure (AED 300 → AED 315 with 5% VAT) while other currencies auto-convert. Partner form has a currency select
  that defaults to the event country's currency (`meta.countries[].primary_city|currency`); event cards and detail
  use `fmtOf()` so an exact local price always beats the FX conversion, with a "Priced by the organiser in AED"
  note when viewing in another currency. `backend/localize_prices.py` migrated all 23 priced events to their own
  city currency (AED 285 Dubai, GBP 90 London, JPY 7,500 Tokyo, THB 700 Bangkok…).
- Fixed a pre-existing mobile header overflow (390px guests: currency picker + Log in moved into the mobile menu,
  compact "Join" CTA) — `/`, `/events`, `/cities`, `/city/*` now have zero horizontal scroll.
- Verified: `backend/tests/test_iteration7.py` 9/9 and the full suite 107 passed / 2 skipped; testing agent
  iteration 7 frontend sweep (all city/leaderboard/pricing/social flows) plus a follow-up self-test of the fixes.

## Implemented — iteration 8 (June 2026): city guides, leaderboard prize, waitlist emails
- **Editorial city guides** (`backend/city_guides.py`): a hand-written guide for all 27 cities — intro
  paragraph, 3–4 named neighbourhoods with what each is for, when the city goes out, how to get around and a
  local tip. Served inside `GET /api/cities/{slug}` as `guide` and rendered on `/city/:slug` as an "Where to go
  out in {city}" section. Each city page also renders 5 city-specific FAQs (`city-faq-*`) and emits both
  `CollectionPage` and `FAQPage` JSON-LD so the answers can win rich results.
- **Monthly leaderboard prize**: `award_monthly_prize()` finds the previous month's top inviter, books them the
  highest-value active pass as a ₹0 paid order (`gateway: leaderboard_prize`, unique index on `prizes.month`, so
  it can never double-award), notifies the winner by email + in-app and tells the runners-up who won.
  `GET /api/referrals/leaderboard` now returns `prize` and `champion`, rendered as a plum "July 2026 champion"
  card on `/referrals`. Driven by the platform cron `monthly-prize` (`0 3 1 * *`).
- **City waitlist emails**: `city_waitlist` rows carry `notified_at`; `notify_city_waitlist(city)` emails everyone
  waiting the moment that city has a published event — triggered immediately when an admin approves the first
  event in a city (`/api/admin/events/{id}/moderate`) and swept daily by the `city-openings` cron (`0 9 * * *`).
  One email per address, ever. Signing up for an already-live city now says so instead of promising an email.
- **Platform crons** in `.emergent/crons.yml` → `POST /api/cron/monthly-prize` and `POST /api/cron/city-openings`,
  both guarded by `WEBHOOK_CRON_SECRET` (constant-time compare, 401 otherwise) and both ack immediately and do
  the work in a background task.
- Verified: `backend/tests/test_iteration8.py` 6/6 (all 27 guides present and city-specific, cron auth, prize
  idempotency + free-pass order + notifications, champion payload, waitlist email gating) plus a UI pass on
  `/city/london`, `/city/tokyo` (mobile) and the `/referrals` champion card.

## Implemented — iteration 9 (June 2026): guide photography, Gulf calendar, public leaderboard
- **Per-neighbourhood photography**: `AREA_PHOTOS` in `backend/city_guides.py` maps every city to real
  Unsplash photo IDs (served at `w=900`), merged into each area by `guide_for()` so the payload is
  `[name, blurb, photo]`. Neighbourhood cards on `/city/:slug` now lead with a lazy-loaded image that scales on
  hover. All 27 cities carry exactly 4 neighbourhoods with 4 distinct photos (Gurugram, Noida, Hyderabad, Pune,
  Manchester, Austin and Melbourne each gained a 4th area in this pass).
- **Fuller Gulf calendar** (`backend/seed_gulf_events.py`, idempotent): 5 new Dubai nights (Marina yacht
  sundowner, Alserkal gallery hop, DIFC rooftop jazz, padel + poolside brunch, Old Dubai food walk) and 4 Abu
  Dhabi nights (desert camp dinner, Louvre late, Corniche sunrise ride, Yas race night) — all published, priced
  in **AED** with the local-pricing fields, with covers. Plus 4 Gulf members so the faces strip and member counts
  look real. Dubai now has 6 events / 3 members, Abu Dhabi 4 / 2, across 5 categories.
- **Public leaderboard**: `GET /api/referrals/leaderboard` now uses `optional_user` — guests get the ranking,
  the champion card and the prize label, but `me` is `null` and no row is flagged as theirs. The board moved to
  `frontend/src/components/Leaderboard.jsx` and is rendered both inside `/referrals` and on a new public
  `/leaderboard` page (SEO copy, how-it-works trio, join CTA, footer link under Explore). Names stay shortened to
  first name + last initial and the payload exposes no contact details.
- Verified: `backend/tests/test_iteration9.py` 6/6 (photo coverage + real HTTP 200 image check, Gulf counts and
  AED pricing, guest vs signed-in leaderboard payloads) plus UI checks on `/city/dubai`, `/city/abu-dhabi`
  (mobile) and `/leaderboard`.

## Deployment readiness (iteration 10, June 2026)
Deployment agent verdict: **PASS — no blockers**, after these fixes:
- `CORS_ORIGINS="*"` in `backend/.env` (was pinned to the preview host, which would have broken the live domain).
- Removed 11 N+1 query patterns. A shared `load_many(collection, ids, fields)` helper does one `$in` fetch keyed by
  string id, now used by `/me/events`, `/partner/events/{id}/participants`, `/events/{id}` participants, `/events`
  top_review, `/discover` membership, `/referrals/leaderboard`, `/conversations`, `/conversations/{cid}/messages`,
  `/admin/reviews`, `/admin/payouts`, `/cities/{slug}` quotes and `reminder_loop()`. Per-row `count_documents`
  calls for leaderboard lifetime badges and conversation unread counts became single `$group` aggregations.
- Added an explicit server-side `.limit(N)` to all 57 `find(...).to_list(N)` cursors (paginated
  `.skip().limit()` cursors and aggregation pipelines deliberately left alone).
- Fixed a real bug this exposed: `/cities/{slug}` only looked at `published` events when picking review quotes,
  but reviewed events are `completed`, so the quotes section on every city page was permanently empty. It now
  reads `status in [published, completed]` and Delhi/Gurugram show real member quotes.
- `seed_referrals.py` now clears the awarded prize *order* alongside the `prizes` row, so re-seeding then
  re-awarding can't leave a duplicate free-pass order.
- Added `backend/tests/conftest.py` — a session-scoped autouse fixture purging the `TEST_*` events/users the
  suites create (one had leaked a published TEST event onto the public Delhi city page). Added `/app/.dockerignore`.
- Verified: full backend suite **132 passed / 2 skipped** (serial), clean `yarn build`, and a testing-agent
  regression pass over all 11 rewritten endpoints reporting zero backend and zero UI issues.
- Known dev-only noise: a hydration warning from the visual-editor instrumentation (not app code); the backend
  suite intermittently drops 1–2 tests to connection resets when run with 2 xdist workers — all pass serially.

## Backlog
**P0** — Add real `RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET` to flip INR checkout live; claim a Stripe account for
live international payments; register both webhook URLs. Verify Resend delivery to a real inbox (only
`delivered@resend.dev` works in this sandbox). Confirm the Google sign-in flow end-to-end (never user-verified).
**P1** — Live FX rate feed instead of static rates; Razorpay Route / Stripe Connect for automatic partner
transfers; saved searches with alerts; admin UI for prize history and city waitlists; grow the calendar in the
cities that are still empty (Melbourne, Vancouver, Manchester and the other 11 with zero events).
**P2** — Retention cohorts, native app clients, splitting `server.py` into routers, silencing the
visual-editor dev hydration warning.

## Next tasks
1. User acceptance pass on mobile: install the PWA, turn on phone alerts, run a referral + checkout end to end.
2. Supply Razorpay keys + webhook secret to go live (code complete, tested in simulation).
3. Decide whether the leaderboard and city guides should be visible to guests (both are member-gated / public
   respectively today) and whether the monthly prize should scale with invite count.
