"""Iteration 21 — public host directory/profile, follow toggle, follower notifications,
event recap card generation & caching, hidden photo exclusion.

Run serial (-n 0). Cleans up follows / notifications / recaps / seeded photos & events.
"""
import io
import os
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
API = f"{BASE.rstrip('/')}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("diya.sharma@example.com", "User@12345")
ATTENDEE = ("tara.joshi@example.com", "User@12345")

FINISHED_EVENT_ID = "6a7b73e34a13de566dbd110f"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def partner_tok():
    return _login(*PARTNER)


@pytest.fixture(scope="module")
def member_tok():
    return _login(*MEMBER)


@pytest.fixture(scope="module")
def attendee_tok():
    return _login(*ATTENDEE)


@pytest.fixture(scope="module")
def partner_id(partner_tok):
    r = requests.get(f"{API}/auth/me", headers=_hdr(partner_tok), timeout=30)
    return r.json()["id"]


# ================= HOST DIRECTORY =================
class TestHostDirectory:
    def test_list_hosts_public(self):
        r = requests.get(f"{API}/hosts", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data and "page" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 1
        # verified first (sorted verified desc)
        verified_flags = [h.get("verified", False) for h in data["items"]]
        if verified_flags and False in verified_flags and True in verified_flags:
            first_false = verified_flags.index(False)
            assert True not in verified_flags[first_false:], "verified hosts must come first"
        # required card fields
        h = data["items"][0]
        for key in ("id", "name", "events", "followers"):
            assert key in h, f"missing {key} in host card"

    def test_verified_only_filter(self):
        r = requests.get(f"{API}/hosts", params={"verified_only": True}, timeout=30)
        assert r.status_code == 200
        for h in r.json()["items"]:
            assert h.get("verified") is True

    def test_search_by_org_name(self):
        r = requests.get(f"{API}/hosts", params={"q": "Nightfall"}, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert any("nightfall" in (h.get("name") or "").lower() for h in items)


# ================= HOST PROFILE =================
class TestHostProfile:
    def test_profile_public_ok(self, partner_id):
        r = requests.get(f"{API}/hosts/{partner_id}", timeout=30)
        assert r.status_code == 200
        h = r.json()
        assert h["id"] == partner_id
        for key in ("name", "verified", "followers", "upcoming", "past", "photos", "reviews"):
            assert key in h
        assert isinstance(h["upcoming"], list)
        assert isinstance(h["past"], list)
        assert isinstance(h["photos"], list)
        assert h.get("is_following") is False  # guest

    def test_profile_not_found(self):
        r = requests.get(f"{API}/hosts/{ObjectId()}", timeout=30)
        assert r.status_code == 404

    def test_profile_bad_id(self):
        r = requests.get(f"{API}/hosts/not-a-valid-id", timeout=30)
        assert r.status_code == 400


# ================= FOLLOW / UNFOLLOW =================
class TestFollow:
    def test_follow_requires_auth(self, partner_id):
        r = requests.post(f"{API}/hosts/{partner_id}/follow", timeout=30)
        assert r.status_code in (401, 403)

    def test_follow_toggle_and_following_list(self, partner_id, member_tok, db):
        # Cleanup pre-existing follow row
        member_uid = requests.get(f"{API}/auth/me", headers=_hdr(member_tok)).json()["id"]
        db.host_follows.delete_many({"user_id": member_uid, "host_id": partner_id})
        try:
            baseline = requests.get(f"{API}/hosts/{partner_id}").json()["followers"]

            r1 = requests.post(f"{API}/hosts/{partner_id}/follow", headers=_hdr(member_tok), timeout=30)
            assert r1.status_code == 200
            j1 = r1.json()
            assert j1["following"] is True
            assert j1["followers"] == baseline + 1

            # my_following list
            lst = requests.get(f"{API}/me/following", headers=_hdr(member_tok), timeout=30).json()
            assert any(h["id"] == partner_id for h in lst["items"])

            # profile now shows is_following true for this user
            prof = requests.get(f"{API}/hosts/{partner_id}", headers=_hdr(member_tok)).json()
            assert prof["is_following"] is True
            assert prof["followers"] == baseline + 1

            # Toggle off
            r2 = requests.post(f"{API}/hosts/{partner_id}/follow", headers=_hdr(member_tok), timeout=30)
            assert r2.status_code == 200
            j2 = r2.json()
            assert j2["following"] is False
            assert j2["followers"] == baseline
        finally:
            db.host_follows.delete_many({"user_id": member_uid, "host_id": partner_id})


# ================= FOLLOWER NOTIFICATIONS =================
class TestFollowerNotifications:
    def test_notify_on_approve(self, partner_id, partner_tok, member_tok, admin_tok, db):
        member_uid = requests.get(f"{API}/auth/me", headers=_hdr(member_tok)).json()["id"]

        # Follow the partner
        db.host_follows.delete_many({"user_id": member_uid, "host_id": partner_id})
        requests.post(f"{API}/hosts/{partner_id}/follow", headers=_hdr(member_tok), timeout=30)

        # Create a submitted event as the partner
        payload = {
            "title": "TEST_iter21 follower alert night",
            "description": "TEST",
            "category": "music",
            "city": "Mumbai",
            "venue": "TEST venue",
            "starts_at": "2099-01-01T18:00:00Z",
            "ends_at": "2099-01-01T22:00:00Z",
            "capacity": 20,
            "price": 0,
            "cover_image": "",
        }
        r = requests.post(f"{API}/partner/events", json=payload, headers=_hdr(partner_tok), timeout=30)
        assert r.status_code in (200, 201), r.text
        eid = r.json().get("id") or r.json().get("_id")
        assert eid

        # Ensure event is 'submitted' (not published) so moderate/approve is a real transition
        db.events.update_one({"_id": ObjectId(eid)}, {"$set": {"status": "submitted"}})

        try:
            # Approve as admin
            mr = requests.post(f"{API}/admin/events/{eid}/moderate",
                               json={"action": "approve"}, headers=_hdr(admin_tok), timeout=30)
            assert mr.status_code == 200, mr.text
            assert mr.json()["status"] == "published"

            # notify_followers is fired via asyncio.create_task — give it a moment
            import time as _t
            for _ in range(20):
                notif = db.notifications.find_one({"user_id": member_uid, "link": f"/events/{eid}"})
                if notif:
                    break
                _t.sleep(0.25)
            assert notif is not None, "follower notification not created"
            assert "TEST_iter21" in (notif.get("title", "") + notif.get("body", ""))
        finally:
            db.notifications.delete_many({"link": f"/events/{eid}"})
            db.events.delete_one({"_id": ObjectId(eid)})
            db.host_follows.delete_many({"user_id": member_uid, "host_id": partner_id})


# ================= RECAP CARD =================
def _upload_jpg(tok, size=(400, 400), color=(200, 50, 90)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    files = {"file": ("photo.jpg", buf.getvalue(), "image/jpeg")}
    r = requests.post(f"{API}/uploads/file", headers=_hdr(tok), files=files, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _seed_photo(tok, caption="TEST_iter21 recap seed"):
    url = _upload_jpg(tok)
    r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                      json={"url": url, "caption": caption},
                      headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="class")
def clean_recap_state(db):
    # Purge existing photos on this event + recap cache before/after the class
    def _purge():
        rows = list(db.event_photos.find({"event_id": FINISHED_EVENT_ID}, {"_id": 1}))
        pids = [r["_id"] for r in rows]
        if pids:
            db.event_photos.delete_many({"_id": {"$in": pids}})
        cached = db.event_recaps.find_one({"event_id": FINISHED_EVENT_ID})
        if cached:
            # try to remove file registration too
            path = cached.get("card_url", "").replace("/api/files/", "")
            if path:
                db.files.delete_many({"path": path})
            db.event_recaps.delete_one({"event_id": FINISHED_EVENT_ID})
    _purge()
    yield
    _purge()


class TestRecap:
    def test_recap_get_empty(self, clean_recap_state):
        r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/recap", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for key in ("title", "city", "going", "photos", "photo_count", "card_url", "share_url", "can_make"):
            assert key in d
        assert d["photo_count"] == 0
        assert d["photos"] == []
        assert d["can_make"] is False  # guest

    def test_recap_post_requires_auth(self):
        r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/recap", timeout=30)
        assert r.status_code in (401, 403)

    def test_recap_post_400_when_empty(self, attendee_tok):
        r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/recap",
                          headers=_hdr(attendee_tok), timeout=30)
        assert r.status_code == 400

    def test_recap_generate_cache_and_signature_change(self, attendee_tok, db):
        pid1 = _seed_photo(attendee_tok, "TEST_iter21 first")

        r1 = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/recap",
                           headers=_hdr(attendee_tok), timeout=60)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["cached"] is False
        card_url_1 = j1["card_url"]
        assert card_url_1.startswith("/api/files/")

        # File is served
        served = requests.get(f"{BASE.rstrip('/')}{card_url_1}", timeout=30)
        assert served.status_code == 200
        assert served.headers.get("content-type", "").startswith("image/jpeg")
        # sanity — real JPEG bytes
        img = Image.open(io.BytesIO(served.content))
        assert img.size == (1080, 1350)

        # Second POST returns cached
        r2 = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/recap",
                           headers=_hdr(attendee_tok), timeout=60)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["cached"] is True
        assert j2["card_url"] == card_url_1

        # can_make True for authenticated user
        rget = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/recap",
                            headers=_hdr(attendee_tok), timeout=30).json()
        assert rget["photo_count"] >= 1
        assert rget["can_make"] is True
        assert rget["card_url"] == card_url_1

        # Add a new photo -> signature changes -> new card
        pid2 = _seed_photo(attendee_tok, "TEST_iter21 second")
        r3 = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/recap",
                           headers=_hdr(attendee_tok), timeout=60)
        assert r3.status_code == 200
        j3 = r3.json()
        assert j3["cached"] is False
        assert j3["card_url"] != card_url_1

    def test_hidden_photos_excluded(self, attendee_tok, admin_tok, db):
        # Ensure there's at least one photo, get its id
        rows = list(db.event_photos.find({"event_id": FINISHED_EVENT_ID}, {"_id": 1}).limit(1))
        assert rows, "expected seeded photos from previous test"
        pid = str(rows[0]["_id"])
        before = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/recap").json()["photo_count"]

        # Hide it via admin
        mr = requests.post(f"{API}/admin/photos/{pid}",
                           json={"action": "hide", "note": "TEST_iter21"},
                           headers=_hdr(admin_tok), timeout=30)
        assert mr.status_code == 200, mr.text
        try:
            after = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/recap").json()
            assert after["photo_count"] == before - 1
            urls = after["photos"]
            row = db.event_photos.find_one({"_id": ObjectId(pid)})
            assert row.get("url") not in urls

            # Host photo strip must also drop hidden photos: partner profile
            ev = db.events.find_one({"_id": ObjectId(FINISHED_EVENT_ID)}, {"partner_id": 1})
            if ev and ev.get("partner_id"):
                prof = requests.get(f"{API}/hosts/{ev['partner_id']}").json()
                host_urls = [p["url"] for p in prof.get("photos", [])]
                assert row.get("url") not in host_urls
        finally:
            # Restore
            requests.post(f"{API}/admin/photos/{pid}",
                          json={"action": "restore"}, headers=_hdr(admin_tok), timeout=30)
