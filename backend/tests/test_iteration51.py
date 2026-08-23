"""Iteration 51 — currency list, human support inbox, SEO & indexing, sitemap encoding."""
import os
import re
import xml.etree.ElementTree as ET

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} -> {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    return tok


@pytest.fixture(scope="session")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="session")
def member_token():
    return login(*MEMBER)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- currency (meta) ----------------
class TestCurrencies:
    def test_meta_currencies_exactly_four(self):
        r = requests.get(f"{BASE}/meta", timeout=30)
        assert r.status_code == 200, r.text[:300]
        codes = [c["code"] for c in r.json().get("currencies", [])]
        assert codes == ["USD", "INR", "GBP", "EUR"], codes


# ---------------- sitemap ----------------
class TestSitemap:
    def test_sitemap_valid_and_plus_encoded(self):
        r = requests.get(f"{BASE}/sitemap.xml", timeout=60)
        assert r.status_code == 200
        assert "xml" in r.headers.get("content-type", "")
        root = ET.fromstring(r.text)  # valid XML
        locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        assert locs, "sitemap empty"
        cats = [l for l in locs if "?category=" in l]
        assert cats, "no category urls"
        assert any("City+Guides" in l for l in cats), cats
        for l in cats:
            assert "%20" not in l and " " not in l, l

    def test_sitemap_published_posts_only(self):
        sm = requests.get(f"{BASE}/sitemap.xml", timeout=60).text
        idx = requests.get(f"{BASE}/blog?limit=48", timeout=30).json()
        posts = [p for p in [idx.get("featured")] + (idx.get("items") or []) if p]
        assert posts, "no published posts"
        for p in posts:
            assert f"/blog/{p['slug']}" in sm, p["slug"]


# ---------------- SEO panel ----------------
class TestSeo:
    def test_seo_public_shape(self):
        r = requests.get(f"{BASE}/seo/public", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("gsc_verification", "indexnow_key", "site_url"):
            assert k in d, d

    def test_admin_seo_requires_perm(self, member_token):
        r = requests.get(f"{BASE}/admin/seo", headers=H(member_token), timeout=30)
        assert r.status_code == 403, r.status_code

    def test_admin_seo_overview(self, admin_token):
        r = requests.get(f"{BASE}/admin/seo", headers=H(admin_token), timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] > 0 and isinstance(d["urls"], list) and d["urls"]
        assert "Journal" in d["groups"]
        assert d["sitemap_url"].endswith("/api/sitemap.xml")
        assert d["can_submit"] is False, "preview host should not be submittable"

    def test_save_and_persist_settings(self, admin_token):
        token = "TESTtoken51abc"
        r = requests.put(f"{BASE}/admin/seo", headers=H(admin_token),
                         json={"gsc_verification": f'<meta name="google-site-verification" content="{token}" />',
                               "site_url": "lifestyle-connect-17.preview.emergentagent.com"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        got = requests.get(f"{BASE}/admin/seo", headers=H(admin_token), timeout=60).json()
        assert got["gsc_verification"] == token, got["gsc_verification"]
        assert got["site_url"].startswith("https://"), got["site_url"]
        pub = requests.get(f"{BASE}/seo/public", timeout=30).json()
        assert pub["gsc_verification"] == token

    def test_rotate_indexnow_key(self, admin_token):
        before = requests.get(f"{BASE}/admin/seo", headers=H(admin_token), timeout=60).json()["indexnow_key"]
        r = requests.post(f"{BASE}/admin/seo/indexnow-key", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        new = r.json()["indexnow_key"]
        assert new and new != before
        assert requests.get(f"{BASE}/seo/public", timeout=30).json()["indexnow_key"] == new

    def test_submit_refused_on_preview_host(self, admin_token):
        """Must refuse — never fires a real IndexNow submission from preview."""
        r = requests.post(f"{BASE}/admin/seo/submit", headers=H(admin_token),
                          json={"scope": "blog"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "live site" in r.json().get("detail", "").lower()

    def test_submit_forbidden_for_member(self, member_token):
        r = requests.post(f"{BASE}/admin/seo/submit", headers=H(member_token),
                          json={"scope": "blog"}, timeout=30)
        assert r.status_code == 403


# ---------------- human support ----------------
class TestSupportGuest:
    def test_guest_requires_name_email(self):
        r = requests.post(f"{BASE}/support/threads",
                          json={"message": "TEST_ guest hello there"}, timeout=30)
        assert r.status_code == 400, r.status_code
        assert "name" in r.json().get("detail", "").lower()

    def test_guest_thread_flow(self):
        r = requests.post(f"{BASE}/support/threads",
                          json={"message": "TEST_ guest needs a human", "name": "TEST Guest",
                                "email": "test.guest51@example.com", "page": "/",
                                "ai_transcript": ["u: hi", "a: hello"]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        tid, token = d["thread"]["id"], d["token"]
        assert token and d["thread"]["messages"][0]["role"] == "visitor"

        # read with token
        g = requests.get(f"{BASE}/support/threads/{tid}", params={"token": token}, timeout=30)
        assert g.status_code == 200
        assert g.json()["thread"]["messages"][0]["body"] == "TEST_ guest needs a human"

        # no token / wrong token -> 403
        assert requests.get(f"{BASE}/support/threads/{tid}", timeout=30).status_code == 403
        assert requests.get(f"{BASE}/support/threads/{tid}",
                            params={"token": "nope"}, timeout=30).status_code == 403

        # follow-up message
        r2 = requests.post(f"{BASE}/support/threads/{tid}/messages",
                           json={"message": "TEST_ any update?", "token": token}, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        assert len(requests.get(f"{BASE}/support/threads/{tid}", params={"token": token},
                                timeout=30).json()["thread"]["messages"]) == 2
        pytest.guest_thread = (tid, token)


class TestSupportMember:
    def test_member_thread_no_identity_needed(self, member_token):
        r = requests.post(f"{BASE}/support/threads", headers=H(member_token),
                          json={"message": "TEST_ member wants a human"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        tid = r.json()["thread"]["id"]
        # member can read without token (session ownership)
        g = requests.get(f"{BASE}/support/threads/{tid}", headers=H(member_token), timeout=30)
        assert g.status_code == 200
        mine = requests.get(f"{BASE}/support/threads", headers=H(member_token), timeout=30)
        assert mine.status_code == 200
        assert any(t["id"] == tid for t in mine.json()["items"])
        pytest.member_thread = tid

    def test_member_cannot_read_guest_thread(self, member_token):
        tid, _tok = pytest.guest_thread
        r = requests.get(f"{BASE}/support/threads/{tid}", headers=H(member_token), timeout=30)
        assert r.status_code == 403, r.status_code

    def test_member_admin_inbox_forbidden(self, member_token):
        assert requests.get(f"{BASE}/admin/support", headers=H(member_token),
                            timeout=30).status_code == 403


class TestSupportAdmin:
    def test_inbox_lists_threads_with_counts(self, admin_token):
        r = requests.get(f"{BASE}/admin/support", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        ids = [t["id"] for t in d["items"]]
        gid, _ = pytest.guest_thread
        assert gid in ids and pytest.member_thread in ids
        guest = next(t for t in d["items"] if t["id"] == gid)
        assert guest["unread"] is True and guest["is_member"] is False
        member = next(t for t in d["items"] if t["id"] == pytest.member_thread)
        assert member["is_member"] is True
        for s in ("open", "pending", "closed", "unread"):
            assert s in d["counts"]

    def test_open_marks_read(self, admin_token):
        gid, _ = pytest.guest_thread
        r = requests.get(f"{BASE}/admin/support/{gid}", headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["ai_transcript"], "ai transcript not stored"
        lst = requests.get(f"{BASE}/admin/support", headers=H(admin_token), timeout=30).json()
        assert next(t for t in lst["items"] if t["id"] == gid)["unread"] is False

    def test_staff_reply_visible_to_visitor(self, admin_token):
        gid, token = pytest.guest_thread
        r = requests.post(f"{BASE}/admin/support/{gid}/reply", headers=H(admin_token),
                          json={"message": "TEST_ staff reply here"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        thread = requests.get(f"{BASE}/support/threads/{gid}", params={"token": token},
                              timeout=30).json()["thread"]
        staff = [m for m in thread["messages"] if m["role"] == "staff"]
        assert staff and staff[-1]["body"] == "TEST_ staff reply here"
        assert thread["status"] == "pending"

    def test_status_transitions(self, admin_token):
        gid, _ = pytest.guest_thread
        for s in ("closed", "open"):
            r = requests.patch(f"{BASE}/admin/support/{gid}", headers=H(admin_token),
                               json={"status": s}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            got = requests.get(f"{BASE}/admin/support/{gid}", headers=H(admin_token),
                               timeout=30).json()["thread"]
            assert got["status"] == s
        bad = requests.patch(f"{BASE}/admin/support/{gid}", headers=H(admin_token),
                             json={"status": "banana"}, timeout=30)
        assert bad.status_code == 400

    def test_status_filter(self, admin_token):
        r = requests.get(f"{BASE}/admin/support", headers=H(admin_token),
                         params={"status": "open"}, timeout=30)
        assert r.status_code == 200
        assert all(t["status"] == "open" for t in r.json()["items"])

    def test_no_mongo_id_leak(self, admin_token):
        r = requests.get(f"{BASE}/admin/support", headers=H(admin_token), timeout=30)
        assert '"_id"' not in r.text
        assert '"token"' not in r.text, "visitor token leaked in staff list"


# ---------------- blog regression ----------------
class TestBlogRegression:
    def test_blog_index_and_article(self):
        idx = requests.get(f"{BASE}/blog?limit=12", timeout=30)
        assert idx.status_code == 200
        d = idx.json()
        assert d["items"] and d.get("all_categories")
        slug = (d.get("featured") or d["items"][0])["slug"]
        art = requests.get(f"{BASE}/blog/{slug}", timeout=30)
        assert art.status_code == 200
        a = art.json()
        assert a["post"]["slug"] == slug and a["post"]["body"]
        assert a["jsonld"]["@type"] in ("BlogPosting", "Article")

    def test_blog_category_filter(self):
        cats = requests.get(f"{BASE}/blog?limit=12", timeout=30).json()["all_categories"]
        cat = cats[0]
        r = requests.get(f"{BASE}/blog", params={"category": cat, "limit": 12}, timeout=30)
        assert r.status_code == 200
        assert all(i["category"] == cat for i in r.json()["items"])

    def test_no_draft_leak(self):
        assert requests.get(f"{BASE}/blog/definitely-not-a-slug-51", timeout=30).status_code == 404
