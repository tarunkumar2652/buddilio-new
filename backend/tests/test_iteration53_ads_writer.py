"""Iteration 53 — writer invites (staff_role writer, /api/writer/*) and house ads (/api/ads, /api/admin/ads)."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
WRITER = ("writer.aisha@example.com", "Writer@12345")
MEMBER = ("arjun.sethi@example.com", "User@12345")

LONG_BODY = "<p>" + " ".join(["Buddilio nights out in the city are a story worth telling."] * 20) + "</p>"
SHORT_BODY = "<p>Too short to review.</p>"


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token in login response: {r.text[:200]}"
    return tok


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_t():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def writer_t():
    return login(*WRITER)


@pytest.fixture(scope="module")
def member_t():
    return login(*MEMBER)


@pytest.fixture(scope="module")
def state():
    return {"ads": [], "posts": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(state, admin_t):
    yield
    for aid in state["ads"]:
        requests.delete(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30)
    requests.put(f"{API}/admin/ads-config", headers=hdr(admin_t), timeout=30,
                 json={"network_enabled": False, "network_client": "", "network_slots": {},
                       "hide_for_plans": []})
    for pid in state["posts"]:
        requests.delete(f"{API}/admin/blog/{pid}", headers=hdr(admin_t), timeout=30)


# ---------------- writer scope / RBAC ----------------
class TestWriterScope:
    def test_writer_me_role(self, writer_t):
        r = requests.get(f"{API}/auth/me", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        me = r.json()
        assert me.get("staff_role") == "writer", me
        perms = me.get("permissions") or []
        assert "content:draft" in perms, perms
        assert "content:manage" not in perms, perms

    @pytest.mark.parametrize("path", ["/admin/blog", "/admin/ads", "/admin/seo"])
    def test_writer_blocked_from_admin_sections(self, writer_t, path):
        r = requests.get(f"{API}{path}", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_writer_desk_loads(self, writer_t):
        r = requests.get(f"{API}/writer/posts", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["items"], list)
        assert d["categories"], d
        assert d["author"] and d["author"]["slug"] == "aisha-rahman", d.get("author")


# ---------------- writer authoring + review cycle ----------------
class TestWriterFlow:
    def test_create_draft_not_public(self, writer_t, state):
        payload = {"title": "TEST Writer draft story", "category": "Community",
                   "excerpt": "TEST standfirst", "body": SHORT_BODY}
        r = requests.post(f"{API}/writer/posts", headers=hdr(writer_t), json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        pid = r.json()["id"]
        state["posts"].append(pid)
        state["pid"] = pid

        g = requests.get(f"{API}/writer/posts/{pid}", headers=hdr(writer_t), timeout=30)
        assert g.status_code == 200, g.text[:300]
        post = g.json()["post"]
        assert post["status"] == "draft"
        assert post["title"] == payload["title"]
        slug = post["slug"]
        state["slug"] = slug

        pub = requests.get(f"{API}/blog", timeout=30).json()
        titles = [p["title"] for p in pub.get("items", [])]
        assert payload["title"] not in titles, "draft leaked onto public /blog"
        assert requests.get(f"{API}/blog/{slug}", timeout=30).status_code == 404

    def test_submit_short_story_refused(self, writer_t, state):
        r = requests.post(f"{API}/writer/posts/{state['pid']}/submit", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "80 words" in r.json().get("detail", ""), r.text[:300]

    def test_submit_long_story_moves_to_review(self, writer_t, state):
        up = requests.put(f"{API}/writer/posts/{state['pid']}", headers=hdr(writer_t), timeout=30,
                          json={"title": "TEST Writer draft story", "category": "Community",
                                "excerpt": "TEST standfirst", "body": LONG_BODY})
        assert up.status_code == 200, up.text[:300]
        r = requests.post(f"{API}/writer/posts/{state['pid']}/submit", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = requests.get(f"{API}/writer/posts", headers=hdr(writer_t), timeout=30).json()["items"]
        row = next(p for p in rows if p["id"] == state["pid"])
        assert row["status"] == "in_review", row

    def test_writer_cannot_publish(self, writer_t, state):
        r = requests.post(f"{API}/admin/blog/{state['pid']}/approve", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 403, r.text[:300]

    def test_editor_sees_in_review(self, admin_t, state):
        r = requests.get(f"{API}/admin/blog", headers=hdr(admin_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        row = next((p for p in r.json()["items"] if p["id"] == state["pid"]), None)
        assert row and row["status"] == "in_review", row

    def test_request_changes_requires_note(self, admin_t, state):
        r = requests.post(f"{API}/admin/blog/{state['pid']}/request-changes", headers=hdr(admin_t),
                          json={"note": "  "}, timeout=30)
        assert r.status_code == 400, r.text[:300]

    def test_request_changes_then_writer_sees_note(self, admin_t, writer_t, state):
        note = "TEST please add a quote from the venue owner."
        r = requests.post(f"{API}/admin/blog/{state['pid']}/request-changes", headers=hdr(admin_t),
                          json={"note": note}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        rows = requests.get(f"{API}/writer/posts", headers=hdr(writer_t), timeout=30).json()["items"]
        row = next(p for p in rows if p["id"] == state["pid"])
        assert row["status"] == "changes_requested", row
        assert row["review_note"] == note, row

    def test_writer_resubmits(self, writer_t, state):
        up = requests.put(f"{API}/writer/posts/{state['pid']}", headers=hdr(writer_t), timeout=30,
                          json={"title": "TEST Writer draft story", "category": "Community",
                                "excerpt": "TEST standfirst v2", "body": LONG_BODY})
        assert up.status_code == 200, up.text[:300]
        rows = requests.get(f"{API}/writer/posts", headers=hdr(writer_t), timeout=30).json()["items"]
        assert next(p for p in rows if p["id"] == state["pid"])["status"] == "draft"
        r = requests.post(f"{API}/writer/posts/{state['pid']}/submit", headers=hdr(writer_t), timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_approve_publishes_and_is_public(self, admin_t, state):
        r = requests.post(f"{API}/admin/blog/{state['pid']}/approve", headers=hdr(admin_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        pub = requests.get(f"{API}/blog/{state['slug']}", timeout=30)
        assert pub.status_code == 200, pub.text[:300]
        assert pub.json()["post"]["title"] == "TEST Writer draft story"

    def test_writer_cannot_edit_published(self, writer_t, state):
        r = requests.put(f"{API}/writer/posts/{state['pid']}", headers=hdr(writer_t), timeout=30,
                         json={"title": "TEST hijack", "category": "Community", "body": LONG_BODY})
        assert r.status_code == 403, r.text[:300]
        assert "live" in r.json().get("detail", "").lower(), r.text[:300]

    def test_writer_cannot_touch_another_authors_story(self, writer_t, admin_t):
        rows = requests.get(f"{API}/admin/blog", headers=hdr(admin_t), timeout=30).json()["items"]
        other = next((p for p in rows if p.get("author_slug") and p["author_slug"] != "aisha-rahman"), None)
        if not other:
            pytest.skip("no post by another author to test with")
        g = requests.get(f"{API}/writer/posts/{other['id']}", headers=hdr(writer_t), timeout=30)
        assert g.status_code in (403, 404), g.status_code
        p = requests.put(f"{API}/writer/posts/{other['id']}", headers=hdr(writer_t), timeout=30,
                         json={"title": "TEST hijack", "category": "Community", "body": LONG_BODY})
        assert p.status_code in (403, 404), p.status_code


# ---------------- ads admin CRUD ----------------
def iso_days(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).isoformat()


@pytest.fixture(scope="class")
def solo_ads(admin_t):
    """Pause pre-seeded ads (e.g. 'Skybar launch') so serving tests see only their own ad."""
    rows = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["items"]
    paused = []
    for a in rows:
        if a.get("status") == "active" and not a.get("name", "").startswith("TEST"):
            body = {k: a.get(k) for k in ("name", "headline", "body", "image", "cta_label", "url",
                                          "advertiser", "placements", "cities", "priority",
                                          "starts_at", "ends_at")}
            paused.append((a["id"], body, a.get("views", 0), a.get("clicks", 0)))
            requests.put(f"{API}/admin/ads/{a['id']}", headers=hdr(admin_t), timeout=30,
                         json=body | {"status": "paused"})
    yield
    for aid, body, views, clicks in paused:
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json=body | {"status": "active"})


class TestAdsAdmin:
    def test_admin_ads_shape(self, admin_t):
        r = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert {"items", "placements", "plans", "config"} <= set(d)
        assert [p["key"] for p in d["placements"]] == ["home", "events", "journal", "article",
                                                       "membership", "passes", "footer"]
        for it in d["items"]:
            assert "_id" not in it
            assert "ctr" in it and "views" in it and "clicks" in it

    def test_create_requires_placement(self, admin_t):
        r = requests.post(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30,
                          json={"name": "TEST No placement", "headline": "x", "url": "/events",
                                "placements": []})
        assert r.status_code in (400, 422), f"ad with no placement accepted: {r.status_code} {r.text[:200]}"

    def test_create_update_delete(self, admin_t, state):
        payload = {"name": "TEST Ad CRUD", "headline": "TEST headline", "body": "TEST body",
                   "url": "/events", "advertiser": "TEST Co", "placements": ["journal"],
                   "priority": 7, "status": "active"}
        c = requests.post(f"{API}/admin/ads", headers=hdr(admin_t), json=payload, timeout=30)
        assert c.status_code == 200, c.text[:300]
        aid = c.json()["id"]
        state["ads"].append(aid)

        rows = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["items"]
        row = next(a for a in rows if a["id"] == aid)
        assert row["placements"] == ["journal"] and row["priority"] == 7 and row["status"] == "active"

        u = requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                         json=payload | {"status": "paused", "priority": 3})
        assert u.status_code == 200, u.text[:300]
        rows = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["items"]
        row = next(a for a in rows if a["id"] == aid)
        assert row["status"] == "paused" and row["priority"] == 3

        d = requests.delete(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30)
        assert d.status_code == 200, d.text[:300]
        rows = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["items"]
        assert not any(a["id"] == aid for a in rows)
        state["ads"].remove(aid)

    def test_update_preserves_counters(self, admin_t, state):
        c = requests.post(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30,
                          json={"name": "TEST Counter keep", "headline": "h", "url": "/events",
                                "placements": ["passes"]})
        aid = c.json()["id"]
        state["ads"].append(aid)
        requests.get(f"{API}/ads", params={"placement": "passes"}, timeout=30)
        before = next(a for a in requests.get(f"{API}/admin/ads", headers=hdr(admin_t),
                                             timeout=30).json()["items"] if a["id"] == aid)
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json={"name": "TEST Counter keep", "headline": "h2", "url": "/events",
                           "placements": ["passes"]})
        after = next(a for a in requests.get(f"{API}/admin/ads", headers=hdr(admin_t),
                                            timeout=30).json()["items"] if a["id"] == aid)
        assert after["views"] >= before["views"] >= 1, (before, after)
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json={"name": "TEST Counter keep", "headline": "h2", "url": "/events",
                           "placements": ["passes"], "status": "paused"})

    def test_member_cannot_admin_ads(self, member_t):
        r = requests.get(f"{API}/admin/ads", headers=hdr(member_t), timeout=30)
        assert r.status_code == 403, r.status_code


# ---------------- ad serving ----------------
class TestAdServing:
    def test_unknown_placement_400(self):
        r = requests.get(f"{API}/ads", params={"placement": "nope"}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_serve_and_view_increment(self, admin_t, state):
        c = requests.post(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30,
                          json={"name": "TEST Serve home", "headline": "TEST serve headline",
                                "body": "b", "url": "https://example.com", "placements": ["home"],
                                "priority": 10, "status": "active"})
        aid = c.json()["id"]
        state["ads"].append(aid)
        state["serve_id"] = aid

        r = requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ad"] and d["ad"]["id"] == aid, d
        assert d["ad"]["headline"] == "TEST serve headline"
        assert "views" not in d["ad"] and "status" not in d["ad"], d["ad"]

        v1 = next(a for a in requests.get(f"{API}/admin/ads", headers=hdr(admin_t),
                                          timeout=30).json()["items"] if a["id"] == aid)["views"]
        requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30)
        v2 = next(a for a in requests.get(f"{API}/admin/ads", headers=hdr(admin_t),
                                          timeout=30).json()["items"] if a["id"] == aid)["views"]
        assert v2 == v1 + 1, (v1, v2)

    def test_click_increments_and_returns_url(self, admin_t, state):
        aid = state["serve_id"]
        r = requests.post(f"{API}/ads/{aid}/click", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["url"] == "https://example.com"
        row = next(a for a in requests.get(f"{API}/admin/ads", headers=hdr(admin_t),
                                           timeout=30).json()["items"] if a["id"] == aid)
        assert row["clicks"] >= 1 and row["ctr"] > 0, row

    def test_paused_not_served(self, admin_t, state):
        aid = state["serve_id"]
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json={"name": "TEST Serve home", "headline": "h", "url": "https://example.com",
                           "placements": ["home"], "priority": 10, "status": "paused"})
        d = requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()
        assert not d["ad"], d

    def test_expired_and_future_not_served(self, admin_t, state):
        aid = state["serve_id"]
        base = {"name": "TEST Serve home", "headline": "h", "url": "https://example.com",
                "placements": ["home"], "priority": 10, "status": "active"}
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json=base | {"ends_at": iso_days(-2)})
        assert not requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()["ad"]
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json=base | {"starts_at": iso_days(5)})
        assert not requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()["ad"]
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30, json=base)
        assert requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()["ad"]

    def test_city_targeting(self, admin_t, state):
        aid = state["serve_id"]
        base = {"name": "TEST Serve home", "headline": "h", "url": "https://example.com",
                "placements": ["home"], "priority": 10, "status": "active"}
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30,
                     json=base | {"cities": ["Mumbai"]})
        assert requests.get(f"{API}/ads", params={"placement": "home", "city": "Mumbai"},
                            timeout=30).json()["ad"]
        assert not requests.get(f"{API}/ads", params={"placement": "home", "city": "Dubai"},
                                timeout=30).json()["ad"]
        assert not requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()["ad"]
        requests.put(f"{API}/admin/ads/{aid}", headers=hdr(admin_t), timeout=30, json=base)

    def test_empty_placement_returns_nothing(self):
        d = requests.get(f"{API}/ads", params={"placement": "footer"}, timeout=30).json()
        assert d["ad"] is None and d["network"] is None, d


# ---------------- network fallback + hide for plans ----------------
class TestAdsConfig:
    def test_network_fallback_only_in_empty_slots(self, admin_t, state):
        r = requests.put(f"{API}/admin/ads-config", headers=hdr(admin_t), timeout=30,
                         json={"network_enabled": True, "network_client": "ca-pub-TEST123",
                               "network_slots": {"footer": "9988776655", "bogus": "x"},
                               "hide_for_plans": []})
        assert r.status_code == 200, r.text[:300]
        cfg = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["config"]
        assert cfg["network_enabled"] and cfg["network_client"] == "ca-pub-TEST123"
        assert "bogus" not in cfg["network_slots"], cfg

        empty = requests.get(f"{API}/ads", params={"placement": "footer"}, timeout=30).json()
        assert empty["network"] == {"client": "ca-pub-TEST123", "slot": "9988776655"}, empty
        assert empty["ad"] is None

        house = requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()
        assert house["ad"] and house["network"] is None, house

    def test_hide_for_plans(self, admin_t, member_t):
        me = requests.get(f"{API}/auth/me", headers=hdr(member_t), timeout=30).json()
        plan = (me.get("membership") or {}).get("plan_name") or ""
        plans = requests.get(f"{API}/admin/ads", headers=hdr(admin_t), timeout=30).json()["plans"]
        target = plan or (plans[0] if plans else "Premium Annual")
        requests.put(f"{API}/admin/ads-config", headers=hdr(admin_t), timeout=30,
                     json={"network_enabled": True, "network_client": "ca-pub-TEST123",
                           "network_slots": {}, "hide_for_plans": [target]})
        as_member = requests.get(f"{API}/ads", params={"placement": "home"}, headers=hdr(member_t),
                                 timeout=30).json()
        if plan and plan == target:
            assert as_member == {"ad": None, "network": None, "hidden": True}, as_member
        else:
            assert "hidden" in as_member, as_member
        anon = requests.get(f"{API}/ads", params={"placement": "home"}, timeout=30).json()
        assert anon["ad"], anon
        requests.put(f"{API}/admin/ads-config", headers=hdr(admin_t), timeout=30,
                     json={"network_enabled": False, "network_client": "", "network_slots": {},
                           "hide_for_plans": []})


# ---------------- advertise enquiry -> support inbox ----------------
class TestAdvertise:
    def test_enquiry_lands_in_support(self, admin_t):
        payload = {"name": "TEST Advertiser", "email": "test_advertiser@example.com",
                   "company": "TEST Skybar Group", "budget": "$2500",
                   "message": "TEST we would like the events list slot for August."}
        r = requests.post(f"{API}/advertise", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("message")

        threads = requests.get(f"{API}/admin/support", headers=hdr(admin_t), timeout=30)
        assert threads.status_code == 200, threads.text[:300]
        items = threads.json().get("items", threads.json() if isinstance(threads.json(), list) else [])
        t = next((x for x in items if x.get("email") == payload["email"]), None)
        assert t, f"advertise enquiry not in support inbox: {str(items)[:300]}"
        assert "Advertising enquiry" in t.get("subject", ""), t
        tid = t["id"]
        full = requests.get(f"{API}/admin/support/{tid}", headers=hdr(admin_t), timeout=30)
        assert full.status_code == 200, full.text[:300]
        body = str(full.json())
        assert "TEST Skybar Group" in body and "$2500" in body, body[:400]

    def test_validation(self):
        r = requests.post(f"{API}/advertise", json={"name": "x", "email": "bad", "message": "hi"},
                          timeout=30)
        assert r.status_code == 422, r.status_code


# ---------------- regression ----------------
class TestRegression:
    def test_public_journal(self):
        r = requests.get(f"{API}/blog", timeout=30)
        assert r.status_code == 200 and r.json().get("items"), r.text[:200]

    def test_author_page(self):
        r = requests.get(f"{API}/blog-authors/aisha-rahman", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"

    def test_seo_panel(self, admin_t):
        r = requests.get(f"{API}/admin/seo", headers=hdr(admin_t), timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_blog_export(self, admin_t):
        r = requests.get(f"{API}/admin/blog/export", headers=hdr(admin_t), timeout=60)
        assert r.status_code == 200 and r.json().get("posts") is not None

    def test_readers_report(self, admin_t):
        r = requests.get(f"{API}/admin/blog/insights", headers=hdr(admin_t), timeout=60)
        assert r.status_code in (200, 404), r.status_code

    def test_newsletter_signup(self):
        r = requests.post(f"{API}/newsletter/subscribe",
                          json={"email": "test_news53@example.com"}, timeout=30)
        assert r.status_code in (200, 201, 409), f"{r.status_code} {r.text[:200]}"
