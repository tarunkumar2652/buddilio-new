"""Iteration 49 — Journal (blog) public + admin API, SEO, and iteration-48 security fixes."""
import os
import re
import time

import pytest
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")

SLUG = "the-rooftop-rule-how-to-actually-enjoy-a-night-out-with-people-you-just-met"


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def member_token():
    return login(*MEMBER)


@pytest.fixture(scope="module")
def partner_token():
    return login(*PARTNER)


# ---------------------------------------------------------------- public journal
class TestPublicJournal:
    def test_index_shape_and_no_body(self):
        r = requests.get(f"{API}/blog", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for key in ("items", "featured", "categories", "all_categories", "total"):
            assert key in d, f"missing {key}"
        assert d["items"], "no published posts returned"
        assert all("body" not in i for i in d["items"]), "listing leaks full body"
        f = d["featured"]
        assert f and f["slug"], "no featured hero"
        for i in d["items"]:
            for k in ("slug", "title", "category", "excerpt", "read_minutes", "published_at"):
                assert k in i
            assert isinstance(i["read_minutes"], int) and i["read_minutes"] >= 1

    def test_category_filter(self):
        d = requests.get(f"{API}/blog", timeout=30).json()
        cat = d["items"][0]["category"]
        r = requests.get(f"{API}/blog", params={"category": cat}, timeout=30)
        assert r.status_code == 200
        got = r.json()
        assert got["items"] and all(i["category"] == cat for i in got["items"])

    def test_empty_category_returns_no_items(self):
        r = requests.get(f"{API}/blog", params={"category": "Events"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # nothing seeded under Events
        assert d["items"] == [] and d["featured"] is None and d["total"] == 0

    def test_unknown_category_is_not_an_error(self):
        r = requests.get(f"{API}/blog", params={"category": "NotACategory"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_search_query(self):
        r = requests.get(f"{API}/blog", params={"q": "rooftop"}, timeout=30)
        assert r.status_code == 200
        slugs = [i["slug"] for i in r.json()["items"]]
        assert SLUG in slugs, slugs
        empty = requests.get(f"{API}/blog", params={"q": "zzqqxx-nothing"}, timeout=30).json()
        assert empty["items"] == []

    def test_tag_filter(self):
        post = requests.get(f"{API}/blog/{SLUG}", timeout=30).json()["post"]
        tag = post["tags"][0]
        r = requests.get(f"{API}/blog", params={"tag": tag}, timeout=30)
        assert r.status_code == 200
        assert any(i["slug"] == SLUG for i in r.json()["items"])

    def test_article_payload_and_jsonld(self):
        r = requests.get(f"{API}/blog/{SLUG}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        p = d["post"]
        assert "_id" not in p and "id" in p
        for k in ("title", "body", "cover_image", "author_name", "published_at",
                  "read_minutes", "seo_title", "seo_description", "tags"):
            assert k in p, f"post missing {k}"
        assert p["body"].strip(), "empty body"
        j = d["jsonld"]
        assert j["@type"] == "BlogPosting"
        for k in ("headline", "description", "image", "datePublished", "author",
                  "publisher", "mainEntityOfPage"):
            assert j.get(k), f"jsonld missing {k}"
        assert j["mainEntityOfPage"].endswith(f"/blog/{SLUG}")
        assert isinstance(d["related"], list) and d["related"]
        assert all(r_["slug"] != SLUG for r_ in d["related"])
        assert all("body" not in r_ for r_ in d["related"])

    def test_views_increment(self):
        before = requests.get(f"{API}/blog/{SLUG}", timeout=30).json()["post"]["views"]
        requests.get(f"{API}/blog/{SLUG}", timeout=30)
        after = requests.get(f"{API}/blog/{SLUG}", timeout=30).json()["post"]["views"]
        assert after > before, f"views did not increment ({before} -> {after})"

    def test_unknown_slug_404(self):
        r = requests.get(f"{API}/blog/no-such-story-xyz", timeout=30)
        assert r.status_code == 404
        assert "isn't published" in r.json().get("detail", "")

    def test_sitemap_includes_blog_urls(self):
        r = requests.get(f"{API}/sitemap.xml", timeout=60)
        assert r.status_code == 200
        xml = r.text
        assert "/blog<" in xml or "/blog</loc>" in xml
        for slug in [i["slug"] for i in requests.get(f"{API}/blog", timeout=30).json()["items"]]:
            assert f"/blog/{slug}</loc>" in xml, f"sitemap missing {slug}"
        assert "/blog?category=Nightlife" in xml


# ---------------------------------------------------------------- admin authoring
class TestAdminBlog:
    created = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, request):
        yield
        tok = login(*ADMIN)
        for pid in TestAdminBlog.created:
            requests.delete(f"{API}/admin/blog/{pid}", headers=hdr(tok), timeout=30)

    def test_list(self, admin_token):
        r = requests.get(f"{API}/admin/blog", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["items"], list) and d["items"]
        assert all("_id" not in i and "id" in i for i in d["items"])
        assert "Nightlife" in d["categories"]

    def test_draft_lifecycle(self, admin_token):
        body = "<p>" + ("word " * 450) + "</p>"
        payload = {"title": "TEST Journal Draft Story", "category": "Nightlife",
                   "body": body, "tags": ["test-tag"], "status": "draft",
                   "seo_title": "TEST SEO title", "seo_description": "TEST SEO description"}
        r = requests.post(f"{API}/admin/blog", headers=hdr(admin_token), json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        out = r.json()
        pid, slug = out["id"], out["slug"]
        TestAdminBlog.created.append(pid)
        assert slug == "test-journal-draft-story", slug

        got = requests.get(f"{API}/admin/blog/{pid}", headers=hdr(admin_token), timeout=30).json()
        assert got["status"] == "draft"
        assert got["read_minutes"] == 2, got["read_minutes"]      # 450 words / 220 wpm
        assert got["excerpt"], "excerpt not auto-generated"
        assert not got.get("published_at")

        # draft must not be publicly reachable
        assert requests.get(f"{API}/blog/{slug}", timeout=30).status_code == 404
        assert slug not in [i["slug"] for i in requests.get(f"{API}/blog", timeout=30).json()["items"]]

        # publish
        payload["status"] = "published"
        up = requests.put(f"{API}/admin/blog/{pid}", headers=hdr(admin_token),
                          json=payload, timeout=30)
        assert up.status_code == 200, up.text[:300]
        pub = requests.get(f"{API}/admin/blog/{pid}", headers=hdr(admin_token), timeout=30).json()
        assert pub["status"] == "published"
        assert pub["published_at"], "published_at not set on first publish"
        first_pub = pub["published_at"]

        pr = requests.get(f"{API}/blog/{slug}", timeout=30)
        assert pr.status_code == 200
        assert pr.json()["post"]["seo_title"] == "TEST SEO title"

        # re-save keeps the original published_at
        requests.put(f"{API}/admin/blog/{pid}", headers=hdr(admin_token),
                     json=payload | {"title": "TEST Journal Draft Story Edited"}, timeout=30)
        again = requests.get(f"{API}/admin/blog/{pid}", headers=hdr(admin_token), timeout=30).json()
        assert again["published_at"] == first_pub
        assert again["title"] == "TEST Journal Draft Story Edited"

    def test_slug_dedup(self, admin_token):
        payload = {"title": "TEST Duplicate Slug Story", "category": "Dining",
                   "body": "<p>hello there</p>", "status": "published"}
        a = requests.post(f"{API}/admin/blog", headers=hdr(admin_token), json=payload, timeout=30)
        b = requests.post(f"{API}/admin/blog", headers=hdr(admin_token), json=payload, timeout=30)
        assert a.status_code == 200 and b.status_code == 200
        TestAdminBlog.created += [a.json()["id"], b.json()["id"]]
        assert a.json()["slug"] != b.json()["slug"], "duplicate slug not de-duplicated"
        assert b.json()["slug"].startswith("test-duplicate-slug-story-")

    def test_featured_toggle_moves_hero(self, admin_token):
        payload = {"title": "TEST Featured Hero Story", "category": "Travel",
                   "body": "<p>a featured story body</p>", "status": "published",
                   "featured": True}
        r = requests.post(f"{API}/admin/blog", headers=hdr(admin_token), json=payload, timeout=30)
        assert r.status_code == 200
        pid, slug = r.json()["id"], r.json()["slug"]
        TestAdminBlog.created.append(pid)
        assert requests.get(f"{API}/blog", timeout=30).json()["featured"]["slug"] == slug
        # un-feature
        requests.put(f"{API}/admin/blog/{pid}", headers=hdr(admin_token),
                     json=payload | {"featured": False}, timeout=30)
        assert requests.get(f"{API}/blog", timeout=30).json()["featured"]["slug"] != slug

    def test_delete_removes_post(self, admin_token):
        r = requests.post(f"{API}/admin/blog", headers=hdr(admin_token),
                          json={"title": "TEST Deletable Story", "body": "<p>x</p>",
                                "status": "published"}, timeout=30)
        pid, slug = r.json()["id"], r.json()["slug"]
        d = requests.delete(f"{API}/admin/blog/{pid}", headers=hdr(admin_token), timeout=30)
        assert d.status_code == 200
        assert requests.get(f"{API}/admin/blog/{pid}", headers=hdr(admin_token),
                            timeout=30).status_code == 404
        assert requests.get(f"{API}/blog/{slug}", timeout=30).status_code == 404

    def test_validation_rejects_short_title(self, admin_token):
        r = requests.post(f"{API}/admin/blog", headers=hdr(admin_token),
                          json={"title": "ab"}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_bad_object_id(self, admin_token):
        r = requests.get(f"{API}/admin/blog/not-an-id", headers=hdr(admin_token), timeout=30)
        assert r.status_code in (400, 404), r.status_code


class TestAdminBlogRBAC:
    @pytest.mark.parametrize("who", ["member", "partner"])
    def test_forbidden(self, who, member_token, partner_token):
        tok = member_token if who == "member" else partner_token
        h = hdr(tok)
        assert requests.get(f"{API}/admin/blog", headers=h, timeout=30).status_code == 403
        assert requests.post(f"{API}/admin/blog", headers=h,
                             json={"title": "TEST RBAC story"}, timeout=30).status_code == 403
        assert requests.put(f"{API}/admin/blog/000000000000000000000000", headers=h,
                            json={"title": "TEST RBAC story"}, timeout=30).status_code == 403
        assert requests.delete(f"{API}/admin/blog/000000000000000000000000",
                               headers=h, timeout=30).status_code == 403

    def test_anonymous_blocked(self):
        assert requests.get(f"{API}/admin/blog", timeout=30).status_code in (401, 403)


# ---------------------------------------------------------------- iteration-48 fixes
class TestSecurityFixes:
    def test_register_rejects_short_password(self):
        r = requests.post(f"{API}/auth/register", timeout=30, json={
            "email": "test_shortpw_i49@example.com", "password": "Ab1cdefgh",  # 9 chars
            "full_name": "TEST Short Pw", "date_of_birth": "1990-01-01"})
        assert r.status_code == 422, f"{r.status_code} {r.text[:300]}"

    def test_email_credential_test_is_clean(self, admin_token):
        r = requests.post(f"{API}/admin/credentials/test/email", headers=hdr(admin_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "ok" in d and "message" in d
        if not os.environ.get("RESEND_API_KEY"):
            assert d["ok"] is False and d["message"] == "No email key is set.", d

    def test_credentials_list_is_masked(self, admin_token):
        r = requests.get(f"{API}/admin/credentials", headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        blob = r.text
        assert not re.search(r"sk_live|sk_test|re_[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_-]{20,}", blob), \
            "plaintext-looking secret in credentials payload"

    @pytest.mark.parametrize("path", ["/admin/credentials", "/admin/security/accounts"])
    def test_member_partner_forbidden(self, path, member_token, partner_token):
        for tok in (member_token, partner_token):
            assert requests.get(f"{API}{path}", headers=hdr(tok), timeout=30).status_code == 403

    def test_sidebar_role_source_exposes_role(self, admin_token):
        """The sidebar label needs a real role from /auth/me.
        NOTE: the seeded super admin has no `staff_role` at all (only role='admin'),
        so any label has to fall back on `role`."""
        me = requests.get(f"{API}/auth/me", headers=hdr(admin_token), timeout=30)
        assert me.status_code == 200
        d = me.json()
        assert d.get("role") == "admin"
        assert "permissions" in d and d["permissions"]


class TestAdminPasswordReset:
    """Reset the partner password through the admin endpoint, then restore it."""

    def test_reset_signs_out_and_new_password_works(self, admin_token):
        partner_old = login(*PARTNER)
        accounts = requests.get(f"{API}/admin/security/accounts", headers=hdr(admin_token),
                                timeout=30).json()
        target = next(i for i in accounts["items"] if i["email"] == PARTNER[0])

        # short password is rejected -> nothing is revealed to the UI
        bad = requests.post(f"{API}/admin/security/accounts/{target['id']}/password",
                            headers=hdr(admin_token), json={"value": "Short1"}, timeout=30)
        assert bad.status_code in (400, 422), bad.status_code
        assert requests.get(f"{API}/auth/me", headers=hdr(partner_old), timeout=30).status_code == 200

        new_pw = "TestRotate9xQ"
        try:
            ok = requests.post(f"{API}/admin/security/accounts/{target['id']}/password",
                               headers=hdr(admin_token), json={"value": new_pw}, timeout=30)
            assert ok.status_code == 200, ok.text[:300]
            assert "signed out" in ok.json()["message"].lower()
            time.sleep(1)
            assert requests.get(f"{API}/auth/me", headers=hdr(partner_old),
                                timeout=30).status_code == 401, "old token still valid"
            fresh = login(PARTNER[0], new_pw)
            assert requests.get(f"{API}/auth/me", headers=hdr(fresh), timeout=30).status_code == 200
        finally:
            back = requests.post(f"{API}/admin/security/accounts/{target['id']}/password",
                                 headers=hdr(admin_token), json={"value": PARTNER[1]}, timeout=30)
            assert back.status_code == 200, f"RESTORE FAILED: {back.text[:300]}"
            time.sleep(1)
            login(*PARTNER)

    def test_self_reset_blocked(self, admin_token):
        me = requests.get(f"{API}/auth/me", headers=hdr(admin_token), timeout=30).json()
        r = requests.post(f"{API}/admin/security/accounts/{me['id']}/password",
                          headers=hdr(admin_token), json={"value": "Whatever12345"}, timeout=30)
        assert r.status_code == 400


class TestRevokeAccess:
    def test_revoke_then_restore(self, admin_token):
        accounts = requests.get(f"{API}/admin/security/accounts", headers=hdr(admin_token),
                                timeout=30).json()
        target = next(i for i in accounts["items"] if i["email"] == PARTNER[0])
        tok = login(*PARTNER)
        try:
            r = requests.post(f"{API}/admin/security/accounts/{target['id']}/access",
                              headers=hdr(admin_token), json={"active": False}, timeout=30)
            assert r.status_code == 200 and r.json()["status"] == "suspended", r.text[:300]
            time.sleep(1)
            assert requests.get(f"{API}/auth/me", headers=hdr(tok),
                                timeout=30).status_code in (401, 403)
            blocked = requests.post(f"{API}/auth/login", timeout=30,
                                    json={"email": PARTNER[0], "password": PARTNER[1]})
            assert blocked.status_code in (401, 403), blocked.status_code
        finally:
            back = requests.post(f"{API}/admin/security/accounts/{target['id']}/access",
                                 headers=hdr(admin_token), json={"active": True}, timeout=30)
            assert back.status_code == 200 and back.json()["status"] == "active"
            time.sleep(1)
            login(*PARTNER)

    def test_revoke_sessions_only(self, admin_token):
        accounts = requests.get(f"{API}/admin/security/accounts", headers=hdr(admin_token),
                                timeout=30).json()
        target = next(i for i in accounts["items"] if i["email"] == PARTNER[0])
        tok = login(*PARTNER)
        r = requests.post(f"{API}/admin/security/accounts/{target['id']}/revoke",
                          headers=hdr(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        time.sleep(1)
        assert requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30).status_code == 401
        login(*PARTNER)  # can still log back in — access not revoked
