"""Iteration 19 — Vendor verification queue, weekly payout reminders, event photo wall.

Runs against the live backend so we can catch integration bugs (auth, ObjectId leaks,
cron guard, idempotency). Cleanup: any TEST_* artefacts are wiped by conftest, and this
suite explicitly restores Skyline Sessions to pending/verified=false and deletes photos
created here so demo state is not polluted.
"""
import os
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE:
    # frontend env
    fe = Path("/app/frontend/.env").read_text()
    for line in fe.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"

CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER_ATTENDEE = ("tara.joshi@example.com", "User@123")
MEMBER_OTHER = ("diya.sharma@example.com", "User@123")

FINISHED_EVENT_ID = "6a7b73e34a13de566dbd110f"  # Rooftop Jazz & Tapas Night
SKYLINE_EMAIL = "invited.vendor@example.com"


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def manager_tok():
    return _login(*MANAGER)


@pytest.fixture(scope="module")
def partner_tok():
    return _login(*PARTNER)


@pytest.fixture(scope="module")
def attendee_tok():
    return _login(*MEMBER_ATTENDEE)


@pytest.fixture(scope="module")
def other_tok():
    return _login(*MEMBER_OTHER)


# --------------- Vendor verification queue ---------------

def _skyline_id(db):
    u = db.users.find_one({"email": SKYLINE_EMAIL}, {"_id": 1})
    assert u, "Skyline vendor missing"
    return str(u["_id"])


def test_admin_list_pending_shows_skyline(admin_tok, db):
    r = requests.get(f"{API}/admin/verifications?status=pending", headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "counts" in body
    ids = {i["id"] for i in body["items"]}
    assert _skyline_id(db) in ids, f"Skyline not in pending: {ids}"
    sky = next(i for i in body["items"] if i["id"] == _skyline_id(db))
    assert sky["document_count"] >= 1
    assert sky["verification_status"] == "pending"


def test_admin_approve_reject_reset_skyline(admin_tok, db):
    vid = _skyline_id(db)
    # approve
    r = requests.post(f"{API}/admin/verifications/{vid}",
                      json={"action": "approve", "note": "TEST_iter19 approve"}, headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "verified"
    assert r.json()["verified"] is True

    # verified list contains it
    r = requests.get(f"{API}/admin/verifications?status=verified", headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 200
    assert vid in {i["id"] for i in r.json()["items"]}

    # reject
    r = requests.post(f"{API}/admin/verifications/{vid}",
                      json={"action": "reject", "note": "TEST_iter19 reject"}, headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 200
    assert r.json()["verification_status"] == "rejected"

    # reset -> pending
    r = requests.post(f"{API}/admin/verifications/{vid}",
                      json={"action": "reset", "note": ""}, headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 200
    assert r.json()["verification_status"] == "pending"

    # restore demo state: pending / verified=false / clear note+verified_at
    db.users.update_one({"_id": ObjectId(vid)},
                        {"$set": {"verification_status": "pending", "verified": False,
                                  "verification_note": "", "verified_at": ""}})


def test_approve_zero_documents_returns_400(admin_tok, db):
    # find a partner with no documents
    partner = db.users.find_one({"role": "partner",
                                  "$or": [{"documents": {"$exists": False}}, {"documents": []}]}, {"_id": 1})
    if not partner:
        pytest.skip("no doc-less partner available")
    vid = str(partner["_id"])
    r = requests.post(f"{API}/admin/verifications/{vid}",
                      json={"action": "approve", "note": ""}, headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 400, r.text


def test_non_admin_forbidden(manager_tok, partner_tok, attendee_tok, db):
    vid = _skyline_id(db)
    for tok in (manager_tok, partner_tok, attendee_tok):
        r = requests.get(f"{API}/admin/verifications", headers=_hdr(tok), timeout=30)
        assert r.status_code == 403, f"GET expected 403, got {r.status_code}"
        r = requests.post(f"{API}/admin/verifications/{vid}",
                          json={"action": "approve"}, headers=_hdr(tok), timeout=30)
        assert r.status_code == 403


def test_invalid_action_returns_400(admin_tok, db):
    vid = _skyline_id(db)
    r = requests.post(f"{API}/admin/verifications/{vid}",
                      json={"action": "boop"}, headers=_hdr(admin_tok), timeout=30)
    assert r.status_code == 400


# --------------- Event partner_verified on public event ---------------

def test_public_event_returns_partner_verified():
    r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}", timeout=30)
    assert r.status_code == 200, r.text
    assert "partner_verified" in r.json()


# --------------- Cron: payout reminders ---------------

def test_cron_payout_reminders_auth():
    r = requests.post(f"{API}/cron/payout-reminders", timeout=30)
    assert r.status_code == 401
    r = requests.post(f"{API}/cron/payout-reminders",
                      headers={"Authorization": "Bearer wrong"}, timeout=30)
    assert r.status_code == 401
    r = requests.post(f"{API}/cron/payout-reminders",
                      headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("queued") == "payout-reminders"
    assert "week" in body


def test_cron_payout_reminders_idempotency_and_happy_path(db):
    """Create a temp pending payout for a vendor managed by ops.manager, fire the cron,
    check exactly one payout_reminders row (or already present) and no duplicate on repeat."""
    manager = db.users.find_one({"email": MANAGER[0]}, {"_id": 1})
    assert manager
    mid = str(manager["_id"])
    vendor = db.users.find_one({"role": "partner", "managed_by": mid}, {"_id": 1})
    if not vendor:
        pytest.skip("ops.manager has no vendor")

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    payout_doc = {
        "partner_id": str(vendor["_id"]),
        "event_id": "TEST_iter19_event",
        "event_title": "TEST_iter19 payout",
        "currency": "INR",
        "net": 1234.0,
        "status": "pending",
        "created_at": now_iso,
    }
    ins = db.payouts.insert_one(payout_doc)

    # capture existing week reminder if any
    y, w, _ = datetime.now(timezone.utc).isocalendar()
    wk = f"{y}-W{w:02d}"
    existed_before = db.payout_reminders.find_one({"manager_id": mid, "week": wk}) is not None

    try:
        r = requests.post(f"{API}/cron/payout-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r.status_code == 200
        # give the background task time to write the reminder row
        for _ in range(20):
            time.sleep(0.5)
            if db.payout_reminders.find_one({"manager_id": mid, "week": wk}):
                break

        row = db.payout_reminders.find_one({"manager_id": mid, "week": wk})
        if not existed_before:
            assert row is not None, "expected a payout_reminders row after cron"

        # Fire again: idempotent — count must not increase
        count_before = db.payout_reminders.count_documents({"manager_id": mid, "week": wk})
        r2 = requests.post(f"{API}/cron/payout-reminders",
                           headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r2.status_code == 200
        time.sleep(2)
        count_after = db.payout_reminders.count_documents({"manager_id": mid, "week": wk})
        assert count_after == count_before, "duplicate reminder written for same manager/week"
    finally:
        db.payouts.delete_one({"_id": ins.inserted_id})
        # remove the reminder we may have just created (only if it was created by us)
        if not existed_before:
            db.payout_reminders.delete_many({"manager_id": mid, "week": wk})


# --------------- Event photo wall ---------------

def test_photos_guest_reason():
    r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/photos", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["can_post"] is False
    assert body["reason"], "guest should see reason"
    assert body["max_per_member"] == 10


def _upload_test_file(tok):
    files = {"file": ("test.jpg", b"\xff\xd8\xff\xe0test-jpg-bytes", "image/jpeg")}
    r = requests.post(f"{API}/uploads/file", headers=_hdr(tok), files=files, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["url"]


def test_photo_post_and_authorization(attendee_tok, other_tok, admin_tok, db):
    """Happy path for confirmed attendee, plus non-attendee 403, bad url 400, delete authz."""
    # confirm attendee is participant
    me = requests.get(f"{API}/auth/me", headers=_hdr(attendee_tok), timeout=30).json()
    part = db.event_participants.find_one({"event_id": FINISHED_EVENT_ID, "user_id": me["id"]})
    assert part and part.get("status") == "confirmed", "tara must be confirmed attendee of finished event"

    # bad url
    r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                      json={"url": "https://elsewhere.example/pic.jpg"},
                      headers=_hdr(attendee_tok), timeout=30)
    assert r.status_code == 400

    # good url via upload
    url = _upload_test_file(attendee_tok)
    assert url.startswith("/api/files/")
    r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                      json={"url": url, "caption": "TEST_iter19 vibe"}, headers=_hdr(attendee_tok), timeout=30)
    assert r.status_code == 200, r.text
    photo = r.json()
    assert photo["ok"] is True and "id" in photo
    # response must NOT leak ObjectId '_id'
    assert "_id" not in photo, f"ObjectId leaked: {photo}"
    pid = photo["id"]

    try:
        # non-attendee cannot post — pick a member NOT in the participants for this event
        parts = list(db.event_participants.find({"event_id": FINISHED_EVENT_ID}, {"user_id": 1}))
        part_ids = {p["user_id"] for p in parts}
        candidate = db.users.find_one({"email": {"$regex": "@example.com$"},
                                        "_id": {"$nin": [ObjectId(u) for u in part_ids]}},
                                       {"email": 1})
        assert candidate, "no non-attendee member available"
        non_tok = _login(candidate["email"], "User@123")
        url2 = _upload_test_file(non_tok)
        r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                          json={"url": url2}, headers=_hdr(non_tok), timeout=30)
        assert r.status_code == 403, r.text

        # non-owner (other member) cannot delete
        r = requests.delete(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}",
                            headers=_hdr(non_tok), timeout=30)
        assert r.status_code == 403

        # admin can delete
        r = requests.delete(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}",
                            headers=_hdr(admin_tok), timeout=30)
        assert r.status_code == 200
    finally:
        # ensure no leftover
        db.event_photos.delete_one({"_id": ObjectId(pid)})


def test_photo_wall_future_event_400(attendee_tok, db):
    """POST to an event that has not started yet returns 400."""
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    ev_doc = {
        "title": "TEST_iter19 future event",
        "status": "published",
        "starts_at": future,
        "ends_at": future,
        "city": "Delhi NCR",
        "category": "food",
        "price": 0,
        "partner_id": "",
        "created_at": future,
    }
    ins = db.events.insert_one(ev_doc)
    eid = str(ins.inserted_id)
    # attempt post (no participant check reached because starts_at gate fires first per code)
    try:
        url = _upload_test_file(attendee_tok)
        r = requests.post(f"{API}/events/{eid}/photos", json={"url": url},
                          headers=_hdr(attendee_tok), timeout=30)
        assert r.status_code == 400, r.text
    finally:
        db.events.delete_one({"_id": ins.inserted_id})


def test_photo_wall_max_10(attendee_tok, db):
    """Seed 10 photos then verify 11th returns 400. Cleanup after."""
    me = requests.get(f"{API}/auth/me", headers=_hdr(attendee_tok), timeout=30).json()
    uid = me["id"]
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    seeded = []
    try:
        # any pre-existing count from tara on this event
        existing = db.event_photos.count_documents({"event_id": FINISHED_EVENT_ID, "user_id": uid})
        needed = 10 - existing
        for i in range(needed):
            ins = db.event_photos.insert_one({"event_id": FINISHED_EVENT_ID, "user_id": uid,
                                              "url": "/api/files/seed.jpg", "caption": f"TEST_iter19 {i}",
                                              "created_at": now_iso})
            seeded.append(ins.inserted_id)
        url = _upload_test_file(attendee_tok)
        r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                          json={"url": url}, headers=_hdr(attendee_tok), timeout=30)
        assert r.status_code == 400, f"expected 400 at 11th photo, got {r.status_code} {r.text}"
    finally:
        if seeded:
            db.event_photos.delete_many({"_id": {"$in": seeded}})


def test_cleanup_tara_photos_on_finished_event(db):
    """Best-effort: remove any TEST_iter19 photos left behind on the finished event."""
    res = db.event_photos.delete_many({"event_id": FINISHED_EVENT_ID,
                                        "caption": {"$regex": "^TEST_iter19"}})
    print(f"cleanup removed {res.deleted_count} TEST_iter19 photos")
