# Agent learnings — Buddilio

## Tooling
- **Never issue multiple `search_replace` calls against the SAME file inside one parallel batch.** They race and
  silently drop edits (the tool reports success for all of them). It happened three times:
  `server.py` lost `RegisterIn.country`, `Dashboard.jsx` lost the `Gift` lucide import, `seed_data.py` lost the
  product-city + seo_description changes. Symptoms were a 500 on `/api/auth/register`
  (`'RegisterIn' object has no attribute 'country'`) and a blank `/dashboard`.
  Batch across *different* files only; for several edits to one file, use one `create_file` overwrite or a single
  python patch script.
- `python3 -m pytest` in `/app/backend` needs `REACT_APP_BACKEND_URL` exported, otherwise 6 collection errors.
- `urllib.request` against the preview URL is blocked without a browser-ish `User-Agent`; always set one.
- Screenshot tool ignores `page.set_viewport_size` for the final capture width — trust `data-testid` counts /
  `scrollWidth` assertions for mobile checks, or let the testing agent do responsive checks.

## Environment / data
- Demo state must stay clean: earlier runs left users `test_*`, events `TEST *` and a review whose body was
  literally "TEST outsider". Sweep `users(email ^test_|^repro_|^reftest_|^dup_)`, `events(title ^TEST)` and
  pending orders after every test run.
- `tarunkumar2652@gmail.com` is the real owner's signup — never delete it during cleanup.
- Resend only delivers to `delivered@resend.dev` in this sandbox; `@example.com` is rejected (422) by the provider.
- Stripe: the claimable sandbox is unavailable for India (`country_not_supported: IN`) — use the platform test key.

## Design system (post-rebrand, June 2026)
- Brand comes from the user's logo: coral `#FF9A62` → magenta `#E81E7C` → violet `#6B34CD`, plum `#52146F`,
  ink `#2A0836`, blush white `#FDF8FB`. Tagline: “Your Vibe, Your Buddy”.
- The whole app was rebranded by overriding Tailwind's `slate` scale with plum-tinted neutrals in
  `tailwind.config.js` — so existing `bg-slate-900` / `text-slate-500` classes rebrand automatically.
  Prefer the named `brand-*` tokens for new work (`bg-brand-ink`, `text-brand-magenta`).
- Gradient is reserved for primary CTAs, the logo mark and thin accents — never as a big background wash.
- Logo assets: `/public/brand/mark.png` (transparent heart), `/public/brand/lockup.png` (full lockup),
  regenerated PWA icons in `/public/icons/`. They were extracted from the user's collage with PIL flood-fill
  (corner flood fill → alpha) at 4x then downscaled; the naive "make white transparent" approach punched holes
  in the two face silhouettes inside the heart.
