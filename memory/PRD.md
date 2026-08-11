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

## Backlog
**P0** — Real Razorpay keys + webhook signature verification; email delivery (Resend) for verification/receipts.
**P1** — WebSocket chat instead of polling; event group chat UI; object storage for images; event reviews/ratings; partner payout records.
**P2** — Referrals, saved searches, retention cohort analytics, multi-country locations, native app clients.

## Next tasks
1. Swap simulated gateway for live Razorpay (order create + webhook).
2. Real email/SMS notification delivery.
3. Socket-based realtime chat + event group chats.
