"""Iteration 54: Admin Publish button + hide-paid-hangouts switch (+ ads/writer regression)."""
import os
import re
from pathlib import Path

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
WRITER = ("writer.aisha@example.com", "Writer@12345")
HIDDEN_MSG = "Hangouts aren't available on Buddilio right now."


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login {email} failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok
    return tok


def sess(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def admin():
    return sess(login(*ADMIN))


@pytest.fixture(scope="session")
def member():
    return sess(login(*MEMBER))


@pytest.fixture(scope="session")
def writer():
    return sess(login(*WRITER))


def set_hide(admin_client, value: bool):
    cur = admin_client.get(f"{BASE}/admin/settings", timeout=30)
    assert cur.status_code == 200, cur.text[:300]
    body = cur.json()
    body.pop("id", None)
    body["hide_hangouts"] = value
    r = admin_client.put(f"{BASE}/admin/settings", json=body, timeout=60)
    assert r.status_code == 200, r.text[:400]
    assert bool(r.json().get("hide_hangouts")) is value
    return r.json()


# ---------------------------------------------------------------- Publish API
class TestPublish:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE}/admin/publish", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_status_forbidden_for_writer(self, writer):
        r = writer.get(f"{BASE}/admin/publish", timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_status_for_admin(self, admin):
        r = admin.get(f"{BASE}/admin/publish", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("available", "site_url", "last_publish"):
            assert k in d, f"missing {k} in {d}"
        assert isinstance(d["available"], bool)
        assert isinstance(d["site_url"], str) and d["site_url"]

    def test_post_publish_runs(self, admin):
        r = admin.post(f"{BASE}/admin/publish", timeout=300)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        assert "ok" in d and "message" in d
        if d.get("preview"):
            pytest.skip(f"no build dir in this env: {d['message']}")
        assert d["ok"] is True, f"publish failed: {d}"
        assert isinstance(d.get("log"), list)
        assert d.get("at")
        # last_publish persisted
        st = admin.get(f"{BASE}/admin/publish", timeout=30).json()
        assert st["last_publish"] == d["at"]

    def test_post_forbidden_for_anon_and_writer(self, writer):
        assert requests.post(f"{BASE}/admin/publish", timeout=30).status_code in (401, 403)
        assert writer.post(f"{BASE}/admin/publish", timeout=60).status_code == 403

    def test_publish_not_destructive(self):
        b = requests.get(f"{BASE}/blog?limit=3", timeout=30)
        assert b.status_code == 200, b.text[:300]
        items = b.json().get("items", [])
        assert items, "journal list empty after publish"
        slug = items[0]["slug"]
        one = requests.get(f"{BASE}/blog/{slug}", timeout=30)
        assert one.status_code == 200, one.text[:300]
        sm = requests.get(f"{BASE}/sitemap.xml", timeout=60)
        assert sm.status_code == 200
        assert "<urlset" in sm.text


# ------------------------------------------------- hide paid hangouts switch
class TestHideHangouts:
    @pytest.fixture(scope="class", autouse=True)
    def restore(self, admin):
        yield
        set_hide(admin, False)

    def test_hidden_state(self, admin, member):
        set_hide(admin, True)
        sc = requests.get(f"{BASE}/site-content", timeout=30)
        assert sc.status_code == 200
        assert sc.json().get("hangouts_enabled") is False

        for method, path, body in [
            ("get", "/companions", None),
            ("get", "/companions/507f1f77bcf86cd799439011", None),
            ("get", "/me/companion", None),
            ("post", "/me/companion", {"headline": "x", "bio": "y", "hourly_rate": 100,
                                       "city": "Delhi", "accept_terms": True}),
            ("post", "/companions/507f1f77bcf86cd799439011/bookings",
             {"hours": 1, "starts_at": "2026-12-01T10:00:00Z", "accept_terms": True}),
        ]:
            r = getattr(member, method)(f"{BASE}{path}", json=body, timeout=30)
            assert r.status_code == 404, f"{method.upper()} {path} -> {r.status_code} {r.text[:200]}"
            assert HIDDEN_MSG in r.text, f"{path} detail: {r.text[:200]}"

    def test_admin_data_intact_while_hidden(self, admin):
        r = admin.get(f"{BASE}/admin/companions?status=all", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json().get("items"), list)
        assert r.json()["items"], "admin companions list empty while hidden"

    def test_persistence_across_reload(self, admin):
        s = admin.get(f"{BASE}/admin/settings", timeout=30).json()
        assert s.get("hide_hangouts") is True

    def test_restore(self, admin, member):
        set_hide(admin, False)
        sc = requests.get(f"{BASE}/site-content", timeout=30)
        assert sc.json().get("hangouts_enabled") is True
        r = member.get(f"{BASE}/companions", timeout=30)
        assert r.status_code in (200, 403), f"{r.status_code} {r.text[:200]}"
        assert HIDDEN_MSG not in r.text
        mc = member.get(f"{BASE}/me/companion", timeout=30)
        assert mc.status_code in (200, 403, 404)
        assert HIDDEN_MSG not in mc.text


# --------------------------------------------------------- ads regression
class TestAdsRegression:
    created = []

    @pytest.fixture(scope="class", autouse=True)
    def cleanup(self, admin):
        yield
        for aid in self.created:
            admin.delete(f"{BASE}/admin/ads/{aid}", timeout=30)

    def test_list(self, admin):
        r = admin.get(f"{BASE}/admin/ads", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["items"], list) and d["placements"] and "config" in d

    def test_create_update_toggle_delete(self, admin):
        payload = {"name": "TEST_i54 ad", "placements": ["home"], "headline": "Test ad",
                   "image": "https://example.com/a.png", "url": "https://example.com",
                   "status": "active", "priority": 5}
        r = admin.post(f"{BASE}/admin/ads", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:400]
        aid = r.json()["id"]
        self.created.append(aid)
        r2 = admin.put(f"{BASE}/admin/ads/{aid}", json=payload | {"name": "TEST_i54 ad v2"}, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        rows = admin.get(f"{BASE}/admin/ads", timeout=30).json()["items"]
        assert any(x["name"] == "TEST_i54 ad v2" for x in rows)
        d = admin.delete(f"{BASE}/admin/ads/{aid}", timeout=30)
        assert d.status_code == 200, d.text[:300]
        self.created.remove(aid)
        rows = admin.get(f"{BASE}/admin/ads", timeout=30).json()["items"]
        assert not any(x["id"] == aid for x in rows)

    def test_empty_placement_rejected(self, admin):
        r = admin.post(f"{BASE}/admin/ads", json={"name": "TEST_i54 bad", "placements": [],
                                                  "image": "https://e.com/a.png",
                                                  "url": "https://e.com"}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"

    def test_bogus_placement_rejected(self, admin):
        r = admin.post(f"{BASE}/admin/ads", json={"name": "TEST_i54 bogus", "placements": ["nope"],
                                                  "image": "https://e.com/a.png",
                                                  "url": "https://e.com"}, timeout=30)
        assert r.status_code in (400, 422), f"{r.status_code} {r.text[:200]}"

    def test_click_bogus_ad(self):
        r = requests.post(f"{BASE}/ads/507f1f77bcf86cd799439011/click", timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"
        assert "no longer exists" in r.text

    def test_view_dedup(self, admin):
        payload = {"name": "TEST_i54 dedup", "placements": ["passes"], "headline": "Dedup",
                   "image": "https://example.com/a.png", "url": "https://example.com",
                   "status": "active", "priority": 10}
        aid = admin.post(f"{BASE}/admin/ads", json=payload, timeout=30).json()["id"]
        self.created.append(aid)
        s = requests.Session()
        for _ in range(3):
            r = s.get(f"{BASE}/ads?placement=passes", timeout=30)
            assert r.status_code == 200, r.text[:200]
        row = next((x for x in admin.get(f"{BASE}/admin/ads", timeout=30).json()["items"]
                    if x["id"] == aid), None)
        assert row is not None
        assert row.get("views", 0) <= 1, f"views not de-duplicated: {row.get('views')}"

    def test_head_code_save_and_clear(self, admin):
        cfg = admin.get(f"{BASE}/admin/ads", timeout=30).json()["config"]
        original = cfg.get("head_code", "")
        try:
            r = admin.put(f"{BASE}/admin/ads-config",
                          json=cfg | {"head_code": "<meta name=\"test-i54\" content=\"qa\" />"},
                          timeout=30)
            assert r.status_code == 200, r.text[:300]
            assert "test-i54" in admin.get(f"{BASE}/admin/ads", timeout=30).json()["config"]["head_code"]
        finally:
            admin.put(f"{BASE}/admin/ads-config", json=cfg | {"head_code": original}, timeout=30)
        assert admin.get(f"{BASE}/admin/ads", timeout=30).json()["config"].get("head_code", "") == original

    def test_public_slots_and_advertise_form(self):
        for slot in ("home", "events", "journal", "article", "footer"):
            r = requests.get(f"{BASE}/ads?placement={slot}", timeout=30)
            assert r.status_code == 200, f"{slot} -> {r.status_code}"
            assert "ad" in r.json()
        r = requests.post(f"{BASE}/advertise", json={
            "name": "TEST_i54 Advertiser", "email": "test.i54@example.com",
            "company": "TEST_i54 Co", "budget": "50k",
            "message": "TEST_i54 advertising enquiry from automated test."}, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"


# --------------------------------------------------------- writer regression
class TestWriterRegression:
    def test_writer_perms(self, writer):
        me = writer.get(f"{BASE}/auth/me", timeout=30)
        assert me.status_code == 200, me.text[:300]
        assert me.json().get("staff_role") == "writer" or me.json().get("role") == "admin"
        st = writer.get(f"{BASE}/admin/stats", timeout=30)
        assert st.status_code == 403, f"expected 403 for writer stats, got {st.status_code}"
        own = writer.get(f"{BASE}/writer/posts", timeout=30)
        assert own.status_code == 200, f"{own.status_code} {own.text[:200]}"
        assert isinstance(own.json().get("items"), list)
