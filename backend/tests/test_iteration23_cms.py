"""Iteration 23 — dynamic pages, site content, profile CRUD, admin events, city guides.

Run serially: pytest -n 0 backend/tests/test_iteration23_cms.py
"""
import os
import time
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from passlib.hash import bcrypt
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
MEMBER = ("diya.sharma@example.com", "User@12345")
PARTNER = ("partner@buddilio.com", "Partner@123")

# a members:manage-only staff account (no team:manage). Uses moderator preset which has members:manage
MMONLY = "test_members_only@buddilio.com"
MMONLY_PWD = "Test@1234"

VIEWER = "test_viewer_23@buddilio.com"
VIEWER_PWD = "Test@1234"


def _hash(pw): return bcrypt.hash(pw)


def _clear_lock(emails):
    DB.login_attempts.delete_many({"identifier": {"$in": [f"email:{e.lower()}" for e in emails]}})


def _ensure_staff():
    # members:manage only – custom staff with just members:manage extra
    DB.users.update_one({"email": MMONLY}, {"$set": {
        "email": MMONLY, "full_name": "TEST membersonly", "role": "admin",
        "staff_role": "support",  # support preset includes members:manage, moderation:manage, orders:view
        "extra_permissions": [],
        "password_hash": _hash(MMONLY_PWD),
        "status": "active", "verified": True, "email_verified": True, "city": "", "photo": "",
    }}, upsert=True)
    DB.users.update_one({"email": VIEWER}, {"$set": {
        "email": VIEWER, "full_name": "TEST viewer", "role": "admin",
        "staff_role": "viewer", "extra_permissions": [],
        "password_hash": _hash(VIEWER_PWD),
        "status": "active", "verified": True, "email_verified": True, "city": "", "photo": "",
    }}, upsert=True)
    _clear_lock([MMONLY, VIEWER, ADMIN[0], MANAGER[0], MEMBER[0], PARTNER[0]])


def _cleanup_staff():
    DB.users.delete_many({"email": {"$in": [MMONLY, VIEWER]}})


def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok): return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def setup():
    _ensure_staff()
    yield
    _cleanup_staff()
    # cleanup any test pages / users / events / site-content overrides left behind
    DB.cms_pages.delete_many({"slug": {"$regex": "^test-", "$options": "i"}})
    DB.users.delete_many({"email": {"$regex": "^test_it23_", "$options": "i"}})
    DB.events.delete_many({"title": {"$regex": "^TEST_IT23", "$options": "i"}})


@pytest.fixture(scope="module")
def admin_tok(): return _login(*ADMIN)


@pytest.fixture(scope="module")
def member_tok(): return _login(*MEMBER)


@pytest.fixture(scope="module")
def viewer_tok(): return _login(VIEWER, VIEWER_PWD)


@pytest.fixture(scope="module")
def mmonly_tok(): return _login(MMONLY, MMONLY_PWD)


# =============== 1. PAGES CMS ===============
class TestPagesCMS:
    def test_list_pages_has_block_types(self, admin_tok):
        r = requests.get(f"{BASE}/admin/pages", headers=_h(admin_tok))
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert set(data["block_types"]) == {"heading", "text", "richtext", "image", "quote", "list",
                                             "faq", "cta", "html"}

    def test_create_page_slug_normalised(self, admin_tok):
        r = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "Test Page!!", "title": "Test Page", "status": "published"})
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == "test-page"
        # cleanup below via slug delete
        pid = r.json()["id"]
        d = requests.delete(f"{BASE}/admin/pages/{pid}", headers=_h(admin_tok))
        assert d.status_code == 200

    def test_duplicate_slug_400(self, admin_tok):
        p = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "test-dup", "title": "Dup1"})
        assert p.status_code == 200
        pid = p.json()["id"]
        try:
            r = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
                "slug": "test-dup", "title": "Dup2"})
            assert r.status_code == 400
        finally:
            requests.delete(f"{BASE}/admin/pages/{pid}", headers=_h(admin_tok))

    def test_unknown_block_type_400(self, admin_tok):
        r = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "test-bad-block", "title": "Bad",
            "blocks": [{"type": "video", "text": "no"}]})
        assert r.status_code == 400
        assert "Unknown block type" in r.json()["detail"]

    def test_update_slug_clash_400(self, admin_tok):
        a = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "test-a", "title": "A"}).json()
        b = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "test-b", "title": "B"}).json()
        try:
            r = requests.put(f"{BASE}/admin/pages/{b['id']}", headers=_h(admin_tok), json={
                "slug": "test-a", "title": "B"})
            assert r.status_code == 400
        finally:
            requests.delete(f"{BASE}/admin/pages/{a['id']}", headers=_h(admin_tok))
            requests.delete(f"{BASE}/admin/pages/{b['id']}", headers=_h(admin_tok))

    def test_update_unknown_id_404(self, admin_tok):
        r = requests.put(f"{BASE}/admin/pages/{ObjectId()}", headers=_h(admin_tok),
                         json={"slug": "x", "title": "x"})
        assert r.status_code == 404

    def test_update_malformed_id_400(self, admin_tok):
        r = requests.put(f"{BASE}/admin/pages/notanid", headers=_h(admin_tok),
                         json={"slug": "x", "title": "x"})
        assert r.status_code == 400

    def test_delete_core_page_400(self, admin_tok):
        # find the "faq" page (core, seeded)
        page = DB.cms_pages.find_one({"slug": "faq"})
        assert page, "seed missing 'faq' page"
        r = requests.delete(f"{BASE}/admin/pages/{page['_id']}", headers=_h(admin_tok))
        assert r.status_code == 400
        assert "draft" in r.json()["detail"].lower()

    def test_draft_page_hidden_publicly(self, admin_tok):
        p = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json={
            "slug": "test-draft", "title": "Draft", "status": "draft"}).json()
        try:
            r = requests.get(f"{BASE}/cms/test-draft")
            assert r.status_code == 404
            listing = requests.get(f"{BASE}/cms").json()
            assert not any(p["slug"] == "test-draft" for p in listing["items"])
        finally:
            requests.delete(f"{BASE}/admin/pages/{p['id']}", headers=_h(admin_tok))

    def test_permission_gating(self, member_tok, viewer_tok):
        r = requests.get(f"{BASE}/admin/pages", headers=_h(member_tok))
        assert r.status_code == 403
        r = requests.get(f"{BASE}/admin/pages", headers=_h(viewer_tok))
        assert r.status_code == 403


# =============== 2. Full block-type rendering ===============
class TestBlockTypes:
    def test_all_block_types_persist(self, admin_tok):
        payload = {
            "slug": "test-blocks", "title": "Blocks",
            "blocks": [
                {"type": "heading", "heading": "Hello"},
                {"type": "text", "text": "Body"},
                {"type": "richtext", "text": "<p>rt</p>"},
                {"type": "image", "image": "https://ex.com/i.jpg"},
                {"type": "quote", "text": "Q"},
                {"type": "list", "items": ["one", "two"]},
                {"type": "faq", "items": ["Question | Answer"]},
                {"type": "cta", "cta_label": "Click", "cta_url": "/events"},
                {"type": "html", "text": "<div>html</div>"},
            ]}
        p = requests.post(f"{BASE}/admin/pages", headers=_h(admin_tok), json=payload).json()
        try:
            r = requests.get(f"{BASE}/cms/test-blocks")
            assert r.status_code == 200
            blocks = r.json()["blocks"]
            assert len(blocks) == 9
            kinds = [b["type"] for b in blocks]
            assert kinds == ["heading", "text", "richtext", "image", "quote", "list", "faq", "cta", "html"]
        finally:
            requests.delete(f"{BASE}/admin/pages/{p['id']}", headers=_h(admin_tok))


# =============== 3. Site content ===============
class TestSiteContent:
    def test_admin_site_content(self, admin_tok):
        r = requests.get(f"{BASE}/admin/site-content", headers=_h(admin_tok))
        assert r.status_code == 200
        d = r.json()
        for k in ("hero", "how_it_works", "stats", "testimonials", "nav", "footer"):
            assert k in d["content"] and k in d["defaults"]

    def test_public_site_content_lists_pages(self):
        r = requests.get(f"{BASE}/site-content")
        assert r.status_code == 200
        d = r.json()
        assert "pages" in d and isinstance(d["pages"], list)
        # each entry should have slug/title/label/header/footer_group/order
        for p in d["pages"][:3]:
            for k in ("slug", "title", "label", "header", "footer_group", "order"):
                assert k in p

    def test_update_unknown_key_400(self, admin_tok):
        r = requests.put(f"{BASE}/admin/site-content/nope", headers=_h(admin_tok),
                         json={"data": {}})
        assert r.status_code == 400

    def test_update_non_object_400(self, admin_tok):
        r = requests.put(f"{BASE}/admin/site-content/hero", headers=_h(admin_tok),
                         json={"data": "notdict"})
        assert r.status_code == 400

    def test_hero_update_and_reset(self, admin_tok):
        # snapshot original
        current = requests.get(f"{BASE}/admin/site-content", headers=_h(admin_tok)).json()["content"]["hero"]
        try:
            new_hero = {**current, "headline": "TESTHEAD", "tagline": "TESTTAG",
                        "subtext": "TESTSUB", "primary_label": "TESTPRIMARY"}
            r = requests.put(f"{BASE}/admin/site-content/hero", headers=_h(admin_tok),
                             json={"data": new_hero})
            assert r.status_code == 200
            live = requests.get(f"{BASE}/site-content").json()["hero"]
            assert live["headline"] == "TESTHEAD"
            assert live["tagline"] == "TESTTAG"
            assert live["primary_label"] == "TESTPRIMARY"
        finally:
            d = requests.delete(f"{BASE}/admin/site-content/hero", headers=_h(admin_tok))
            assert d.status_code == 200
        # confirm reset
        live_after = requests.get(f"{BASE}/site-content").json()["hero"]
        assert live_after["headline"] != "TESTHEAD"

    def test_perm_gating(self, member_tok):
        r = requests.get(f"{BASE}/admin/site-content", headers=_h(member_tok))
        assert r.status_code == 403


# =============== 4. Profile CRUD ===============
class TestProfileCRUD:
    def test_create_underage_400(self, admin_tok):
        r = requests.post(f"{BASE}/admin/users", headers=_h(admin_tok), json={
            "full_name": "Kid", "email": "test_it23_kid@example.com", "age": 18})
        assert r.status_code == 400
        assert "21" in r.json()["detail"]

    def test_create_duplicate_email_400(self, admin_tok):
        r = requests.post(f"{BASE}/admin/users", headers=_h(admin_tok), json={
            "full_name": "Dup", "email": ADMIN[0], "age": 30})
        assert r.status_code == 400

    def test_create_invalid_role_400(self, admin_tok):
        r = requests.post(f"{BASE}/admin/users", headers=_h(admin_tok), json={
            "full_name": "Bad", "email": "test_it23_badrole@example.com", "age": 30,
            "role": "wizard"})
        assert r.status_code == 400

    def test_members_only_cannot_create_admin(self, mmonly_tok):
        r = requests.post(f"{BASE}/admin/users", headers=_h(mmonly_tok), json={
            "full_name": "T", "email": "test_it23_denied@example.com", "age": 30,
            "role": "admin"})
        assert r.status_code == 403

    def test_full_lifecycle(self, admin_tok):
        # Create
        cr = requests.post(f"{BASE}/admin/users", headers=_h(admin_tok), json={
            "full_name": "TEST it23 user", "email": "test_it23_user@example.com",
            "age": 27, "role": "user", "password": "Temp@123",
            "city": "Mumbai", "bio": "hi", "interests": ["music"]})
        assert cr.status_code == 200, cr.text
        uid = cr.json()["id"]
        # Edit all fields
        er = requests.put(f"{BASE}/admin/users/{uid}", headers=_h(admin_tok), json={
            "full_name": "TEST it23 user2", "city": "Delhi", "country": "India",
            "age": 30, "bio": "b2", "photo": "http://x/p.jpg", "mobile": "+919999",
            "interests": ["food"], "org_name": "", "status": "active", "verified": True})
        assert er.status_code == 200, er.text
        assert er.json()["city"] == "Delhi"
        # Duplicate email
        d = requests.put(f"{BASE}/admin/users/{uid}", headers=_h(admin_tok),
                         json={"email": ADMIN[0]})
        assert d.status_code == 400
        # Empty body
        e = requests.put(f"{BASE}/admin/users/{uid}", headers=_h(admin_tok), json={})
        assert e.status_code == 400
        # Soft delete
        s = requests.delete(f"{BASE}/admin/users/{uid}?mode=soft", headers=_h(admin_tok))
        assert s.status_code == 200
        assert s.json()["status"] == "deleted"
        # Restore
        r = requests.post(f"{BASE}/admin/users/{uid}/restore", headers=_h(admin_tok))
        assert r.status_code == 200
        # Bad mode
        b = requests.delete(f"{BASE}/admin/users/{uid}?mode=zap", headers=_h(admin_tok))
        assert b.status_code == 400
        # Hard delete
        hd = requests.delete(f"{BASE}/admin/users/{uid}?mode=hard", headers=_h(admin_tok))
        assert hd.status_code == 200
        # Gone
        assert DB.users.find_one({"_id": ObjectId(uid)}) is None

    def test_cannot_delete_self(self, admin_tok):
        me = requests.get(f"{BASE}/auth/me", headers=_h(admin_tok)).json()
        r = requests.delete(f"{BASE}/admin/users/{me['id']}?mode=soft", headers=_h(admin_tok))
        assert r.status_code == 400

    def test_perm_gating(self, member_tok):
        r = requests.post(f"{BASE}/admin/users", headers=_h(member_tok), json={
            "full_name": "x", "email": "test_it23_x@example.com", "age": 30})
        assert r.status_code == 403


# =============== 5. Admin events ===============
class TestAdminEvents:
    def test_create_in_house(self, admin_tok):
        r = requests.post(f"{BASE}/admin/events", headers=_h(admin_tok), json={
            "title": "TEST_IT23 In-house", "category": "social",
            "city": "Mumbai", "starts_at": "2030-01-01T20:00:00Z",
            "partner_id": "", "status": "published"})
        assert r.status_code == 200, r.text
        assert r.json()["partner_name"] == "Buddilio"
        eid = r.json()["id"]
        # Bad status
        b = requests.post(f"{BASE}/admin/events", headers=_h(admin_tok), json={
            "title": "TEST_IT23 Bad", "category": "social",
            "city": "Mumbai", "starts_at": "2030-01-01T20:00:00Z", "status": "weird"})
        assert b.status_code == 400
        # Bad partner id
        bp = requests.post(f"{BASE}/admin/events", headers=_h(admin_tok), json={
            "title": "TEST_IT23 BadP", "category": "social",
            "city": "Mumbai", "starts_at": "2030-01-01T20:00:00Z",
            "partner_id": str(ObjectId())})
        assert bp.status_code == 400
        # Edit
        e = requests.put(f"{BASE}/admin/events/{eid}", headers=_h(admin_tok), json={
            "title": "TEST_IT23 Edited", "category": "social",
            "city": "Delhi", "starts_at": "2030-02-01T20:00:00Z"})
        assert e.status_code == 200
        assert e.json()["city"] == "Delhi"
        # Delete
        d = requests.delete(f"{BASE}/admin/events/{eid}", headers=_h(admin_tok))
        assert d.status_code == 200

    def test_perm_gating(self, member_tok):
        r = requests.post(f"{BASE}/admin/events", headers=_h(member_tok), json={
            "title": "x", "category": "social", "city": "X", "starts_at": "2030-01-01T00:00:00Z"})
        assert r.status_code == 403


# =============== 6. City guides ===============
class TestCityGuides:
    def test_list_all_27(self, admin_tok):
        r = requests.get(f"{BASE}/admin/city-guides", headers=_h(admin_tok))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 27
        for i in items[:3]:
            assert "city" in i and "slug" in i and "guide" in i and "custom" in i

    def test_override_and_reset(self, admin_tok):
        slug = "mumbai"
        # Snapshot
        before = requests.get(f"{BASE}/cities/{slug}")
        assert before.status_code == 200
        try:
            new_guide = {"neighbourhoods": ["TESTBORHOOD"], "when": "TESTWHEN", "tip": "TESTIP",
                         "faqs": [{"q": "TQ", "a": "TA"}]}
            u = requests.put(f"{BASE}/admin/city-guides/{slug}", headers=_h(admin_tok),
                             json={"guide": new_guide})
            assert u.status_code == 200, u.text
            live = requests.get(f"{BASE}/cities/{slug}").json()
            # guide/tip must reflect our change
            g = live.get("guide") or live
            assert "TESTIP" in str(g)
        finally:
            r = requests.delete(f"{BASE}/admin/city-guides/{slug}", headers=_h(admin_tok))
            assert r.status_code == 200

    def test_perm_gating(self, member_tok):
        r = requests.get(f"{BASE}/admin/city-guides", headers=_h(member_tok))
        assert r.status_code == 403


# =============== 7. Regression: PUT /users/me for members ===============
class TestUserProfileRegression:
    """duplicate ProfileIn model at line 4740 overrides the one at 519 —
    members updating just their city should still work."""
    def test_member_can_partial_update(self, member_tok):
        # Just update bio without required fields
        r = requests.put(f"{BASE}/users/me", headers=_h(member_tok), json={"bio": "regression check"})
        # If duplicate ProfileIn model overrides, will return 422
        assert r.status_code == 200, f"PUT /users/me regressed: {r.status_code} {r.text}"
