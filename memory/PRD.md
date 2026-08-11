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

## Backlog
**P0** — Add real `RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET` to flip INR checkout live; claim a Stripe account for live international payments; register both webhook URLs. Verify Resend delivery to a real inbox (only `delivered@resend.dev` works in this sandbox). Confirm the Google sign-in flow end-to-end (code exists, never user-verified).
**P1** — Live FX rate feed instead of static rates; Razorpay Route / Stripe Connect for automatic partner transfers; web push notifications on top of the new service worker; referrals & invite links.
**P2** — Saved searches with alerts, retention cohorts, multi-country locations, native app clients, splitting `server.py` into routers.

## Next tasks
1. User acceptance pass on mobile: install the PWA from the preview URL, then check reviews/moderation, chat and checkout inside the installed app.
2. Supply Razorpay keys + webhook secret to go live (code complete and tested in simulation).
3. Web push notifications (service worker is now in place) for new messages and event reminders.

