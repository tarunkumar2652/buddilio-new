"""Iteration 50 RETEST — Journal/blog + SEO + Security & Credentials fixes.

Covers the fixes made after iteration 48/49:
  * nav/footer Journal links in DEFAULT_SITE_CONTENT
  * sitemap category URL encoding + no draft leakage
  * credentials keyholder gating + permanent masking
  * password policy / session revocation (password restored at the end)
  * user access revoke kills token
  * admin blog authoring lifecycle (draft hidden -> publish -> edit -> delete)
"""
import os
import uuid
from urllib.parse import quote

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok, r.text[:300]
    return tok


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="session")
def member_token():
    return login(*MEMBER)


# ---------------------------------------------------------------- public journal
class TestPublicJournal:
    def test_index_returns_featured_and_categories(self):
        r = requests.get(f"{API}/blog", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["items"], list) and len(d["items"]) >= 1
        assert d["featured"] and d["featured"]["slug"]
        assert "City Guides" in d["all_categories"]
        for it in d["items"]:
            assert "body" not in it

    @pytest.mark.parametrize("category", ["Nightlife", "City Guides"])
    def test_category_filter(self, category):
        r = requests.get(f"{API}/blog", params={"category": category}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        for it in r.json()["items"]:
            full = requests.get(f"{API}/blog/{it['slug']}", timeout=30).json()["post"]
            assert full["category"] == category

    def test_article_has_seo_payload(self):
        slug = requests.get(f"{API}/blog", timeout=30).json()["items"][0]["slug"]
        r = requests.get(f"{API}/blog/{slug}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["post"]["body"]
        assert d["jsonld"]["@type"] == "BlogPosting"
        assert d["jsonld"]["mainEntityOfPage"].endswith(f"/blog/{slug}")
        assert isinstance(d["related"], list)

    def test_unknown_slug_404_message(self):
        r = requests.get(f"{API}/blog/definitely-not-a-post-{uuid.uuid4().hex[:6]}", timeout=30)
        assert r.status_code == 404
        assert "isn't published" in r.json()["detail"]


# ---------------------------------------------------------------- nav / footer / sitemap
class TestNavAndSitemap:
    def test_site_content_has_journal_links(self):
        r = requests.get(f"{API}/site-content", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert any(x["to"] == "/blog" for x in d["nav"]["public"]), d["nav"]["public"]
        assert any(x["to"] == "/blog" for x in d["nav"]["member"]), d["nav"]["member"]
        footer_links = [l["to"] for g in d["footer"]["groups"] for l in g["links"]]
        assert "/blog" in footer_links, footer_links

    def test_sitemap_blog_urls_and_encoding(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=60)
        assert r.status_code == 200
        xml = r.text
        assert "<loc>" in xml and "/blog</loc>" in xml
        assert f"/blog?category={quote('City Guides')}</loc>" in xml
        # no raw spaces inside any <loc>
        import re as _re
        for loc in _re.findall(r"<loc>(.*?)</loc>", xml):
            assert " " not in loc, f"unencoded space in sitemap loc: {loc}"

    def test_sitemap_has_no_draft_posts(self, admin_token):
        rows = requests.get(f"{API}/admin/blog", headers=hdr(admin_token), timeout=30).json()["items"]
        xml = requests.get(f"{API}/sitemap.xml", timeout=60).text
        for row in rows:
            in_map = f"/blog/{row['slug']}</loc>" in xml
            if row.get("status") == "published":
                assert in_map, f"published post missing from sitemap: {row['slug']}"
            else:
                assert not in_map, f"draft leaked into sitemap: {row['slug']}"


# ---------------------------------------------------------------- credentials gating
class TestCredentialsGating:
    ENDPOINTS = [("get", "/admin/credentials"), ("get", "/admin/security/accounts")]

    def test_anonymous_blocked(self):
        for method, path in self.ENDPOINTS:
            r = getattr(requests, method)(f"{API}{path}", timeout=30)
            assert r.status_code in (401, 403), f"{path} -> {r.status_code}"

    def test_member_blocked_with_message(self, member_token):
        for method, path in self.ENDPOINTS:
            r = getattr(requests, method)(f"{API}{path}", headers=hdr(member_token), timeout=30)
            assert r.status_code == 403, f"{path} -> {r.status_code} {r.text[:150]}"
            assert r.json()["detail"] == "Only a Super admin can manage credentials."
        r = requests.put(f"{API}/admin/credentials/PAYPAL_CURRENCY",
                         headers=hdr(member_token), json={"value": "USD"}, timeout=30)
        assert r.status_code == 403

    def test_super_admin_allowed(self, admin_token):
        r = requests.get(f"{API}/admin/credentials", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["items"]) >= 15
        assert all({"name", "configured", "source"} <= set(i) for i in d["items"])


class TestCredentialMasking:
    """Save a low-risk secret, then confirm it is never readable back."""
    KEY = "VAPID_SUBJECT"
    SECRET = "mailto:qa-i50@buddilio.test"

    def test_save_then_never_readable(self, admin_token):
        h = hdr(admin_token)
        try:
            r = requests.put(f"{API}/admin/credentials/{self.KEY}", headers=h,
                             json={"value": self.SECRET}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            d = requests.get(f"{API}/admin/credentials", headers=h, timeout=30).json()
            row = next(i for i in d["items"] if i["name"] == self.KEY)
            assert row["configured"] is True
            assert row["source"] == "dashboard"
            # sensitive keys must never echo plaintext anywhere in the payload
            body = requests.get(f"{API}/admin/credentials", headers=h, timeout=30).text
            for sens in [i["name"] for i in d["items"] if i["sensitive"]]:
                live = None
                assert '"value"' not in body
                del live, sens
            assert "ciphertext" not in body and "nonce" not in body
        finally:
            requests.delete(f"{API}/admin/credentials/{self.KEY}", headers=h, timeout=30)

    def test_sensitive_previews_are_masked(self, admin_token):
        d = requests.get(f"{API}/admin/credentials", headers=hdr(admin_token), timeout=30).json()
        for row in d["items"]:
            if row["sensitive"] and row["configured"]:
                assert "•" in row["preview"], row
                assert len(row["preview"]) <= 14

    def test_unknown_key_404(self, admin_token):
        r = requests.put(f"{API}/admin/credentials/NOT_A_KEY", headers=hdr(admin_token),
                         json={"value": "x"}, timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------- access revoke
class TestAccessRevoke:
    def test_revoke_disables_account_and_token(self, admin_token):
        """Revoke on a real member account: token dies, login refused, then restored."""
        h = hdr(admin_token)
        utok = login(*MEMBER)
        me = requests.get(f"{API}/auth/me", headers=hdr(utok), timeout=30)
        assert me.status_code == 200, me.text[:200]
        uid = me.json()["id"]
        restored = False
        try:
            r = requests.post(f"{API}/admin/security/accounts/{uid}/access", headers=h,
                              json={"active": False}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            assert r.json()["status"] == "suspended"
            dead = requests.get(f"{API}/auth/me", headers=hdr(utok), timeout=30)
            assert dead.status_code in (401, 403), dead.status_code
            relog = requests.post(f"{API}/auth/login",
                                  json={"email": MEMBER[0], "password": MEMBER[1]}, timeout=30)
            assert relog.status_code == 403, f"{relog.status_code} {relog.text[:200]}"
            r = requests.post(f"{API}/admin/security/accounts/{uid}/access", headers=h,
                              json={"active": True}, timeout=30)
            assert r.status_code == 200 and r.json()["status"] == "active"
            restored = True
            assert requests.post(f"{API}/auth/login",
                                 json={"email": MEMBER[0], "password": MEMBER[1]},
                                 timeout=30).status_code == 200
        finally:
            if not restored:
                requests.post(f"{API}/admin/security/accounts/{uid}/access", headers=h,
                              json={"active": True}, timeout=30)

    def test_self_lock_rejected(self, admin_token):
        me = requests.get(f"{API}/auth/me", headers=hdr(admin_token), timeout=30).json()
        r = requests.post(f"{API}/admin/security/accounts/{me['id']}/access",
                          headers=hdr(admin_token), json={"active": False}, timeout=30)
        assert r.status_code == 400


# ---------------------------------------------------------------- admin authoring
class TestBlogAuthoring:
    def test_draft_publish_edit_delete_lifecycle(self, admin_token):
        h = hdr(admin_token)
        # member cannot author
        assert requests.get(f"{API}/admin/blog", headers=hdr(login(*MEMBER)),
                            timeout=30).status_code == 403
        payload = {"title": f"TEST_i50 Retest Story {uuid.uuid4().hex[:5]}",
                   "category": "Nightlife", "body": "<p>" + ("word " * 260) + "</p>",
                   "excerpt": "A QA retest story.", "tags": ["qa", "retest"],
                   "status": "draft"}
        created = requests.post(f"{API}/admin/blog", headers=h, json=payload, timeout=30)
        assert created.status_code == 200, created.text[:300]
        pid, slug = created.json()["id"], created.json()["slug"]
        try:
            # draft hidden publicly
            assert requests.get(f"{API}/blog/{slug}", timeout=30).status_code == 404
            assert slug not in [i["slug"] for i in requests.get(f"{API}/blog", timeout=30).json()["items"]]
            assert slug in [i["slug"] for i in
                            requests.get(f"{API}/admin/blog", headers=h, timeout=30).json()["items"]]
            # publish
            pub = requests.put(f"{API}/admin/blog/{pid}", headers=h,
                               json={**payload, "slug": slug, "status": "published"}, timeout=30)
            assert pub.status_code == 200, pub.text[:300]
            live = requests.get(f"{API}/blog/{slug}", timeout=30)
            assert live.status_code == 200, live.text[:200]
            assert live.json()["post"]["read_minutes"] >= 1
            assert slug in [i["slug"] for i in requests.get(f"{API}/blog", timeout=30).json()["items"]]
            # edit title
            new_title = payload["title"] + " (edited)"
            up = requests.put(f"{API}/admin/blog/{pid}", headers=h,
                              json={**payload, "slug": slug, "status": "published",
                                    "title": new_title}, timeout=30)
            assert up.status_code == 200
            assert requests.get(f"{API}/blog/{slug}", timeout=30).json()["post"]["title"] == new_title
            # view counter
            v1 = requests.get(f"{API}/blog/{slug}", timeout=30).json()["post"]["views"]
            v2 = requests.get(f"{API}/blog/{slug}", timeout=30).json()["post"]["views"]
            assert v2 > v1
        finally:
            d = requests.delete(f"{API}/admin/blog/{pid}", headers=h, timeout=30)
            assert d.status_code == 200, d.text[:200]
        assert requests.get(f"{API}/blog/{slug}", timeout=30).status_code == 404
        assert requests.delete(f"{API}/admin/blog/{pid}", headers=h, timeout=30).status_code == 404

    def test_invalid_payloads(self, admin_token):
        h = hdr(admin_token)
        r = requests.post(f"{API}/admin/blog", headers=h, json={"title": "ab"}, timeout=30)
        assert r.status_code == 422
        r = requests.get(f"{API}/admin/blog/64b7f9f9f9f9f9f9f9f9f9f9", headers=h, timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------- password change (runs last)
def _restore_admin_password_in_db():
    """The documented super-admin password (Admin@123, 9 chars) is REJECTED by the app's own
    10-char policy, so it can only be put back by writing the bcrypt hash directly."""
    import asyncio
    import bcrypt
    from motor.motor_asyncio import AsyncIOMotorClient
    env = dotenv_values("/app/backend/.env")

    async def _go():
        db = AsyncIOMotorClient(env["MONGO_URL"])[env["DB_NAME"]]
        await db.users.update_one(
            {"email": ADMIN[0]},
            {"$set": {"password_hash": bcrypt.hashpw(ADMIN[1].encode(), bcrypt.gensalt()).decode()}})

    asyncio.run(_go())


class TestZZSuperAdminPassword:
    NEW = "QaRetest50Pwd!"

    def test_policy_rejects_short_and_wrong_current(self):
        h = hdr(login(*ADMIN))
        r = requests.post(f"{API}/me/password", headers=h,
                          json={"current_password": ADMIN[1], "new_password": "Short1a"}, timeout=30)
        assert r.status_code == 400
        assert r.json()["detail"] == "Use between 10 and 128 characters."
        r = requests.post(f"{API}/me/password", headers=h,
                          json={"current_password": "WrongPassword1", "new_password": self.NEW},
                          timeout=30)
        assert r.status_code == 400 and "not right" in r.json()["detail"]

    def test_change_revokes_other_sessions(self):
        tok = login(*ADMIN)
        other = login(*ADMIN)          # a second, previously issued session
        try:
            r = requests.post(f"{API}/me/password", headers=hdr(tok),
                              json={"current_password": ADMIN[1], "new_password": self.NEW},
                              timeout=30)
            assert r.status_code == 200, r.text[:300]
            fresh = r.json()["access_token"]
            for dead_tok in (tok, other):
                dead = requests.get(f"{API}/auth/me", headers=hdr(dead_tok), timeout=30)
                assert dead.status_code == 401, dead.status_code
                assert dead.json()["detail"] == "Your session has ended. Please log in again."
            assert requests.get(f"{API}/auth/me", headers=hdr(fresh), timeout=30).status_code == 200
            assert requests.post(f"{API}/auth/login",
                                 json={"email": ADMIN[0], "password": ADMIN[1]},
                                 timeout=30).status_code == 401
            login(ADMIN[0], self.NEW)
            # policy blocks restoring the documented 9-char password through the API
            nt = login(ADMIN[0], self.NEW)
            back = requests.post(f"{API}/me/password", headers=hdr(nt),
                                 json={"current_password": self.NEW, "new_password": ADMIN[1]},
                                 timeout=30)
            assert back.status_code == 400
            assert back.json()["detail"] == "Use between 10 and 128 characters."
        finally:
            _restore_admin_password_in_db()
        login(*ADMIN)
