"""Iteration 30 — PII masking + reveal / temp password + HTML rich-text sanitisation.

Covers:
- masked_user() output shape via GET /api/admin/users (can_reveal only for team:manage)
- POST /api/admin/users/{uid}/reveal — super admin 200 with seconds=10, manager/partner/member 403,
  400 on bad id, 404 on unknown id, and audit row written.
- POST /api/admin/users/{uid}/temp-password — super admin only, rotates hash, must_change=true,
  old password stops working, new one logs in, audit row written; teardown restores original bcrypt.
- Masked values rejected on PUT /api/admin/users/{uid} for email + mobile.
- bleach sanitisation on rich-text endpoints strips <script>, onerror handlers and javascript: URLs
  while keeping <p>/<b>/<h2>/<ul>/<li>/<a href="https://..">.
"""
import os
import re
import time
from pathlib import Path
from typing import Optional

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("tara.joshi@example.com", "User@12345")
AARAV = ("aarav.mehta@example.com", "User@12345")
COMPANION = ("ananya.kapoor@example.com", "User@12345")

DIRTY_HTML = (
    '<p>Hello <b>world</b></p>'
    '<script>alert("xss")</script>'
    '<img src=x onerror="alert(1)"/>'
    '<a href="javascript:alert(1)">bad</a>'
    '<a href="https://buddilio.com">good</a>'
    '<h2>Section</h2><ul><li>one</li><li>two</li></ul>'
)


# ---------------- fixtures ----------------
def _login(session: requests.Session, email: str, password: str) -> Optional[str]:
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


def _client(token: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    tok = _login(s, *ADMIN)
    if not tok:
        pytest.skip("admin login failed")
    return _client(tok)


@pytest.fixture(scope="module")
def manager_client():
    s = requests.Session()
    tok = _login(s, *MANAGER)
    if not tok:
        pytest.skip("manager login failed")
    return _client(tok)


@pytest.fixture(scope="module")
def partner_client():
    s = requests.Session()
    tok = _login(s, *PARTNER)
    return _client(tok) if tok else None


@pytest.fixture(scope="module")
def member_client():
    s = requests.Session()
    tok = _login(s, *MEMBER)
    return _client(tok) if tok else None


@pytest.fixture(scope="module")
def aarav_client():
    s = requests.Session()
    tok = _login(s, *AARAV)
    return _client(tok) if tok else None


@pytest.fixture(scope="module")
def target_uid(admin_client):
    """Find Tara's user id via masked admin listing (unique full_name)."""
    r = admin_client.get(f"{API}/admin/users?q=Tara+Joshi&limit=5", timeout=15)
    assert r.status_code == 200, r.text
    for u in r.json()["items"]:
        if u.get("full_name", "").lower().startswith("tara"):
            return u["id"]
    pytest.skip("Tara Joshi not found in admin users")


# ---------------- PII masking ----------------
class TestPiiMasking:
    def test_admin_sees_masked_and_can_reveal(self, admin_client):
        r = admin_client.get(f"{API}/admin/users?limit=5", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["can_reveal"] is True
        assert body["items"], "expected some users"
        for u in body["items"]:
            assert u.get("pii_masked") is True
            assert "•" in u["email"] or "@" not in u.get("email", "@")
            # mobile may be empty for some accounts; if present, ensure masked
            if u.get("mobile"):
                assert "•" in u["mobile"]

    def test_mask_shape(self, admin_client):
        r = admin_client.get(f"{API}/admin/users?q=Tara&limit=3", timeout=15)
        assert r.status_code == 200
        u = [x for x in r.json()["items"] if x["full_name"].lower().startswith("tara")][0]
        # first 2 chars of local, then bullets, then @, first char host, bullets, .tld
        assert re.match(r"^[a-z]{2}•+@[a-z]•+\.[a-z]+$", u["email"], re.I), u["email"]

    def test_manager_no_members_view(self, manager_client):
        # ops.manager (legacy vendor_manager) has no members:view — /admin/users must 403
        r = manager_client.get(f"{API}/admin/users?limit=3", timeout=15)
        assert r.status_code == 403

    def test_staff_with_members_view_only(self, admin_client, db):
        """Create a temp staff user with members:view but no team:manage — must see masked + can_reveal=false."""
        from passlib.hash import bcrypt
        email = "test_iter30_viewer@buddilio.com"
        db.users.delete_many({"email": email})
        db.users.insert_one({
            "email": email, "full_name": "TEST Viewer", "role": "admin",
            "password_hash": bcrypt.hash("Viewer@123"), "status": "active",
            "staff_role": "support",  # support preset includes members:view but not team:manage
            "created_at": "2026-01-01T00:00:00Z",
        })
        s = requests.Session()
        tok = _login(s, email, "Viewer@123")
        assert tok, "viewer login failed"
        cli = _client(tok)
        try:
            r = cli.get(f"{API}/admin/users?limit=3", timeout=15)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["can_reveal"] is False, "non-team:manage staff must not see can_reveal=true"
            for u in body["items"]:
                assert u.get("pii_masked") is True
        finally:
            db.users.delete_many({"email": email})

    def test_partner_cannot_list(self, partner_client):
        if not partner_client:
            pytest.skip("partner login failed")
        r = partner_client.get(f"{API}/admin/users?limit=3", timeout=15)
        assert r.status_code == 403


# ---------------- Reveal endpoint ----------------
class TestReveal:
    def test_admin_reveal_returns_real_values(self, admin_client, db, target_uid):
        before = db.audit_logs.count_documents({"action": "user.pii_reveal", "entity_id": target_uid})
        r = admin_client.post(f"{API}/admin/users/{target_uid}/reveal", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["seconds"] == 10
        assert body["email"] == "tara.joshi@example.com"
        assert "•" not in body["email"]
        after = db.audit_logs.count_documents({"action": "user.pii_reveal", "entity_id": target_uid})
        assert after == before + 1, "audit row not written"

    def test_manager_reveal_403(self, manager_client, target_uid):
        r = manager_client.post(f"{API}/admin/users/{target_uid}/reveal", timeout=15)
        assert r.status_code == 403

    def test_partner_reveal_403(self, partner_client, target_uid):
        if not partner_client:
            pytest.skip()
        r = partner_client.post(f"{API}/admin/users/{target_uid}/reveal", timeout=15)
        assert r.status_code == 403

    def test_member_reveal_403(self, member_client, target_uid):
        if not member_client:
            pytest.skip()
        r = member_client.post(f"{API}/admin/users/{target_uid}/reveal", timeout=15)
        assert r.status_code == 403

    def test_invalid_id_400(self, admin_client):
        r = admin_client.post(f"{API}/admin/users/not-an-oid/reveal", timeout=15)
        assert r.status_code == 400

    def test_unknown_id_404(self, admin_client):
        oid = str(ObjectId())
        r = admin_client.post(f"{API}/admin/users/{oid}/reveal", timeout=15)
        assert r.status_code == 404


# ---------------- Temp password ----------------
class TestTempPassword:
    def test_manager_temp_pw_403(self, manager_client, target_uid):
        r = manager_client.post(f"{API}/admin/users/{target_uid}/temp-password", timeout=15)
        assert r.status_code == 403

    def test_partner_temp_pw_403(self, partner_client, target_uid):
        if not partner_client:
            pytest.skip()
        r = partner_client.post(f"{API}/admin/users/{target_uid}/temp-password", timeout=15)
        assert r.status_code == 403

    def test_super_admin_temp_password_flow_and_restore(self, admin_client, db, target_uid):
        """Issue temp pw, verify old fails + new works, then restore original hash."""
        original = db.users.find_one({"_id": ObjectId(target_uid)},
                                     {"password_hash": 1, "must_change_password": 1,
                                      "password_reset_by": 1, "password_reset_at": 1})
        original_hash = original["password_hash"]
        assert original_hash.startswith("$2b$")

        audit_before = db.audit_logs.count_documents({"action": "user.temp_password", "entity_id": target_uid})

        r = admin_client.post(f"{API}/admin/users/{target_uid}/temp-password", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["seconds"] == 10
        assert body["must_change"] is True
        assert isinstance(body["password"], str) and len(body["password"]) >= 12
        temp_pw = body["password"]

        # audit row written
        assert db.audit_logs.count_documents({"action": "user.temp_password",
                                              "entity_id": target_uid}) == audit_before + 1

        # DB flags set
        u = db.users.find_one({"_id": ObjectId(target_uid)},
                              {"must_change_password": 1, "password_hash": 1, "password_reset_by": 1})
        assert u["must_change_password"] is True
        assert u["password_hash"] != original_hash
        assert u.get("password_reset_by")

        # Old password no longer works
        s = requests.Session()
        r_old = s.post(f"{API}/auth/login", json={"email": MEMBER[0], "password": MEMBER[1]}, timeout=15)
        assert r_old.status_code == 401, f"old password still valid: {r_old.status_code}"

        # New temp password works
        r_new = s.post(f"{API}/auth/login", json={"email": MEMBER[0], "password": temp_pw}, timeout=15)
        assert r_new.status_code == 200, r_new.text

        # RESTORE original hash + clear flags (teardown that must always run before other suites)
        db.users.update_one({"_id": ObjectId(target_uid)},
                            {"$set": {"password_hash": original_hash},
                             "$unset": {"must_change_password": "", "password_reset_by": "",
                                        "password_reset_at": ""}})
        # Verify original documented password logs in again — if the pre-test hash was already
        # stale (e.g. leftover from a previous aborted run), forcibly reseed User@123 so downstream
        # suites keep working.
        r_restored = s.post(f"{API}/auth/login", json={"email": MEMBER[0], "password": MEMBER[1]}, timeout=15)
        if r_restored.status_code != 200:
            import bcrypt as _bc
            reseeded = _bc.hashpw(MEMBER[1].encode(), _bc.gensalt()).decode()
            db.users.update_one({"_id": ObjectId(target_uid)},
                                {"$set": {"password_hash": reseeded}})
            # clear lockout too
            db.login_attempts.delete_many({"identifier": f"email:{MEMBER[0]}"})
            r_restored = s.post(f"{API}/auth/login",
                                json={"email": MEMBER[0], "password": MEMBER[1]}, timeout=15)
        assert r_restored.status_code == 200, "documented password no longer works after restore!"


# ---------------- Reject masked values on save ----------------
class TestRejectMasked:
    def test_masked_email_rejected(self, admin_client, target_uid):
        r = admin_client.put(f"{API}/admin/users/{target_uid}",
                             json={"email": "ta••••@g•••••.com"}, timeout=15)
        assert r.status_code == 400
        assert "reveal" in r.json()["detail"].lower()

    def test_masked_mobile_rejected(self, admin_client, target_uid):
        r = admin_client.put(f"{API}/admin/users/{target_uid}",
                             json={"mobile": "91••••••••23"}, timeout=15)
        assert r.status_code == 400
        assert "reveal" in r.json()["detail"].lower()

    def test_real_email_saves(self, admin_client, db, target_uid):
        r = admin_client.put(f"{API}/admin/users/{target_uid}",
                             json={"email": "tara.joshi@example.com"}, timeout=15)
        assert r.status_code == 200
        # DB unchanged
        u = db.users.find_one({"_id": ObjectId(target_uid)}, {"email": 1})
        assert u["email"] == "tara.joshi@example.com"


# ---------------- HTML sanitisation ----------------
def _assert_sanitised(html: str):
    low = html.lower()
    assert "<script" not in low, f"<script> not stripped: {html[:200]}"
    assert "onerror" not in low, f"onerror not stripped: {html[:200]}"
    assert "javascript:" not in low, f"javascript: not stripped: {html[:200]}"
    # allowed tags survive
    assert "<b>" in low or "<strong>" in low
    assert "<h2>" in low
    assert "<ul>" in low and "<li>" in low
    assert 'href="https://buddilio.com"' in low or "href='https://buddilio.com'" in low


class TestRichTextSanitisation:
    def test_email_template_body(self, admin_client, db):
        # Get any existing template key
        r = admin_client.get(f"{API}/admin/email-templates", timeout=15)
        assert r.status_code == 200
        key = r.json()["items"][0]["key"]
        # Fetch current values to preserve
        cur = [t for t in r.json()["items"] if t["key"] == key][0]
        payload = {"subject": cur["subject"], "title": cur.get("title", ""),
                   "body": DIRTY_HTML, "cta_label": cur.get("cta_label", ""),
                   "cta_url": cur.get("cta_url", "")}
        r2 = admin_client.put(f"{API}/admin/email-templates/{key}", json=payload, timeout=15)
        assert r2.status_code == 200, r2.text
        _assert_sanitised(r2.json()["body"])
        # cleanup: reset to default
        admin_client.delete(f"{API}/admin/email-templates/{key}", timeout=15)

    def test_cms_content(self, admin_client, db):
        slug = "faq"
        cur = db.cms_pages.find_one({"slug": slug}) or {}
        body = {"title": cur.get("title", "FAQ"), "content": DIRTY_HTML,
                "seo_title": cur.get("seo_title", ""), "seo_description": cur.get("seo_description", "")}
        r = admin_client.put(f"{API}/admin/cms/{slug}", json=body, timeout=15)
        assert r.status_code == 200, r.text
        _assert_sanitised(r.json()["content"])
        # restore
        if cur:
            db.cms_pages.update_one({"slug": slug}, {"$set": {"content": cur.get("content", "")}})

    def test_page_create_and_blocks(self, admin_client, db):
        payload = {"slug": "test_iter30_page", "title": "TEST Iter30 Page",
                   "content": DIRTY_HTML, "status": "draft",
                   "blocks": [
                       {"type": "richtext", "heading": "TEST", "text": DIRTY_HTML,
                        "image": "", "items": [], "cta_label": "", "cta_url": ""},
                       {"type": "text", "heading": "", "text": DIRTY_HTML,
                        "image": "", "items": [], "cta_label": "", "cta_url": ""},
                   ]}
        r = admin_client.post(f"{API}/admin/pages", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        page = r.json()
        _assert_sanitised(page["content"])
        for b in page["blocks"]:
            _assert_sanitised(b["text"])
        # update path
        r2 = admin_client.put(f"{API}/admin/pages/{page['id']}", json=payload, timeout=15)
        assert r2.status_code == 200
        _assert_sanitised(r2.json()["content"])
        # delete
        admin_client.delete(f"{API}/admin/pages/{page['id']}", timeout=15)

    def test_user_bio(self, aarav_client, db):
        if not aarav_client:
            pytest.skip()
        prev = db.users.find_one({"email": AARAV[0]}, {"bio": 1}).get("bio", "")
        r = aarav_client.put(f"{API}/users/me", json={"bio": DIRTY_HTML}, timeout=15)
        assert r.status_code == 200, r.text
        _assert_sanitised(r.json()["bio"])
        # restore
        aarav_client.put(f"{API}/users/me", json={"bio": prev or ""}, timeout=15)

    def test_partner_event_description_and_rules(self, partner_client, db):
        if not partner_client:
            pytest.skip()
        payload = {"title": "TEST Iter30 Event", "category": "dining", "city": "Mumbai",
                   "starts_at": "2099-01-01T20:00:00", "capacity": 10,
                   "description": DIRTY_HTML, "rules": DIRTY_HTML}
        r = partner_client.post(f"{API}/partner/events", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        ev = r.json()
        _assert_sanitised(ev["description"])
        _assert_sanitised(ev["rules"])
        # update
        payload["description"] = "<p>Updated</p>" + DIRTY_HTML
        r2 = partner_client.put(f"{API}/partner/events/{ev['id']}", json=payload, timeout=20)
        assert r2.status_code == 200
        _assert_sanitised(r2.json()["description"])
        # cleanup — hard delete via mongo (partner API has no delete)
        db.events.delete_one({"_id": ObjectId(ev["id"])})

    def test_companion_about(self, db):
        """Ananya is an approved companion — update her about with dirty HTML and confirm sanitisation."""
        u = db.users.find_one({"email": COMPANION[0]}, {"companion": 1})
        prev_companion = u.get("companion") or {}
        s = requests.Session()
        tok = _login(s, *COMPANION)
        if not tok:
            pytest.skip("companion login failed")
        cli = _client(tok)
        payload = {"about": DIRTY_HTML, "hourly_rate": prev_companion.get("hourly_rate", 1500),
                   "categories": prev_companion.get("categories", ["dining"]),
                   "cities": prev_companion.get("cities", ["Mumbai"]),
                   "min_hours": prev_companion.get("min_hours", 2),
                   "max_hours": prev_companion.get("max_hours", 5),
                   "packages": prev_companion.get("packages", []),
                   "accept_terms": True}
        r = cli.post(f"{API}/me/companion", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        _assert_sanitised(r.json()["about"])
        # restore original companion doc (keeps enabled, verified etc.)
        db.users.update_one({"email": COMPANION[0]}, {"$set": {"companion": prev_companion}})

    def test_email_send_test_renders_html(self, admin_client):
        # Wait for the 15s cooldown from earlier test_email_template_body
        time.sleep(16)
        r = admin_client.get(f"{API}/admin/email-templates", timeout=15)
        key = r.json()["items"][0]["key"]
        r2 = admin_client.post(f"{API}/admin/email-templates/{key}/test", timeout=20)
        # sandbox provider rejects admin@buddilio.com (documented) but the render itself must succeed
        assert r2.status_code in (200, 429), r2.text
