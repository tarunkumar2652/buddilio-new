"""Iteration 38 — vendor payout runs, individual settlements, commission invoices, scorecards.

Seeds two TEST_ vendors (one on payout hold) with pending settlements in a dedicated period,
then exercises batching / CSV export / UTR marking / commission invoices / scorecards / RBAC.
"""
import os
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
PERIOD = "2026-06"
CREATED_AT = f"{PERIOD}-15T10:00:00+00:00"
DUE_ON = f"{PERIOD}-20T10:00:00+00:00"
CRON = os.environ["WEBHOOK_CRON_SECRET"]

BANK = {"bank_account_name": "TEST_ Payout Vendor A", "bank_account_number": "998877665544",
        "bank_ifsc": "HDFC0001234", "bank_name": "HDFC Bank", "bank_branch": "Bandra",
        "bank_account_type": "current", "bank_swift": "", "upi_id": ""}


def token(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    return hdr(token("admin@buddilio.com", "Admin@123"))


@pytest.fixture(scope="module")
def member():
    return hdr(token("arjun.sethi@example.com", "User@123"))


@pytest.fixture(scope="module")
def partner():
    return hdr(token("partner@buddilio.com", "Partner@123"))


@pytest.fixture(scope="module")
def seed(db):
    """Vendor A (payable, owned by the member) and Vendor B (payout hold), 2 + 1 pending settlements."""
    member_user = db.users.find_one({"email": "arjun.sethi@example.com"}, {"_id": 1})
    assert member_user, "member fixture user missing"
    a = db.vendor_profiles.insert_one({
        "legal_name": "TEST_ Payout Vendor A", "email": "test_payout_a@example.com",
        "user_id": str(member_user["_id"]), "status": "approved", "vendor_kind": "venue",
        "payout_hold": False, "pan": "AAACT1234A", "registered_address": "1 Test Road, Mumbai",
        **BANK}).inserted_id
    b = db.vendor_profiles.insert_one({
        "legal_name": "TEST_ Held Vendor B", "email": "test_payout_b@example.com",
        "user_id": "", "status": "approved", "vendor_kind": "venue",
        "payout_hold": True, "payout_hold_reason": "bank verification pending", **BANK}).inserted_id

    def s(vid, gross, commission, fee, net):
        return {"vendor_id": str(vid), "booking_id": f"TEST_{vid}_{gross}", "order_no": "TEST_ORDER",
                "gross": gross, "commission": commission, "platform_fee": fee, "refunds": 0.0,
                "adjustments": 0.0, "net": net, "currency": "INR", "status": "pending",
                "due_on": DUE_ON, "created_at": CREATED_AT}
    db.vendor_settlements.insert_many([s(a, 1000.0, 100.0, 50.0, 850.0), s(a, 2000.0, 200.0, 100.0, 1700.0),
                                       s(b, 500.0, 50.0, 25.0, 425.0)])
    yield {"a": str(a), "b": str(b)}
    ids = [str(a), str(b)]
    db.vendor_settlements.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_payout_batches.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_commission_invoices.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_profiles.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})


# ---------------- RBAC ----------------
class TestIteration38Payouts:
    """Single class so xdist --dist loadscope keeps the shared seed/batch state on one worker."""

    def test_anon_reads_401(self):
        for p in ["/admin/vendor-settlements", "/admin/vendor-payout-runs", "/admin/vendor-scorecards",
                  "/admin/vendor-commission-invoices"]:
            assert requests.get(f"{API}{p}", timeout=30).status_code == 401, p

    def test_member_forbidden(self, member, seed):
        assert requests.get(f"{API}/admin/vendor-settlements", headers=member, timeout=30).status_code == 403
        assert requests.post(f"{API}/admin/vendor-payout-runs", json={"due_only": False},
                             headers=member, timeout=30).status_code == 403
        assert requests.get(f"{API}/admin/vendor-scorecards", headers=member, timeout=30).status_code == 403

    def test_cron_requires_secret(self):
        assert requests.post(f"{API}/cron/commission-invoices", timeout=30).status_code == 401
        r = requests.post(f"{API}/cron/commission-invoices",
                          headers={"Authorization": f"Bearer {CRON}"}, timeout=30)
        assert r.status_code == 200 and r.json().get("ok") is True


# ---------------- settlements list + payout runs ----------------
    def test_settlements_list_shape(self, admin, seed):
        r = requests.get(f"{API}/admin/vendor-settlements", headers=admin, timeout=30)
        assert r.status_code == 200
        d = r.json()
        mine = [i for i in d["items"] if i["vendor_id"] in (seed["a"], seed["b"])]
        assert len(mine) == 3
        assert all("_id" not in i for i in d["items"])
        assert {i["vendor"]["legal_name"] for i in mine} == {"TEST_ Payout Vendor A", "TEST_ Held Vendor B"}
        for k in ("due", "batched", "paid", "commission", "platform_fee", "count"):
            assert k in d["totals"], k
        assert d["totals"]["due"] >= 2975.0
        assert d["held"] >= 1

    def test_create_batch_groups_and_skips_held(self, admin, seed, db):
        r = requests.post(f"{API}/admin/vendor-payout-runs", json={"due_only": False},
                          headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        batch = [b for b in d["created"] if b["vendor_id"] == seed["a"]]
        assert len(batch) == 1, "vendor A settlements must group into ONE batch"
        b = batch[0]
        assert b["count"] == 2 and b["net"] == 2550.0
        assert b["commission"] == 300.0 and b["platform_fee"] == 150.0
        assert b["batch_no"].startswith("BUD-PR-") and b["status"] == "open"
        assert b["bank"]["bank_ifsc"] == BANK["bank_ifsc"]
        assert "_id" not in b
        assert not [x for x in d["created"] if x["vendor_id"] == seed["b"]], "held vendor was batched"
        assert any("TEST_ Held Vendor B" == s["vendor"] for s in d["skipped"]), d["skipped"]
        rows = list(db.vendor_settlements.find({"vendor_id": seed["a"]}))
        assert {r_["status"] for r_ in rows} == {"batched"}
        assert {r_["batch_id"] for r_ in rows} == {b["id"] if "id" in b else b.get("_id")}
        held = list(db.vendor_settlements.find({"vendor_id": seed["b"]}))
        assert held[0]["status"] == "pending" and not held[0].get("batch_id")
        pytest.batch_id = b["id"]

    def test_list_batches_with_totals(self, admin):
        r = requests.get(f"{API}/admin/vendor-payout-runs", headers=admin, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert any(b["id"] == pytest.batch_id for b in d["items"])
        assert "open" in d["totals"] and "paid" in d["totals"]
        assert d["totals"]["open"] >= 2550.0

    def test_export_csv(self, admin):
        r = requests.get(f"{API}/admin/vendor-payout-runs/{pytest.batch_id}/export",
                         headers=admin, timeout=30)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("Beneficiary Name,Account Number,IFSC")
        assert BANK["bank_account_number"] in lines[1] and BANK["bank_ifsc"] in lines[1]
        assert "2550.00" in lines[1] and "BUD-PR-" in lines[1]

    def test_export_bad_id_404(self, admin):
        r = requests.get(f"{API}/admin/vendor-payout-runs/{'0' * 24}/export", headers=admin, timeout=30)
        assert r.status_code == 404

    def test_mark_paid_requires_utr(self, admin):
        r = requests.post(f"{API}/admin/vendor-payout-runs/{pytest.batch_id}/paid",
                          json={"utr": "   "}, headers=admin, timeout=30)
        assert r.status_code == 400 and "UTR" in r.json()["detail"]

    def test_mark_paid_and_notify(self, admin, seed, db):
        r = requests.post(f"{API}/admin/vendor-payout-runs/{pytest.batch_id}/paid",
                          json={"utr": "TEST_UTR_38"}, headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["utr"] == "TEST_UTR_38" and r.json()["net"] == 2550.0
        batch = db.vendor_payout_batches.find_one({"_id": ObjectId(pytest.batch_id)})
        assert batch["status"] == "paid" and batch["utr"] == "TEST_UTR_38"
        rows = list(db.vendor_settlements.find({"vendor_id": seed["a"]}))
        assert {x["status"] for x in rows} == {"paid"}
        assert {x["utr"] for x in rows} == {"TEST_UTR_38"}
        user_id = db.vendor_profiles.find_one({"_id": ObjectId(seed["a"])})["user_id"]
        assert db.notifications.count_documents({"user_id": user_id, "title": "Settlement transferred"}) >= 1

    def test_mark_paid_twice_rejected(self, admin):
        r = requests.post(f"{API}/admin/vendor-payout-runs/{pytest.batch_id}/paid",
                          json={"utr": "TEST_UTR_38B"}, headers=admin, timeout=30)
        assert r.status_code == 400


# ---------------- individual settlement ----------------
    def test_held_vendor_settlement_refused(self, admin, seed, db):
        sid = str(db.vendor_settlements.find_one({"vendor_id": seed["b"]})["_id"])
        r = requests.post(f"{API}/admin/vendor-settlements/{sid}/paid", json={"utr": "TEST_UTR_H"},
                          headers=admin, timeout=30)
        assert r.status_code == 400 and "hold" in r.json()["detail"].lower()

    def test_requires_utr_then_pays_and_rejects_repeat(self, admin, seed, db):
        db.vendor_profiles.update_one({"_id": ObjectId(seed["b"])}, {"$set": {"payout_hold": False}})
        sid = str(db.vendor_settlements.find_one({"vendor_id": seed["b"]})["_id"])
        r = requests.post(f"{API}/admin/vendor-settlements/{sid}/paid", json={"utr": ""},
                          headers=admin, timeout=30)
        assert r.status_code == 400, r.text
        r = requests.post(f"{API}/admin/vendor-settlements/{sid}/paid", json={"utr": "TEST_UTR_SINGLE"},
                          headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        row = db.vendor_settlements.find_one({"_id": ObjectId(sid)})
        assert row["status"] == "paid" and row["utr"] == "TEST_UTR_SINGLE"
        r = requests.post(f"{API}/admin/vendor-settlements/{sid}/paid", json={"utr": "TEST_UTR_SINGLE"},
                          headers=admin, timeout=30)
        assert r.status_code == 400
        db.vendor_profiles.update_one({"_id": ObjectId(seed["b"])}, {"$set": {"payout_hold": True}})

    def test_unknown_settlement_404(self, admin):
        r = requests.post(f"{API}/admin/vendor-settlements/{'0' * 24}/paid", json={"utr": "x"},
                          headers=admin, timeout=30)
        assert r.status_code == 404


# ---------------- commission invoices ----------------
    def test_generate_is_idempotent_and_numbered(self, admin, seed):
        r = requests.post(f"{API}/admin/vendor-commission-invoices/generate?period={PERIOD}",
                          headers=admin, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == PERIOD
        mine = [i for i in d["created"] if i["vendor_id"] in (seed["a"], seed["b"])]
        assert len(mine) == 2, d["created"]
        nos = sorted(i["invoice_no"] for i in mine)
        assert nos == [f"BUD-CI-{PERIOD}-0001", f"BUD-CI-{PERIOD}-0002"], nos
        a = next(i for i in mine if i["vendor_id"] == seed["a"])
        assert a["commission"] == 300.0 and a["platform_fee"] == 150.0
        assert a["total"] == 450.0 and a["bookings"] == 2
        assert a["vendor_settlement"] == 2550.0 and a["gross"] == 3000.0
        assert "_id" not in a
        pytest.inv_a = a["id"]

        again = requests.post(f"{API}/admin/vendor-commission-invoices/generate?period={PERIOD}",
                              headers=admin, timeout=60)
        assert again.status_code == 200
        created = again.json()["created"]
        assert [i["id"] for i in created if i["vendor_id"] == seed["a"]] == [pytest.inv_a]
        listed = requests.get(f"{API}/admin/vendor-commission-invoices?period={PERIOD}",
                              headers=admin, timeout=30).json()["items"]
        assert len([i for i in listed if i["vendor_id"] in (seed["a"], seed["b"])]) == 2

    def test_admin_list(self, admin):
        r = requests.get(f"{API}/admin/vendor-commission-invoices", headers=admin, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert any(i["id"] == pytest.inv_a for i in d["items"])
        assert isinstance(d["total"], (int, float))

    def test_vendor_sees_only_own(self, member, seed):
        r = requests.get(f"{API}/vendor/commission-invoices", headers=member, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items and all(i["vendor_id"] == seed["a"] for i in items)

    def test_pdf_for_owner_admin_and_403_for_other(self, admin, member, partner):
        for who, h in (("vendor", member), ("admin", admin)):
            r = requests.get(f"{API}/vendor-commission-invoices/{pytest.inv_a}/pdf", headers=h, timeout=60)
            assert r.status_code == 200, f"{who}: {r.status_code} {r.text[:200]}"
            assert r.headers.get("content-type") == "application/pdf"
            assert r.content[:4] == b"%PDF" and len(r.content) > 800
        r = requests.get(f"{API}/vendor-commission-invoices/{pytest.inv_a}/pdf", headers=partner, timeout=30)
        assert r.status_code == 403, r.status_code
        assert requests.get(f"{API}/vendor-commission-invoices/{'0' * 24}/pdf",
                            headers=admin, timeout=30).status_code == 404


# ---------------- scorecards ----------------
    def test_scorecards(self, admin, seed, db):
        r = requests.get(f"{API}/admin/vendor-scorecards", headers=admin, timeout=60)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items
        scores = [i["score"] for i in items]
        assert scores == sorted(scores), "must be sorted worst-first"
        for i in items:
            assert 0 <= i["score"] <= 100
            assert i["flag"] == ("green" if i["score"] >= 80 else "amber" if i["score"] >= 60 else "red")
            for k in ("cancel_rate", "rating", "complaints", "documents_complete", "payout_hold"):
                assert k in i, k
        held = next(i for i in items if i["vendor_id"] == seed["b"])
        assert held["payout_hold"] is True and held["documents_complete"] is False
        # FLAG ONLY: no auto suspension
        for vid in (seed["a"], seed["b"]):
            assert db.vendor_profiles.find_one({"_id": ObjectId(vid)})["status"] == "approved"
