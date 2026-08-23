"""Iteration 20 — photo wall moderation, verified organiser filter, payout reminder preview.

Runs serial. Restores demo state (Skyline pending; partner2 verified True; no leftover
photos/payouts/reminder rows) at teardown.
"""
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
API = f"{BASE.rstrip('/')}/api"

CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
PARTNER2 = ("partner2@buddilio.com", "Partner@123")
MEMBER_ATTENDEE = ("tara.joshi@example.com", "User@12345")   # confirmed on finished event
MEMBER_REPORTER = ("diya.sharma@example.com", "User@12345")

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
def manager_tok():
    return _login(*MANAGER)


@pytest.fixture(scope="module")
def partner_tok():
    return _login(*PARTNER)


@pytest.fixture(scope="module")
def attendee_tok():
    return _login(*MEMBER_ATTENDEE)


@pytest.fixture(scope="module")
def reporter_tok():
    return _login(*MEMBER_REPORTER)


# ---------- helpers ----------

def _upload(tok):
    files = {"file": ("t.jpg", b"\xff\xd8\xff\xe0test", "image/jpeg")}
    r = requests.post(f"{API}/uploads/file", headers=_hdr(tok), files=files, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["url"]


def _seed_photo(db, owner_tok):
    """Attendee (tara) posts a photo on the finished event via the API. Returns pid."""
    url = _upload(owner_tok)
    r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                      json={"url": url, "caption": "TEST_iter20 vibe"},
                      headers=_hdr(owner_tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ================= PHOTO REPORT (member) =================

class TestPhotoReport:
    def test_report_others_photo_idempotent(self, attendee_tok, reporter_tok, admin_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            # 1st report -> report_count 1, reports row inserted, target_type photo
            r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                              json={"reason": "TEST_iter20 test reason"},
                              headers=_hdr(reporter_tok), timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is True

            row = db.event_photos.find_one({"_id": ObjectId(pid)})
            assert row["report_count"] == 1
            reporter_uid = requests.get(f"{API}/auth/me", headers=_hdr(reporter_tok)).json()["id"]
            assert reporter_uid in row.get("reported_by", [])

            rep = db.reports.find_one({"target_type": "photo", "target_id": pid})
            assert rep is not None
            assert rep["reporter_id"] == reporter_uid
            assert rep["status"] == "open"

            # 2nd report by same user -> idempotent, no increment
            r2 = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                               json={"reason": "again"}, headers=_hdr(reporter_tok), timeout=30)
            assert r2.status_code == 200
            row2 = db.event_photos.find_one({"_id": ObjectId(pid)})
            assert row2["report_count"] == 1
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.reports.delete_many({"target_type": "photo", "target_id": pid})

    def test_cannot_report_own_photo(self, attendee_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            r = requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                              json={"reason": "self"}, headers=_hdr(attendee_tok), timeout=30)
            assert r.status_code == 400, r.text
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})

    def test_reported_photo_visible_publicly_until_hidden(self, attendee_tok, reporter_tok, admin_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                          json={"reason": "TEST_iter20"}, headers=_hdr(reporter_tok), timeout=30)
            # still visible to guest
            r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/photos", timeout=30)
            assert pid in {i["id"] for i in r.json()["items"]}

            # admin hides
            r = requests.post(f"{API}/admin/photos/{pid}",
                              json={"action": "hide", "note": "TEST_iter20 hide"},
                              headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200

            # guest cannot see it now
            r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/photos", timeout=30)
            assert pid not in {i["id"] for i in r.json()["items"]}

            # admin still sees it (hidden:true items)
            r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}/photos",
                             headers=_hdr(admin_tok), timeout=30)
            assert pid in {i["id"] for i in r.json()["items"]}
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.reports.delete_many({"target_type": "photo", "target_id": pid})


# ================= ADMIN PHOTO MODERATION =================

class TestAdminPhotoModeration:
    def test_non_admin_forbidden(self, manager_tok, partner_tok, reporter_tok):
        for tok in (manager_tok, partner_tok, reporter_tok):
            r = requests.get(f"{API}/admin/photos", headers=_hdr(tok), timeout=30)
            assert r.status_code == 403, f"GET expected 403 got {r.status_code}"
            r = requests.post(f"{API}/admin/photos/000000000000000000000000",
                              json={"action": "hide"}, headers=_hdr(tok), timeout=30)
            assert r.status_code == 403

    def test_unknown_action_returns_400(self, admin_tok, attendee_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            r = requests.post(f"{API}/admin/photos/{pid}",
                              json={"action": "boop"}, headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 400
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})

    def test_filters_and_counts(self, admin_tok, attendee_tok, reporter_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                          json={"reason": "TEST_iter20 f"}, headers=_hdr(reporter_tok), timeout=30)
            r = requests.get(f"{API}/admin/photos?status=reported", headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200
            body = r.json()
            assert "items" in body and "counts" in body
            assert body["counts"]["reported"] >= 1
            assert pid in {i["id"] for i in body["items"]}

            # hide it and confirm counts.hidden increases
            requests.post(f"{API}/admin/photos/{pid}",
                          json={"action": "hide"}, headers=_hdr(admin_tok), timeout=30)
            r = requests.get(f"{API}/admin/photos?status=hidden", headers=_hdr(admin_tok), timeout=30)
            assert pid in {i["id"] for i in r.json()["items"]}
            r = requests.get(f"{API}/admin/photos?status=all", headers=_hdr(admin_tok), timeout=30)
            assert pid in {i["id"] for i in r.json()["items"]}
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.reports.delete_many({"target_type": "photo", "target_id": pid})

    def test_hide_with_warn_increments_warnings_and_writes_audit(self, admin_tok, attendee_tok, reporter_tok, db):
        pid = _seed_photo(db, attendee_tok)
        owner = db.users.find_one({"email": MEMBER_ATTENDEE[0]}, {"warnings": 1})
        warnings_before = owner.get("warnings", 0) if owner else 0
        try:
            requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                          json={"reason": "TEST_iter20"}, headers=_hdr(reporter_tok), timeout=30)
            r = requests.post(f"{API}/admin/photos/{pid}",
                              json={"action": "hide", "note": "TEST_iter20 warn me", "warn": True},
                              headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["warned"] is True
            assert body["action"] == "hide"

            owner2 = db.users.find_one({"email": MEMBER_ATTENDEE[0]}, {"warnings": 1})
            assert owner2["warnings"] == warnings_before + 1

            # reports row resolved
            rep = db.reports.find_one({"target_type": "photo", "target_id": pid})
            assert rep and rep["status"] == "resolved" and rep["resolution"] == "hide"

            # audit
            aud = db.audit_logs.find_one({"action": "photo.hide", "entity_id": pid})
            assert aud is not None
        finally:
            # restore warnings
            db.users.update_one({"email": MEMBER_ATTENDEE[0]}, {"$set": {"warnings": warnings_before}})
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.reports.delete_many({"target_type": "photo", "target_id": pid})
            db.audit_logs.delete_many({"entity_id": pid})

    def test_restore_clears_reports(self, admin_tok, attendee_tok, reporter_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            requests.post(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}/report",
                          json={"reason": "TEST_iter20"}, headers=_hdr(reporter_tok), timeout=30)
            requests.post(f"{API}/admin/photos/{pid}", json={"action": "hide"},
                          headers=_hdr(admin_tok), timeout=30)
            r = requests.post(f"{API}/admin/photos/{pid}", json={"action": "restore"},
                              headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200
            row = db.event_photos.find_one({"_id": ObjectId(pid)})
            assert row.get("hidden") in (False, None) or row.get("hidden") is False
            assert row.get("report_count", 0) == 0
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.reports.delete_many({"target_type": "photo", "target_id": pid})
            db.audit_logs.delete_many({"entity_id": pid})

    def test_delete_removes_photo(self, admin_tok, attendee_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            r = requests.post(f"{API}/admin/photos/{pid}", json={"action": "delete"},
                              headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200
            assert db.event_photos.find_one({"_id": ObjectId(pid)}) is None
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})
            db.audit_logs.delete_many({"entity_id": pid})


# ================= VERIFIED-ORGANISER FILTER =================

class TestVerifiedFilter:
    def test_partner_verified_present_on_list(self):
        r = requests.get(f"{API}/events?limit=5", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "no events"
        for e in items:
            assert "partner_verified" in e

    def test_verified_only_excludes_unverified(self, db):
        p2 = db.users.find_one({"email": PARTNER2[0]}, {"verified": 1})
        assert p2, "partner2 missing"
        p2_id = str(p2["_id"])
        original = bool(p2.get("verified"))
        try:
            # baseline: verified_only=true count with everyone verified
            r_all = requests.get(f"{API}/events?verified_only=true&limit=100", timeout=30)
            assert r_all.status_code == 200
            base_count = r_all.json()["total"]

            # flip partner2 to unverified
            db.users.update_one({"_id": p2["_id"]}, {"$set": {"verified": False}})

            r_flt = requests.get(f"{API}/events?verified_only=true&limit=100", timeout=30)
            new_count = r_flt.json()["total"]
            assert new_count < base_count, (
                f"filter should exclude some events (base={base_count}, filtered={new_count})")
            ids_filtered = {e["id"] for e in r_flt.json()["items"]}

            # without the flag, partner2 events still appear
            r_open = requests.get(f"{API}/events?limit=100", timeout=30)
            ids_open = {e["id"] for e in r_open.json()["items"]}
            p2_events = list(db.events.find({"partner_id": p2_id, "status": "published"}, {"_id": 1}).limit(5))
            if p2_events:
                p2_ev_ids = {str(e["_id"]) for e in p2_events}
                # p2 events should not be in filtered result
                assert not (p2_ev_ids & ids_filtered), "unverified partner events leaked through verified_only"
                # but should be in open result
                assert (p2_ev_ids & ids_open), "partner2 events missing from unfiltered list"
        finally:
            db.users.update_one({"_id": p2["_id"]}, {"$set": {"verified": original}})


# ================= PAYOUT REMINDER PREVIEW =================

class TestPayoutReminderPreview:
    def test_member_and_partner_forbidden(self, reporter_tok, partner_tok):
        for tok in (reporter_tok, partner_tok):
            r = requests.get(f"{API}/console/payout-reminder", headers=_hdr(tok), timeout=30)
            assert r.status_code == 403

    def test_manager_preview_shape(self, manager_tok):
        r = requests.get(f"{API}/console/payout-reminder", headers=_hdr(manager_tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("subject", "intro", "items", "total", "currency", "schedule",
                  "next_send_at", "already_sent_this_week", "will_send"):
            assert k in body, f"missing {k}"
        assert body["schedule"] == "Every Monday, 09:00 IST"
        # next_send_at is a future Monday 03:30 UTC
        nsa = datetime.fromisoformat(body["next_send_at"].replace("Z", "+00:00"))
        assert nsa > datetime.now(timezone.utc)
        assert nsa.weekday() == 0
        assert nsa.hour == 3 and nsa.minute == 30

    def test_admin_can_also_call(self, admin_tok):
        r = requests.get(f"{API}/console/payout-reminder", headers=_hdr(admin_tok), timeout=30)
        assert r.status_code == 200

    def test_pending_payout_shows_in_preview_and_flips_will_send(self, manager_tok, db):
        manager = db.users.find_one({"email": MANAGER[0]}, {"_id": 1})
        mid = str(manager["_id"])
        vendor = db.users.find_one({"role": "partner", "managed_by": mid},
                                    {"org_name": 1, "full_name": 1})
        if not vendor:
            pytest.skip("ops.manager has no vendor")
        vname = vendor.get("org_name") or vendor.get("full_name")

        # baseline
        base = requests.get(f"{API}/console/payout-reminder",
                            headers=_hdr(manager_tok), timeout=30).json()

        now_iso = datetime.now(timezone.utc).isoformat()
        ins = db.payouts.insert_one({
            "partner_id": str(vendor["_id"]), "event_id": "TEST_iter20_event",
            "event_title": "TEST_iter20 payout", "currency": "INR", "net": 4321.0,
            "status": "pending", "created_at": now_iso})
        try:
            r = requests.get(f"{API}/console/payout-reminder",
                             headers=_hdr(manager_tok), timeout=30)
            assert r.status_code == 200
            body = r.json()
            assert body["will_send"] is True
            assert body["total"] >= 4321.0
            vendors_in_items = {i["vendor"] for i in body["items"]}
            assert vname in vendors_in_items, f"vendor {vname} not in items {vendors_in_items}"
        finally:
            db.payouts.delete_one({"_id": ins.inserted_id})

        # confirm returned to baseline
        after = requests.get(f"{API}/console/payout-reminder",
                             headers=_hdr(manager_tok), timeout=30).json()
        assert after["will_send"] == base["will_send"]

    def test_already_sent_this_week(self, manager_tok, db):
        manager = db.users.find_one({"email": MANAGER[0]}, {"_id": 1})
        mid = str(manager["_id"])
        # ISO week
        y, w, _ = datetime.now(timezone.utc).isocalendar()
        wk = f"{y}-W{w:02d}"
        existed = db.payout_reminders.find_one({"manager_id": mid, "week": wk})
        if existed:
            db.payout_reminders.delete_one({"_id": existed["_id"]})
        ins = db.payout_reminders.insert_one({
            "manager_id": mid, "week": wk, "payouts": 0, "total": 0,
            "email_sent": True, "created_at": datetime.now(timezone.utc).isoformat()})
        try:
            r = requests.get(f"{API}/console/payout-reminder",
                             headers=_hdr(manager_tok), timeout=30)
            assert r.status_code == 200
            assert r.json()["already_sent_this_week"] is True
        finally:
            db.payout_reminders.delete_one({"_id": ins.inserted_id})
            if existed:
                existed.pop("_id", None)
                db.payout_reminders.insert_one(existed)


# ================= REGRESSION =================

class TestRegression:
    def test_public_event_returns_partner_verified(self):
        r = requests.get(f"{API}/events/{FINISHED_EVENT_ID}", timeout=30)
        assert r.status_code == 200
        assert "partner_verified" in r.json()

    def test_cron_payout_reminders_auth(self):
        assert requests.post(f"{API}/cron/payout-reminders", timeout=30).status_code == 401
        r = requests.post(f"{API}/cron/payout-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r.status_code == 200

    def test_delete_photo_authz_preserved(self, attendee_tok, reporter_tok, db):
        pid = _seed_photo(db, attendee_tok)
        try:
            r = requests.delete(f"{API}/events/{FINISHED_EVENT_ID}/photos/{pid}",
                                headers=_hdr(reporter_tok), timeout=30)
            assert r.status_code == 403
        finally:
            db.event_photos.delete_one({"_id": ObjectId(pid)})


# ================= FINAL CLEANUP =================

def test_zz_final_cleanup(db):
    """Best-effort — wipe any TEST_iter20 leftovers on the finished event."""
    r1 = db.event_photos.delete_many({"event_id": FINISHED_EVENT_ID,
                                       "caption": {"$regex": "^TEST_iter20"}})
    r2 = db.reports.delete_many({"reason": {"$regex": "TEST_iter20"}})
    r3 = db.payouts.delete_many({"event_id": "TEST_iter20_event"})
    print(f"cleanup photos={r1.deleted_count} reports={r2.deleted_count} payouts={r3.deleted_count}")
