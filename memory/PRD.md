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

## Implemented — iteration 11 (June 2026): Emergent-managed Google sign-in
- **Google sign-in** wired to the Emergent-managed OAuth flow: `GoogleButton` (in `pages/Auth.jsx`, used on
  both `/login` and `/register`) sends the browser to `https://auth.emergentagent.com/?redirect=` +
  `window.location.origin + "/dashboard"` (derived from the browser, never hardcoded). The return hash is
  detected **during render** in `Shell()` via `useLocation().hash` and handed to `pages/AuthCallback.jsx`,
  which exchanges the `session_id` once (`useRef` guard). `AuthProvider` skips its `/auth/me` check while a
  `session_id` is in the hash, so there is no race.
- **Backend** `POST /api/auth/google/session` now: validates the session server-side at
  `demobackend.emergentagent.com/auth/v1/env/oauth/session-data` (X-Session-ID), 401s on an expired link and
  502s if the provider is unreachable, **links** an existing account by email (sets `google_linked`,
  `google_id`, `email_verified`, backfills the photo) while preserving role/referral data, blocks
  banned/suspended accounts like password login does, and for new members creates a global profile
  (no more hardcoded "Delhi NCR"), a referral code, the welcome email + in-app notification, and
  `profile_complete: false`. Buddilio keeps one session mechanism — its own 7-day JWT.
- **Onboarding gate**: new `POST /api/auth/onboarding` enforces the 21+ rule server-side (DOB, `is_adult`,
  `accept_terms`, city required) and derives country/country_code from the city. New `/welcome` page collects
  DOB, gender, country/city, mobile, bio, photo, interests, categories and lifestyle; `Protected` keeps any
  user with `profile_complete === false` on `/welcome` until it is submitted. Existing password users are
  untouched (the field is absent, not `false`).
- **Referrals survive Google**: `/register?ref=CODE` stores `localStorage['bud_ref']`, which `AuthCallback`
  passes as `referral_code`, so a Google sign-up still credits the inviter.
- Flow + how to test without a real Google account documented in `/app/auth_testing.md`.
- Verified: `backend/tests/test_iteration11.py` **15/15**, clean `yarn build`, and testing-agent iteration 11
  (`/app/test_reports/iteration_11.json`) — zero backend, UI and integration issues, including password-login
  regressions (admin → `/admin`, member → `/dashboard`, neither sent to `/welcome`).
- Not verified: a real end-to-end Google round trip (no Google account available in this environment).
  Preview only — a redeploy is needed for buddilio.com.

## Implemented — iteration 12 (June 2026): Buddy AI concierge (ChatGPT)
- **Buddy AI** — a member-facing concierge chat on `/ai` running **OpenAI `gpt-5.4`** through the Emergent
  universal LLM key (`EMERGENT_LLM_KEY`, already in `backend/.env`; `AI_MODEL` overrides the model).
- `backend/ai.py` holds the persona and guardrails: Buddy may only recommend events that are in the context
  block, must link them as `[Title](/events/<id>)`, quotes the organiser's local price verbatim, always steers
  to public venues, never shares another member's contact details, never invents refunds/discounts, and
  declines paid-companionship framing. Also builds the member profile block (city, interests, membership,
  wallet credit) and the starter prompts.
- `backend/server.py` → `GET /api/ai/config` (enabled flag, model, suggestions, `used_today`/`daily_cap`),
  `GET /api/ai/history?session_id=`, `POST /api/ai/concierge` streaming **SSE** (`data: {"delta": …}` →
  `data: {"done": true}`, `X-Accel-Buffering: no`). Context = up to 45 upcoming **published** events, the
  member's own city first. History lives in `db.ai_messages` (indexed on user+session+time), replayed into
  `LlmChat(initial_messages=…)` — the library never owns the transcript. Abandoned turns (client disconnected
  mid-stream) are filtered out of both the replay and the history response. Cap: **30 questions per member per
  rolling 24h**, plus a 1000-character message limit.
- `frontend/src/pages/Concierge.jsx` reads the stream with `fetch` + `ReadableStream` (Authorization header
  needed, so no EventSource), renders `[label](/path)` links as router links and `**bold**`, shows suggestion
  chips on a fresh thread, a thinking placeholder, a live streaming bubble, "New chat" (rotates
  `localStorage['bud_ai_session']`) and a remaining-questions footnote. Entry points: gradient
  **Ask Buddy AI** button on the dashboard, `nav-ai` pill in the desktop header, `mnav-ai` in the mobile menu.
- Verified: `backend/tests/test_iteration12_ai.py` **15/15** and testing-agent iteration 12
  (`/app/test_reports/iteration_12.json`) — zero backend/UI issues, including cross-member session isolation,
  the three guardrail prompts, real-event link resolution, multi-turn recall, reload replay and new-chat.
- Cost note: every question spends Universal Key balance (Profile → Manage plan → Universal Key → Add balance).

## Implemented — iteration 13 (June 2026): guest concierge + site-wide AI chat widget
- **Guest concierge on the homepage** (`components/GuestConcierge.jsx`, above the Featured row): a visitor gets
  **one free question** answered by Buddy from the live event data, then the panel locks into the answer plus a
  "Join Buddilio free" invite. The question/answer is kept in `localStorage['bud_guest_ai_qa']`, so it survives
  a reload and is shared with the floating widget.
- **Site-wide AI chat widget** (`components/AiChatWidget.jsx`, mounted in `App.js`, hidden on `/ai`): floating
  "Ask Buddy" bubble on every page. Guests get the one-shot answer + join CTA; members get the full concierge
  in the **same session as `/ai`** (`localStorage['bud_ai_session']`), so a chat started in the widget continues
  on the page and vice-versa, with an "Open the full Buddy AI page" link.
- **Answers support questions without a human**: `ai_help_block()` injects the CMS policy pages (FAQ, refund,
  community guidelines, safety, about — cached 10 minutes) into both system prompts, and the persona tells Buddy
  to settle refunds/memberships/safety/booking questions itself and only hand off to
  [Contact us](/p/contact) when something needs a look inside an account.
- **Backend**: `GET /api/ai/guest/config` and `POST /api/ai/guest` (no auth, no history, 500-char limit,
  25 answers per IP per rolling 24h, each answer logged to `db.ai_guest_asks`). SSE shape identical to the
  member endpoint. Shared frontend SSE reader lives in `lib/aiStream.js`; the markdown renderer moved to
  `components/Shared.jsx` as `RichText` and is reused by the page, the homepage section and the widget.
- Verified: `backend/tests/test_iteration13_guest_ai.py` **10/10** and testing-agent iteration 13
  (`/app/test_reports/iteration_13.json`) — zero backend/UI issues, including the shared guest lock, widget on
  five routes, member↔page session sharing, CMS-sourced refund answer and 390px/1920px layout regression.

## Implemented — iteration 14 (June 2026): "Picked for you by Buddy"
- `GET /api/ai/picks` (`?refresh=1`) asks gpt-5.4 for up to **3 upcoming events** for the signed-in member and a
  one-line reason each, returned as strict JSON (non-streaming `send_message`, tolerant parsing, `[]` on
  failure). Candidates come from `ai_event_rows()` minus anything they've already joined (max 12); the prompt
  keeps picks inside the member's own country, mixes categories, and forbids internal wording in the copy.
- Results are cached per member in `db.ai_picks` (unique on `user_id`) for **6 hours**; `?refresh=1` regenerates
  but is throttled to one call a minute per member. `ai_hydrate_picks()` re-reads the events at serve time, so a
  pick that gets unpublished or starts before the member returns simply disappears.
- Dashboard row `components/AiPicks.jsx` (above "Your upcoming events"): skeletons while Buddy thinks, then
  three event cards each with the personalised "why" chip, a Refresh button and an "Ask Buddy for more" link.
- Verified: `backend/tests/test_iteration14_ai_picks.py` **10/10** and testing-agent iteration 14
  (`/app/test_reports/iteration_14.json`) — zero backend/UI issues, covering auth, geography, joined-event
  exclusion, per-member isolation, cache/refresh semantics, the unpublish guard and dashboard regression.

## Implemented — iteration 15 (June 2026): companion matches on the event page
- `GET /api/events/{id}/ai-companions` (`?refresh=1`, throttled 1/min) suggests **up to 3 members to message
  about that specific event**, each with a one-line reason. Candidate pool: confirmed attendees first, then
  same-city members sharing an interest or the event's category (max 12). Self, the organiser, blocked members
  and private profiles are excluded when building the pool **and re-checked at serve time** by `hydrate()`, so a
  later block or privacy change takes effect immediately even on a warm cache. Cached 6h in `db.ai_matches`
  (unique on `user_id` + `event_id`).
- `MATCH_SYSTEM` in `ai.py` forbids anything romantic or appearance-based — reasons must name the real overlap
  ("you both like live music, and he's in Dubai") — and shares the JSON parser with the dashboard picks.
- `components/CompanionMatches.jsx` renders under the event's details for signed-in members on upcoming events
  only (hidden for guests and finished events): avatar, first name, city, an "Already going" badge, the reason
  and a **Message** button that opens the conversation with a pre-filled invite linking the event.
- Verified: `backend/tests/test_iteration15_ai_companions.py` **11/11** and testing-agent iteration 15
  (`/app/test_reports/iteration_15.json`) — zero UI issues; the one minor finding (unstable `generated_at` on a
  cache miss) is fixed for both matches and picks.

## Implemented — iteration 16 (June 2026): file & media storage, completed
- Emergent object storage was already wired for 5MB images; this round brings it fully in line with the playbook
  and turns it into real product features.
- **Backend**: `POST /api/uploads/file` (images 5MB; PDF/CSV/TXT/MP4/WEBM/MOV/MP3/M4A 10MB),
  **chunked upload** `POST /api/uploads/chunk/init|part|complete` for files up to **25MB** (3MB parts,
  `db.upload_sessions` with a 1h TTL, `db.upload_parts`, `received` recounted from parts so retried chunks don't
  inflate it), `GET /api/me/files`, and `DELETE /api/uploads?path=` (soft delete — storage has no delete API, so
  `GET /api/files/{path}` refuses `is_deleted` rows; path must sit under `buddilio/uploads/`). Every upload is
  registered in `db.files` with owner, original filename, content type and size.
- **Chat attachments**: `MessageIn.attachment_path` — the sender must own a live `db.files` row, body may be
  empty, the conversation preview reads "Sent a photo"/"Sent a file", and the attachment rides the existing
  WebSocket push. Images render inline in the thread, other files as a download chip with name + size.
- **Partner event galleries**: `components/GalleryUpload.jsx` on the event form — multi-select, per-file
  progress, remove — feeding the gallery strip already present on the event detail page.
- **Frontend**: `lib/uploads.js` `uploadFile()` transparently switches to the chunked path above 4MB and reports
  progress.
- Verified: `backend/tests/test_iteration16_media.py` **12/12** and testing-agent iteration 16
  (`/app/test_reports/iteration_16.json`). Their findings are all fixed: the multi-select gallery closure bug
  (now confirmed adding 3 photos in one dialog), the chunk retry counter, the delete path guard and the 5MB
  helper text.

## Implemented — iteration 17 (June 2026): Vendor Console (separate back-office app)
- The user asked for native iOS/Android apps **and** a separate back-office app where someone can register and
  create vendors. Native apps are the platform's own web-to-mobile (Expo) conversion, which **the user triggers
  from the preview toggle** — nothing in this codebase to do. The back office is built here.
- **New `manager` role**: anyone can request access at `/console` (`POST /api/console/register`) and is created
  with `status: "pending"`. They can sign in and look around, but every write is blocked by the
  `active_manager` dependency until an admin approves them (Admin → **Console access** tab →
  `PATCH /api/admin/managers/{id}` approve/suspend/reject, with email + in-app notification on approval).
- **Vendor management** (`/api/console/...`): `summary`, `vendors` (search by name/email/org/city with per-vendor
  event/published/seats stats in two queries), `vendors/{id}` (detail + recent events), `POST vendors`
  (creates a `partner` account stamped with `managed_by`, then emails a 7-day set-password link so the vendor
  owns their own credentials), `PATCH vendors/{id}` (rename, city, suspend/reactivate, verified badge) and
  `POST vendors/{id}/invite` to resend. Ownership is enforced with a **404** for other managers' vendors;
  admins see everything, including legacy partners with no `managed_by`.
- **Its own app surface**: `Shell()` in `App.js` renders `pages/Console.jsx` for any `/console` path — dark
  layout, own login/registration, no member navbar, footer or Buddy widget, "Main site" link back. A member who
  signs in there is rejected and logged straight back out.
- Verified: `backend/tests/test_iteration17_console.py` **30/30 serial** and testing-agent iteration 17
  (`/app/test_reports/iteration_17.json`) — zero critical issues, zero UI bugs. Their four findings are fixed:
  the intermittent 500 on vendor create (no re-read after insert + email failure no longer loses the account),
  email format validation on registration, a 400 for an unknown vendor status, and clearing the stale member
  token when a member tries the console login.
- Test manager: `ops.manager@buddilio.com` / `Console@123` (already approved).

## Implemented — iteration 18 (June 2026): invites, payouts view, AI copy helper, activity log
- **Vendor invite links**: `POST|GET /api/console/invites`, `DELETE /api/console/invites/{id}` — a manager sends
  an emailed link (14-day token in `db.vendor_invites`, statuses pending/accepted/revoked; the link is only
  returned while pending). The vendor completes signup themselves at **`/vendor-signup?token=`**
  (`GET /api/vendor-invite/{token}`, `POST .../accept`): details, photo, password, then a documents step backed
  by `PUT /api/partner/documents` (max 10, must be `/api/files/...` URLs) and straight into their partner
  dashboard, already signed in. Documents show in the console vendor detail.
- **Console payouts** `GET /api/console/payouts`: per-payout rows (vendor, event, orders, gross, fee %, net,
  status) plus totals for owed / paid / gross / fees, scoped to the manager's own vendors (admins see all).
  New **Vendors | Invites | Payouts** tabs in the console.
- **Partner copy helper** `POST /api/partner/ai-draft` + `components/CopyHelper.jsx` at the top of the event
  form: bullets in, and gpt-5.4 returns a title, 2-paragraph description, enforceable rules (always including
  "21+, valid ID at entry") and 3 highlights, previewed before "Use this draft" fills the form. 20 drafts per
  organiser per day, with identical notes inside 5 minutes reusing the last draft for free.
- **Manager activity log** `GET /api/admin/vendor-activity`: readable audit of who invited, created, updated or
  suspended which vendor, and every console approval, under Admin → Console access.
- Verified: `backend/tests/test_iteration18_invites.py` **31/31 serial** and testing-agent iteration 18
  (`/app/test_reports/iteration_18.json`). Their HIGH finding — the freshly invited vendor landing on `/partner`
  logged out because `VendorSignup` discarded the returned token — is fixed and the full
  signup → documents → dashboard → event form flow was re-verified live. Also fixed: invite email validation,
  a 400 instead of silently dropping the 11th document, name/mobile length caps, no link for used/revoked
  invites, and the AI draft dedupe.

## Iteration 19 — vendor verification, Monday payout reminders, event photo wall (June 2026)
- **Vendor Verification Queue** (Admin → Verification): `GET /api/admin/verifications?status=pending|verified|rejected|all`
  and `POST /api/admin/verifications/{vid}` with `action: approve|reject|reset` + optional note. Approve sets
  `verified: true` / `verification_status: verified`, notifies + emails the vendor, and writes a
  `vendor.verify_*` audit entry. Approving a vendor with no documents is a 400; non-admins get 403.
  `GET /api/events/{id}` now returns `partner_verified`, and the event page shows a
  `host-verified-badge` next to “Hosted by”. UI: `frontend/src/components/Verifications.jsx`.
- **Weekly payout reminders**: `POST /api/cron/payout-reminders` (cron-secret guarded, acks immediately) →
  `send_payout_reminders()` emails each active manager the pending payouts owed to their vendors, with a total.
  Idempotent per `(manager_id, ISO week)` via `db.payout_reminders`; managers with no vendors or nothing pending
  are skipped. Registered in `.emergent/crons.yml` as `payout-reminders` `30 3 * * 1` (Monday 09:00 IST).
- **Event photo wall**: `db.event_photos` + `GET/POST /api/events/{id}/photos` and
  `DELETE /api/events/{id}/photos/{pid}`. Public read; posting needs a **confirmed** attendee and the event to
  have **started** (during or after is fine), max **10 photos per member per event**, `/api/files/...` urls only.
  Uploader, event organiser and admin can delete. UI: `frontend/src/components/PhotoWall.jsx` on the event page.
- Verified: `backend/tests/test_iteration19_verify_photos.py` **13/13** and testing-agent iteration 19
  (`/app/test_reports/iteration_19.json`) — no bugs; frontend testids, mobile 390px and all admin tabs re-checked.
  Demo state restored (Skyline Sessions stays `pending` with 1 document so the queue is never empty).

## Iteration 20 — photo moderation, verified-host filter, reminder preview (June 2026)
- **Photo wall moderation**: members flag a photo they don't own via `POST /api/events/{eid}/photos/{pid}/report`
  (idempotent per reporter, 400 on your own photo, writes a `db.reports` row with `target_type: "photo"`).
  Admin → **Photo wall** tab (`GET /api/admin/photos?status=reported|hidden|all`,
  `POST /api/admin/photos/{pid}` `{action: hide|restore|delete|dismiss, note, warn}`): hiding/deleting with
  `warn: true` increments `users.warnings`, notifies + emails the poster with the reason, and audits `photo.*`.
  Hidden photos disappear from the public wall for everyone but admins.
  UI: `frontend/src/components/PhotoModeration.jsx`, report button in `PhotoWall.jsx`.
- **Verified organisers only filter**: `GET /api/events?verified_only=true` restricts to hosts with
  `verified: true`, and every event item now carries `partner_verified`. Events page has an
  `events-verified-only` toggle and cards show a “Verified host” badge.
- **Payout reminder preview**: `GET /api/console/payout-reminder` (manager/admin) returns the exact subject,
  intro, per-vendor lines, total, `schedule`, `next_send_at` (next Monday 03:30 UTC) and
  `already_sent_this_week`. Shared `payout_digest()` now backs both the cron and the preview, so the console
  can never drift from the email. Rendered at the top of the console Payouts tab.
- Verified: `backend/tests/test_iteration20_photo_mod_verified_payout.py` **20/20** and testing-agent
  iteration 20 (`/app/test_reports/iteration_20.json`) — no bugs; demo data restored.

## Iteration 21 — verified host landing + shareable recap card (June 2026)
- **Organiser directory & profile**: public `/hosts` (search + “verified only” toggle) and `/host/:id`
  (`GET /api/hosts`, `GET /api/hosts/{id}`) showing the verified badge, bio, upcoming events, a strip from their
  photo walls, top reviews, past events and follower count. Event hero links through via `event-host-link`.
  Nav gained an **Organisers** link. UI: `frontend/src/pages/Hosts.jsx`.
- **Follow an organiser**: `POST /api/hosts/{id}/follow` (toggle, auth required), `GET /api/me/following`,
  stored in `db.host_follows`. When an admin approves a submitted event, `notify_followers()` alerts everyone
  following that organiser.
- **Shareable recap card**: `GET /api/events/{id}/recap` (public ingredients + cached card) and
  `POST /api/events/{id}/recap` — Pillow stitches the wall's newest 4 non-hidden photos into a 1080×1350 JPEG
  with the title, city, date and attendance, stores it in object storage (registered in `db.files` so
  `/api/files/...` serves it) and caches per photo signature in `db.event_recaps`. Hidden photos are excluded.
  UI: `frontend/src/components/RecapCard.jsx` under the event photo wall, with share + download.
- Verified: `backend/tests/test_iteration21_hosts_recap.py` **14/14** and testing-agent iteration 21
  (`/app/test_reports/iteration_21.json`) — no bugs, desktop + mobile 390px, all demo data restored.

## Iteration 22 — staff roles & permissions (June 2026)
- **Model**: RBAC — 17 permissions in one catalogue, 8 role presets (6 control-centre: super admin, operations,
  finance, support, moderator, viewer; 2 console: vendor manager, console viewer) plus per-person
  `extra_permissions`. Effective set = preset ∪ extras, enforced by a single `require_perm(*keys, active=False)`
  dependency that replaced every `admin_only` / `manager_only` / `active_manager` gate.
- Accounts created before this (the seeded admin and manager) have no `staff_role` and deliberately keep their
  previous access, so nothing broke.
- **Team management** (Admin → *Team & roles*): `GET /api/admin/permissions`, `GET /api/admin/team`,
  `POST /api/admin/team` (invites by email with a 7-day set-password link), `PATCH /api/admin/team/{uid}`
  (role, extras, active/suspended). Guardrails: nobody can grant permissions they don't hold, you can't edit
  yourself or anyone whose permissions exceed yours, the last active super admin can't be suspended, and every
  change is audited (`team.invite` / `team.update`).
- `GET /api/auth/me` now returns `permissions`; Admin and Console tabs render only what the signed-in person may
  use. UI: `frontend/src/components/Team.jsx`.
- Verified: `backend/tests/test_iteration22_rbac.py` **24/24** and testing-agent iteration 22
  (`/app/test_reports/iteration_22.json`) — full per-role 200/403 matrix, console read-only vs write split,
  tab filtering, mobile 390px. No bugs; test staff accounts torn down.

## Iteration 23 — fully dynamic website (June 2026)
- **Pages CMS**: `GET/POST /api/admin/pages`, `PUT/DELETE /api/admin/pages/{id}` with slug normalisation,
  draft/published status (`Literal`), SEO fields, header/footer placement and a **block builder** —
  heading, text, richtext, image, quote, list, faq (`Question | Answer`), cta, html. Rich text/HTML blocks are
  sanitised with **bleach**; image and CTA links must be `/path`, `https://` or `mailto:`. Core pages
  (faq, refund, guidelines, safety, about) can be drafted but not deleted. Public `/p/<slug>` renders the blocks
  and drafts 404. UI: `frontend/src/components/ContentStudio.jsx` (Pages tab).
- **Site sections**: `GET /api/site-content` (public), `GET /api/admin/site-content`,
  `PUT/DELETE /api/admin/site-content/{key}` for hero, how_it_works, stats, testimonials, header nav and footer
  columns — defaults mirror the shipped copy, and reset restores them. Header/footer come from
  `frontend/src/lib/site.js` + `Layout.jsx`; the homepage hero/stats come from the `hero`/`stats` sections.
- **Profiles CRUD**: `POST /api/admin/users` (password or emailed set-password link),
  `PUT /api/admin/users/{uid}` (every profile field), `DELETE /api/admin/users/{uid}?mode=soft|hard` and
  `POST /api/admin/users/{uid}/restore`. Soft delete disables and is reversible; hard delete cascades
  participants, follows, photos, reviews, notifications and push subs. Staff accounts and role changes require
  `team:manage`; you can't delete yourself; hard-deleting an organiser with events is blocked.
- **Events CRUD for admins**: `POST /api/admin/events`, `PUT /api/admin/events/{eid}`,
  `DELETE /api/admin/events/{eid}?force=` (refuses while paid orders exist, and while people are confirmed
  unless forced). In-house events show as “Buddilio”. UI: `frontend/src/components/AdminForms.jsx`.
- **City guides**: `GET /api/admin/city-guides`, `PUT/DELETE /api/admin/city-guides/{slug}` override the
  editorial guides per city and the public city page serves the override.
- Verified: `backend/tests/test_iteration23_cms.py` **30/30** (54/54 with RBAC) and testing-agent iteration 23
  (`/app/test_reports/iteration_23.json`).
- Fixes after review: missing `useSite()` in Navbar (found by tester — would have crashed every route),
  admin `ProfileIn` renamed `AdminProfileIn`, HTML/link sanitising, page status constrained, staff-role
  demotion blocked, event delete blocked while paid orders exist, hero/stats defaults restored to the
  original launch copy.
- **Not yet editable**: transactional email templates (still in code) — next candidate.

## Iteration 24 — editable email templates (June 2026)
- **All 19 automated emails are now editable**: a single `EMAIL_TEMPLATES` registry (groups: Members, Bookings,
  Growth, Money, Organisers, Safety, Team) holds the default subject, in-email heading, body HTML and button,
  with `{{placeholders}}` for the dynamic bits. `send_tpl(key, to, values)` resolves any admin override at send
  time and every previous `send_email(wrap(...))` call site now goes through it, including `notify()` and the
  weekly payout reminder (whose console preview shares the same rendering, so the two can't drift).
- Admin → **Emails**: `GET /api/admin/email-templates`, `PUT /api/admin/email-templates/{key}`,
  `DELETE …/{key}` (reset to default) and `POST …/{key}/test` (sends the email to yourself with sample values,
  15s per-admin cooldown). Body and heading are bleach-sanitised, button links must be `{{var}}`, `/path`,
  `https://` or `mailto:`, fields are length-capped, and edits are audited with the old/new subject.
  UI: `frontend/src/components/EmailTemplates.jsx`.
- Welcome, Google welcome and password-reset sends are now fired with `asyncio.create_task` so the mail provider
  never stalls a signup or reset request.
- Verified: `backend/tests/test_iteration24_emails.py` **18/18** and testing-agent iteration 24
  (`/app/test_reports/iteration_24.json`) — no bugs; overrides proven to apply on real sends; templates reset,
  nothing left in `db.email_templates`.

## Iteration 25–26 — Paid hangouts, request fee & hidden rates (June 2026)
- **Premium-only paid hangouts** (`backend/server.py`, `frontend/src/pages/Hangouts.jsx`,
  `frontend/src/components/Companions.jsx`): any *verified* member can offer hangouts (admin approves),
  only members with an active membership can browse/book, nothing is publicly visible. Buddilio keeps **25%**
  of the agreed price, the companion gets **75%** via the existing payout ledger (no real bank settlement yet).
- **Non-refundable request fee** (default **₹100**, editable in Admin → Companions → “Request fee”, stored as
  `settings.hangout_request_fee`): charged on *every* request to stop spam. Booking starts at
  `pending_request_fee`, paying the fee moves it to `awaiting_acceptance`. The fee is never refunded and is
  excluded from the 75/25 split (`booking_refundable()` = paid_total − fee_paid).
- **Rates hidden until acceptance**: browsing and detail responses return `hourly_rate: 0`, `rate_hidden: true`
  and packages without prices; the member's own booking hides the amount until the companion accepts.
- **Acceptance names the price**: `POST /api/bookings/{id}/accept` (optional `{amount}`) or `…/counter`
  (must exceed the listed price), both capped at 3× listed. Booking goes to `payment_due` / `counter_offered`
  with `due_amount` = full agreed price.
- **Wallet auto-debit**: if the member's Buddilio credit balance covers the agreed price, acceptance confirms
  the booking instantly (`paid_from: "wallet"`); otherwise they're sent to the card checkout.
- Hangout orders are **tax-free** (person-to-person time), so the guest pays exactly the agreed amount.
- Bugs fixed from iteration 25: `payouts.event_id` unique index made partial (was 500-ing every 2nd companion
  payout), approve-after-suspend now restores `companion.enabled`, member offers capped at 3× listed.
- **Site-wide fix**: every route change now scrolls to the top (or to the `#hash` section) — `ScrollToTop`
  in `frontend/src/App.js`.
- Verified: `backend/tests/test_iteration25_hangouts.py` **22/22 passing** (run with `-n 0`) plus testing-agent
  iterations 25 & 26. Test data cleaned (0 companion bookings/payouts, fee reset to 100).

## Iteration 27 — Wallet, saved cards, ratings & free requests (June 2026)
- **Buddilio wallet** (`frontend/src/pages/Wallet.jsx`, route `/wallet`, in the member nav): top up ₹500–₹200,000
  (`POST /api/wallet/topup` → checkout `kind=wallet`, tax-free, idempotent fulfilment), see the credit ledger,
  and the balance is spent automatically the moment a companion accepts.
- **Saved card (SIMULATED vault)**: `PUT/DELETE /api/wallet/card` stores brand, last4, name, expiry and an
  `autopay` flag — never the full number. `charge_saved_card()` writes an order/payment with
  `gateway="saved_card_sim"`. `try_auto_debit()` order of preference: wallet → saved card (if autopay) →
  otherwise the booking waits at `payment_due` for a manual checkout. **No real Stripe/Razorpay card storage yet.**
- **Companion ratings**: `POST /api/bookings/{id}/rate` (member, completed bookings only, once per booking)
  stores 1–5 stars plus a private note. Only the average + count show on a companion card
  (`companion.rating`, `rating_count`); notes are admin-only via `GET /api/admin/companion-ratings`.
- **Free requests**: `settings.hangout_free_requests` (default 3, editable in Admin → Companions) gives paying
  members N fee-free hangout requests per calendar month; those bookings are created as `fee_waived: true`
  and go straight to `awaiting_acceptance`.
- Verified: `backend/tests/test_iteration27_wallet.py` **17/17** and `test_iteration25_hangouts.py` **22/22**
  (testing-agent iteration 27, run with `-n 0`). Wallet nav link added to `DEFAULT_SITE_CONTENT.nav.member`.

## Iteration 28 — Dynamic countries/cities, ID verification, auto reload, nudges & sorting (June 2026)
- **Dynamic country/city catalogue** (`backend/geo.py`, `db.countries`, `frontend/src/components/Places.jsx`,
  Admin → Countries & cities): 54 countries and ~196 cities seeded on first boot, each with its own currency,
  tax percent/label and emergency number. Admins add/edit/hide/delete countries and add or remove cities;
  `refresh_countries()` reloads the in-memory catalogue after every write so tax, currency and city dropdowns
  update instantly. Deleting a country with published events is blocked. 32 extra currencies added.
- **Member ID & address verification** (`/me/verification`, `/admin/id-verifications`,
  `components/IdVerification.jsx` on the profile, `components/IdVerifications.jsx` in Admin → ID checks):
  members pick from 11 document types (Passport, Aadhaar, PAN, driving licence, Emirates ID, utility bill,
  bank statement, rent agreement …), upload 1–4 files and submit; admin approve sets `users.verified = true`
  (which unlocks hangout hosting), reject returns a note. Verified members can re-submit updated documents.
- **Wallet auto reload** (`PUT /api/wallet/auto-reload`): when the balance falls to the member's threshold after
  a wallet-paid hangout, the saved card is charged for the configured amount and the wallet is credited.
- **Rating nudges**: `POST /api/cron/rating-nudges` (daily 10:00 IST in `.emergent/crons.yml`) reminds guests
  once about completed, unrated hangouts from the previous day.
- **Companion sorting**: `GET /api/companions?sort=rating|experience|rate|rate_desc` with a picker on /hangouts;
  invalid values now 422 via a `Literal` guard.
- Verified: `backend/tests/test_iteration28_geo_verify_autoreload.py` **32/32**, plus regressions
  `test_iteration25_hangouts.py` 22/22 and `test_iteration27_wallet.py` 17/17 — **71/71** (testing-agent
  iteration 28, run with `-n 0`).

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

## Invoices, receipts & member ledger — 18 Jun 2026 (iteration 31, 9/9 green)
- `backend/invoices.py`: ReportLab PDF renderer + one template per money-in kind
  (membership, product, event, companion, wallet, travel, provider_fee) with its own heading,
  line-item wording and footnote. Renders "INVOICE" when pending, "RECEIPT" when paid.
- Endpoints: `GET /api/orders/{oid}/invoice` (JSON), `GET /api/orders/{oid}/invoice.pdf`
  (application/pdf, filename INV-… or RCP-…), `GET /api/me/ledger`.
  Authorization: buyer only, or staff with `finance:view` (403 otherwise, 400 bad id, 404 missing).
- Frontend: `components/MyLedger.jsx` → `/ledger` page (Payments & ledger: totals, payments table with
  View + Invoice/Receipt PDF per row, credits, payouts) and a compact 5-row section on the Dashboard.
  `pages/Invoice.jsx` now shows the per-kind heading + footnote and a real Download PDF button.
  Orders page and the admin Ledger tab both gained per-row PDF buttons.
- Known nuance: `totals.paid` sums in base currency while rows show their own order currency (labelled).
- Backlog (P2): email the receipt PDF automatically after payment; split refunded amounts out of totals.
