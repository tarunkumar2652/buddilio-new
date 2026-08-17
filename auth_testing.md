# Buddilio — Google (Emergent-managed) auth testing notes

## How the flow works in this app
1. `GoogleButton` (in `frontend/src/pages/Auth.jsx`) sends the browser to
   `https://auth.emergentagent.com/?redirect=<window.location.origin>/dashboard`.
   The redirect URL is derived from `window.location.origin` — never hardcoded, no fallbacks.
2. Emergent returns the user to `{origin}/dashboard#session_id=<id>`.
3. `Shell()` in `App.js` checks `useLocation().hash` **during render** and renders
   `pages/AuthCallback.jsx` instead of the routes. `AuthProvider` skips its `/auth/me` check while a
   `session_id` is in the hash so there is no race.
4. `AuthCallback` exchanges the id once (`useRef` guard) via
   `POST /api/auth/google/session { session_id, referral_code }`.
5. The backend calls `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data`
   with header `X-Session-ID` (server-side only), then finds-or-creates the user and issues the app's
   normal 7-day JWT (`access_token` body + httpOnly `access_token` cookie, secure, samesite=none).
   Buddilio keeps a single session mechanism — its own JWT — for both password and Google logins.
6. New Google members get `profile_complete: false` and are routed to `/welcome`
   (`POST /api/auth/onboarding`) to supply DOB (21+ enforced server-side), city/country, interests and
   the terms/21+ confirmations. `Protected` in `App.js` keeps them on `/welcome` until that is done.

## Behaviour to verify
- Existing password account with the same email is **linked** (no duplicate user), role/referral data preserved.
- Banned/suspended accounts are rejected with 403 on the Google path (same as password login).
- Invalid/expired `session_id` → 401 "That Google sign-in link has expired." and a redirect back to `/login`.
- Referral: visiting `/register?ref=CODE` stores `localStorage['bud_ref']`; a Google sign-up then attributes
  the invite to that inviter.
- `/welcome` rejects a DOB under 21 and requires both checkboxes.
- Google accounts never have an app-managed password, so no password can be tested for them.

## Backend testing without a real Google account
Create a user + JWT directly (there is no separate session collection — auth is JWT):

```bash
cd /app/backend && python -c "
import asyncio, os, server
async def main():
    doc = {'full_name':'Test Google User','email':'test.google.user@example.com','role':'user',
           'status':'active','profile_complete':False,'auth_provider':'google','age':0,'city':'',
           'notification_prefs':{'email':True,'in_app':True},'created_at':server.iso(server.now_utc())}
    r = await server.db.users.insert_one(doc)
    print(server.create_access_token(str(r.inserted_id),doc['email'],'user'))
asyncio.run(main())"
```
Then `curl -H "Authorization: Bearer <token>" $URL/api/auth/me` and
`curl -X POST $URL/api/auth/onboarding -H 'Content-Type: application/json' -H 'Authorization: Bearer <token>' \
  -d '{"dob":"1994-05-01","city":"London","is_adult":true,"accept_terms":true}'`.

Browser: set `localStorage['bud_token']` to the token, then load `/welcome`.

Clean up: `db.users.delete_many({'email': {'$regex': '^test.google.'}})`.

## Test identities
See `/app/memory/test_credentials.md` → "Google sign-in". Google OAuth accounts have no app password.
