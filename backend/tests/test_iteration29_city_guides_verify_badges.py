"""Iteration 29 — auto city guides, verification reminders, trusted verified badges.
Run: pytest tests/test_iteration29_city_guides_verify_badges.py -v -n 0
"""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]

ADMIN = ("admin@buddilio.com", "Admin@123")
TARA = ("tara.joshi@example.com", "User@123")
AARAV = ("aarav.mehta@example.com", "User@123")
ANANYA = ("ananya.kapoor@example.com", "User@123")


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"{email}: {r.status_code} {r.text}"
    j = r.json()
    return j["access_token"], j["user"]


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------
# 1. Auto city guides
# ------------------------------------------------------------------
class TestAutoCityGuides:
    AUTO_CITIES = ["lisbon", "oslo"]           # in COUNTRY_SEED but no editorial guide
    CUSTOM_CITIES = ["delhi-ncr", "dubai", "london"]

    @pytest.fixture(autouse=True, scope="class")
    def _cleanup(self):
        yield
        DB.city_guides.delete_many({"slug": {"$in": ["delhi-ncr", "lisbon", "oslo"]}})
        DB.countries.delete_many({"code": "ZQ"})

    def test_auto_guide_for_uncurated_city(self):
        for slug in self.AUTO_CITIES:
            r = requests.get(f"{BASE_URL}/api/cities/{slug}", timeout=30)
            assert r.status_code == 200, f"{slug}: {r.text}"
            g = r.json().get("guide") or {}
            assert g.get("auto") is True, f"{slug} should have auto=True"
            assert g.get("intro") and len(g["intro"]) > 20
            areas = g.get("areas") or []
            assert len(areas) == 4, f"{slug} areas={len(areas)}"
            for a in areas:
                # each area = [name, blurb, photo_url]
                assert len(a) >= 3 and a[2].startswith("http"), f"{slug} area missing photo: {a}"
            for k in ("when", "around", "tip"):
                assert g.get(k), f"{slug} missing {k}"

    def test_auto_guide_page_works_with_zero_events(self):
        # oslo/lisbon should have no events but page still returns 200 with a guide
        r = requests.get(f"{BASE_URL}/api/cities/oslo", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j.get("events_total", 0) == 0
        assert j["guide"].get("auto") is True

    def test_custom_guides_untouched(self):
        for slug in self.CUSTOM_CITIES:
            r = requests.get(f"{BASE_URL}/api/cities/{slug}", timeout=30)
            assert r.status_code == 200
            g = r.json().get("guide") or {}
            assert "auto" not in g, f"{slug} unexpectedly auto: {g.get('auto')}"
            assert g.get("intro")
            assert len(g.get("areas") or []) >= 4

    def test_admin_city_guides_listing(self):
        tok, _ = _login(*ADMIN)
        r = requests.get(f"{BASE_URL}/api/admin/city-guides", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 150
        by_slug = {i["slug"]: i for i in items}
        # editorial cities: custom=False, auto=False
        for slug in ("delhi-ncr", "dubai", "london"):
            assert slug in by_slug, slug
            assert by_slug[slug]["custom"] is False
            assert by_slug[slug]["auto"] is False
        # uncurated cities: custom=False, auto=True
        for slug in ("lisbon", "oslo"):
            assert slug in by_slug, slug
            assert by_slug[slug]["custom"] is False
            assert by_slug[slug]["auto"] is True

    def test_put_overrides_auto_guide(self):
        tok, _ = _login(*ADMIN)
        payload = {"guide": {"intro": "TEST override for lisbon", "areas": [
            ["Bairro Alto", "Bars all night", "https://example.com/1.jpg"],
            ["Alfama", "Fado houses", "https://example.com/2.jpg"],
            ["LX Factory", "Warehouse art", "https://example.com/3.jpg"],
            ["Belém", "Pastel de nata", "https://example.com/4.jpg"],
        ], "when": "Fri/Sat", "around": "Metro + tram", "tip": "Book fado early."}}
        r = requests.put(f"{BASE_URL}/api/admin/city-guides/lisbon",
                         json=payload, headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text

        # listing now flags custom
        items = requests.get(f"{BASE_URL}/api/admin/city-guides", headers=_h(tok)).json()["items"]
        row = next(i for i in items if i["slug"] == "lisbon")
        assert row["custom"] is True
        assert row["auto"] is False

        # public city page shows override, no auto flag
        pg = requests.get(f"{BASE_URL}/api/cities/lisbon", timeout=30).json()
        assert pg["guide"]["intro"].startswith("TEST override")
        assert "auto" not in pg["guide"]

    def test_delete_resets_to_auto_guide(self):
        tok, _ = _login(*ADMIN)
        # first ensure override exists (from previous test), otherwise create
        DB.city_guides.update_one({"slug": "lisbon"},
                                  {"$set": {"slug": "lisbon", "city": "Lisbon",
                                            "data": {"intro": "temp"}}}, upsert=True)
        r = requests.delete(f"{BASE_URL}/api/admin/city-guides/lisbon",
                            headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("guide", {}).get("auto") is True

        # public page returns auto guide again — never empty
        pg = requests.get(f"{BASE_URL}/api/cities/lisbon", timeout=30).json()
        assert pg["guide"].get("auto") is True
        assert pg["guide"].get("intro")

    def test_admin_only_writes(self):
        tara_tok, _ = _login(*TARA)
        r = requests.put(f"{BASE_URL}/api/admin/city-guides/lisbon",
                         json={"guide": {"intro": "no"}}, headers=_h(tara_tok))
        assert r.status_code == 403
        r = requests.delete(f"{BASE_URL}/api/admin/city-guides/lisbon", headers=_h(tara_tok))
        assert r.status_code == 403

    def test_new_admin_city_reachable_without_restart(self):
        tok, _ = _login(*ADMIN)
        payload = {"code": "ZQ", "name": "Testquadia", "currency": "USD",
                   "tax_percent": 5, "tax_label": "TST", "emergency": "911",
                   "cities": ["TESTGuideville"], "active": True}
        r = requests.post(f"{BASE_URL}/api/admin/countries",
                          json=payload, headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        # slug is lowercased hyphenated
        r = requests.get(f"{BASE_URL}/api/cities/testguideville", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["country"] == "Testquadia"
        assert j["guide"].get("auto") is True
        assert len(j["guide"].get("areas") or []) == 4


# ------------------------------------------------------------------
# 2. Verification reminders
# ------------------------------------------------------------------
class TestVerificationReminders:
    @pytest.fixture(autouse=True, scope="class")
    def _cleanup(self):
        yield
        DB.users.update_many({"email": {"$in": [TARA[0], AARAV[0]]}},
                             {"$unset": {"id_verification_started": "", "id_verification": ""},
                              "$set": {"verified": False}})
        # Ananya is a verified companion in the seed — put her back or the hangouts suite loses its host.
        DB.users.update_one({"email": ANANYA[0]},
                            {"$unset": {"id_verification_started": "", "id_verification": ""},
                             "$set": {"verified": True}})
        # restore aarav to unverified (test flips it True temporarily) — original was False
        DB.notifications.delete_many({"title": "Finish your ID check",
                                      "user_id": {"$in": [
                                          str((DB.users.find_one({"email": TARA[0]}) or {}).get("_id", "")),
                                      ]}})

    def test_start_records_for_unverified(self):
        # ensure tara is not verified and clear state
        DB.users.update_one({"email": TARA[0]},
                            {"$set": {"verified": False},
                             "$unset": {"id_verification_started": "", "id_verification": ""}})
        tok, _ = _login(*TARA)
        r = requests.post(f"{BASE_URL}/api/me/verification/start",
                          json={"doc_type": "passport"}, headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["started"] is True
        doc = DB.users.find_one({"email": TARA[0]}, {"id_verification_started": 1})
        started = doc.get("id_verification_started") or {}
        assert started.get("doc_type") == "passport"
        assert started.get("reminders") == 0
        assert started.get("at")

    def test_start_is_noop_for_verified(self):
        DB.users.update_one({"email": TARA[0]}, {"$set": {"verified": True}})
        try:
            tok, _ = _login(*TARA)
            r = requests.post(f"{BASE_URL}/api/me/verification/start",
                              json={"doc_type": "aadhaar"}, headers=_h(tok), timeout=30)
            assert r.status_code == 200
            assert r.json()["started"] is False
        finally:
            DB.users.update_one({"email": TARA[0]}, {"$set": {"verified": False}})

    def test_cron_requires_bearer(self):
        r = requests.post(f"{BASE_URL}/api/cron/verification-reminders", timeout=30)
        assert r.status_code == 401
        r = requests.post(f"{BASE_URL}/api/cron/verification-reminders",
                          headers={"Authorization": "Bearer wrong"}, timeout=30)
        assert r.status_code == 401

    def test_cron_acks_quickly_with_secret(self):
        r = requests.post(f"{BASE_URL}/api/cron/verification-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("queued") == "verification-reminders"

    def test_worker_notifies_only_eligible(self):
        # Directly invoke send_verification_reminders via HTTP is async — instead test
        # by making sure DB shows the increment after the worker runs.
        # Setup: tara — started 25h ago, no submission, reminders=0  → should be nudged
        # Setup: aarav — started 25h ago, HAS submission, reminders=0 → skipped
        # Setup: ananya — started 25h ago, reminders=2 → skipped (over cap)
        import datetime as _dt
        long_ago = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=25)
        ts = long_ago.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        # clean slate for the three users
        DB.users.update_one({"email": TARA[0]},
                            {"$unset": {"id_verification": ""},
                             "$set": {"verified": False,
                                      "id_verification_started": {"doc_type": "passport",
                                                                  "at": ts, "reminders": 0}}})
        DB.users.update_one({"email": AARAV[0]},
                            {"$set": {"verified": False,
                                      "id_verification": {"status": "pending",
                                                          "doc_type": "passport",
                                                          "documents": [{"url": "/api/files/x"}],
                                                          "submitted_at": ts},
                                      "id_verification_started": {"doc_type": "passport",
                                                                  "at": ts, "reminders": 0}}})
        DB.users.update_one({"email": ANANYA[0]},
                            {"$unset": {"id_verification": ""},
                             "$set": {"verified": False,
                                      "id_verification_started": {"doc_type": "passport",
                                                                  "at": ts, "reminders": 2}}})

        tara_id = str(DB.users.find_one({"email": TARA[0]})["_id"])
        aarav_id = str(DB.users.find_one({"email": AARAV[0]})["_id"])
        ananya_id = str(DB.users.find_one({"email": ANANYA[0]})["_id"])
        DB.notifications.delete_many({"title": "Finish your ID check",
                                      "user_id": {"$in": [tara_id, aarav_id, ananya_id]}})

        # fire cron
        r = requests.post(f"{BASE_URL}/api/cron/verification-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r.status_code == 200

        # background task — wait for it
        import time as _t
        for _ in range(20):
            _t.sleep(0.5)
            tara_doc = DB.users.find_one({"email": TARA[0]}, {"id_verification_started": 1})
            if (tara_doc.get("id_verification_started") or {}).get("reminders") == 1:
                break
        else:
            pytest.fail("worker did not increment tara's reminder count within 10s")

        # tara nudged: reminders 0->1, has notification
        assert DB.notifications.count_documents(
            {"user_id": tara_id, "title": "Finish your ID check"}) >= 1

        # aarav skipped (has submission)
        aarav_doc = DB.users.find_one({"email": AARAV[0]}, {"id_verification_started": 1})
        assert (aarav_doc.get("id_verification_started") or {}).get("reminders") == 0
        assert DB.notifications.count_documents(
            {"user_id": aarav_id, "title": "Finish your ID check"}) == 0

        # ananya skipped (at cap)
        ananya_doc = DB.users.find_one({"email": ANANYA[0]}, {"id_verification_started": 1})
        assert (ananya_doc.get("id_verification_started") or {}).get("reminders") == 2
        assert DB.notifications.count_documents(
            {"user_id": ananya_id, "title": "Finish your ID check"}) == 0

    def test_worker_never_sends_third_reminder(self):
        # After first fire tara is at reminders=1. Fire again → 2. Fire once more → still 2.
        import time as _t
        r = requests.post(f"{BASE_URL}/api/cron/verification-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        assert r.status_code == 200
        for _ in range(20):
            _t.sleep(0.5)
            d = DB.users.find_one({"email": TARA[0]}, {"id_verification_started": 1})
            if (d.get("id_verification_started") or {}).get("reminders") == 2:
                break
        else:
            pytest.fail("worker didn't reach reminders=2")

        # third invocation should not push past 2
        requests.post(f"{BASE_URL}/api/cron/verification-reminders",
                      headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
        _t.sleep(3)
        d = DB.users.find_one({"email": TARA[0]}, {"id_verification_started": 1})
        assert (d.get("id_verification_started") or {}).get("reminders") == 2


# ------------------------------------------------------------------
# 3. Trusted "verified" badges in the API
# ------------------------------------------------------------------
class TestVerifiedBadges:
    @pytest.fixture(autouse=True, scope="class")
    def _reset(self):
        # snapshot original verified flags to restore later
        anan = DB.users.find_one({"email": ANANYA[0]}, {"verified": 1})
        tara = DB.users.find_one({"email": TARA[0]}, {"verified": 1})
        original = {ANANYA[0]: bool(anan.get("verified")), TARA[0]: bool(tara.get("verified"))}
        yield
        for email, val in original.items():
            DB.users.update_one({"email": email}, {"$set": {"verified": val}})

    def test_companions_list_exposes_verified(self):
        # Companions list requires companion.verified=True — make sure Ananya qualifies
        DB.users.update_one({"email": ANANYA[0]}, {"$set": {"verified": True}})
        tok, _ = _login(*AARAV)
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert items, "expected at least one companion (ananya)"
        for it in items:
            assert "verified" in it, f"companion {it.get('id')} missing verified key"
            assert isinstance(it["verified"], bool)

    def test_companion_detail_exposes_verified(self):
        tok, _ = _login(*AARAV)
        anan_id = str(DB.users.find_one({"email": ANANYA[0]})["_id"])
        r = requests.get(f"{BASE_URL}/api/companions/{anan_id}", headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        assert "verified" in r.json()

    def test_verified_flag_flips_across_apis(self):
        anan_id = str(DB.users.find_one({"email": ANANYA[0]})["_id"])
        tok, _ = _login(*AARAV)

        # Flip verified=True
        DB.users.update_one({"_id": ObjectId(anan_id)}, {"$set": {"verified": True}})

        # /api/users/{id}
        r = requests.get(f"{BASE_URL}/api/users/{anan_id}", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        assert r.json().get("verified") is True

        # /api/companions/{id}
        r = requests.get(f"{BASE_URL}/api/companions/{anan_id}", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        assert r.json().get("verified") is True

        # /api/companions list
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(tok), timeout=30)
        row = next((c for c in r.json()["items"] if c["id"] == anan_id), None)
        assert row and row["verified"] is True

        # Flip back False
        DB.users.update_one({"_id": ObjectId(anan_id)}, {"$set": {"verified": False}})
        r = requests.get(f"{BASE_URL}/api/users/{anan_id}", headers=_h(tok), timeout=30)
        assert r.json().get("verified") is False
        r = requests.get(f"{BASE_URL}/api/companions/{anan_id}", headers=_h(tok), timeout=30)
        assert r.json().get("verified") is False

    def test_discover_exposes_verified(self):
        tok, _ = _login(*AARAV)
        r = requests.get(f"{BASE_URL}/api/discover", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert items
        for it in items:
            assert "verified" in it
            assert isinstance(it["verified"], bool)

        # Flip a discover member to verified and confirm it flows through
        target = items[0]
        DB.users.update_one({"_id": ObjectId(target["id"])}, {"$set": {"verified": True}})
        try:
            r = requests.get(f"{BASE_URL}/api/discover", headers=_h(tok), timeout=30)
            row = next((i for i in r.json()["items"] if i["id"] == target["id"]), None)
            assert row and row["verified"] is True
        finally:
            DB.users.update_one({"_id": ObjectId(target["id"])},
                                {"$set": {"verified": bool(target.get("verified"))}})
