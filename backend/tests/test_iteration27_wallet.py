"""Iteration 27 — wallet top-up, saved card, auto-charge, fee waiver, ratings.

Covers everything the review-request asks for:
  * GET/POST /api/wallet + /api/wallet/topup (min/max, tax-free, ledger, idempotent fulfilment).
  * PUT/DELETE /api/wallet/card, no full PAN persisted, autopay=false skipped.
  * Auto-charge order on accept: wallet -> card -> stays payment_due.
  * Fee waiver quota (default 3), 4th falls back to fee, quota=0 disables.
  * POST /api/bookings/{bid}/rate + GET /api/admin/companion-ratings (partner 403).

Run: pytest backend/tests/test_iteration27_wallet.py -v -n 0
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
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

ADMIN = ("admin@buddilio.com", "Admin@123")
TARA = ("tara.joshi@example.com", "User@123")
ANANYA = ("ananya.kapoor@example.com", "User@123")
ARJUN = ("arjun.sethi@example.com", "User@123")
PARTNER = ("partner@buddilio.com", "Partner@123")

ANANYA_SEED = {
    "hourly_rate": 1500.0, "min_hours": 2, "max_hours": 5,
    "headline": "Great dinner company", "about": "I love food and jazz.",
    "city": "Mumbai", "languages": ["English", "Hindi"],
    "packages": [{"label": "Dinner evening", "hours": 3, "price": 4000.0}],
    "enabled": True, "status": "approved", "completed": 0, "rating": 0, "rating_count": 0,
}


def _login(e, p):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": e, "password": p}, timeout=30)
    assert r.status_code == 200, f"{e}: {r.text}"
    j = r.json()
    return j["access_token"], j["user"]


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _starts(h=5):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


def _pay_wallet(tok, topup_id, expected_amount):
    o = requests.post(f"{BASE_URL}/api/checkout", headers=_h(tok),
                      json={"kind": "wallet", "item_id": topup_id, "use_credit": False})
    assert o.status_code == 200, o.text
    order = o.json()["order"]
    assert order["total"] == expected_amount, f"tax leaked: {order}"
    assert order["tax"] == 0
    v = requests.post(f"{BASE_URL}/api/payments/verify", headers=_h(tok),
                      json={"order_id": order["id"]})
    assert v.status_code == 200
    return order


def _pay_companion(tok, bid):
    o = requests.post(f"{BASE_URL}/api/checkout", headers=_h(tok),
                      json={"kind": "companion", "item_id": bid, "use_credit": False})
    assert o.status_code == 200, o.text
    order = o.json()["order"]
    v = requests.post(f"{BASE_URL}/api/payments/verify", headers=_h(tok),
                      json={"order_id": order["id"]})
    assert v.status_code == 200
    return order


@pytest.fixture(scope="module")
def sessions():
    out = {}
    for k, (e, p) in {"admin": ADMIN, "tara": TARA, "ananya": ANANYA,
                      "arjun": ARJUN, "partner": PARTNER}.items():
        tok, u = _login(e, p)
        u_db = DB.users.find_one({"email": e}, {"_id": 1})
        out[k] = {"token": tok, "user": u, "id": str(u_db["_id"])}
    return out


@pytest.fixture(scope="module", autouse=True)
def prep_and_cleanup(sessions):
    plan = DB.membership_plans.find_one({"name": "Basic"})
    tara_id = sessions["tara"]["id"]
    ana_id = sessions["ananya"]["id"]
    DB.user_memberships.delete_many({"test_marker": "iter27_wallet"})
    DB.user_memberships.insert_one({
        "user_id": tara_id, "plan_id": str(plan["_id"]), "plan_name": plan["name"],
        "status": "active", "starts_at": datetime.now(timezone.utc).isoformat(),
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        "order_id": "", "test_marker": "iter27_wallet",
        "created_at": datetime.now(timezone.utc).isoformat()})
    DB.credits.delete_many({"user_id": tara_id})
    DB.companion_bookings.delete_many({"$or": [{"member_id": tara_id}, {"companion_id": ana_id}]})
    DB.payouts.delete_many({"kind": "companion"})
    DB.orders.delete_many({"user_id": tara_id, "kind": {"$in": ["companion", "wallet"]}})
    DB.wallet_topups.delete_many({"user_id": tara_id})
    DB.companion_ratings.delete_many({"companion_id": ana_id})
    DB.users.update_one({"_id": ObjectId(tara_id)}, {"$unset": {"saved_card": ""}})
    DB.settings.update_one({}, {"$set": {"hangout_request_fee": 100, "hangout_free_requests": 3},
                                "$unset": {"companions_min_plan": ""}})
    yield
    # teardown
    DB.user_memberships.delete_many({"test_marker": "iter27_wallet"})
    booking_ids = [str(b["_id"]) for b in DB.companion_bookings.find(
        {"$or": [{"member_id": tara_id}, {"companion_id": ana_id}]}, {"_id": 1})]
    if booking_ids:
        DB.companion_bookings.delete_many({"_id": {"$in": [ObjectId(b) for b in booking_ids]}})
        DB.payouts.delete_many({"booking_id": {"$in": booking_ids}})
        DB.credits.delete_many({"booking_id": {"$in": booking_ids}})
        DB.orders.delete_many({"kind": "companion", "ref_id": {"$in": booking_ids}})
    DB.credits.delete_many({"user_id": tara_id})
    DB.orders.delete_many({"user_id": tara_id, "kind": {"$in": ["companion", "wallet"]}})
    DB.wallet_topups.delete_many({"user_id": tara_id})
    DB.companion_ratings.delete_many({"companion_id": ana_id})
    DB.users.update_one({"_id": ObjectId(tara_id)}, {"$unset": {"saved_card": ""}})
    DB.users.update_one({"_id": ObjectId(ana_id)}, {"$set": {"companion": {
        **ANANYA_SEED,
        "accepted_terms_at": datetime.now(timezone.utc).isoformat(),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "rejected_reason": "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }}})
    DB.settings.update_one({}, {"$set": {"hangout_request_fee": 100, "hangout_free_requests": 3},
                                "$unset": {"companions_min_plan": ""}})
    print("[cleanup] iter27 wallet artefacts purged, Ananya restored, quotas reset")


@pytest.fixture(autouse=True)
def _isolate(sessions):
    tara_id = sessions["tara"]["id"]
    ana_id = sessions["ananya"]["id"]
    DB.companion_bookings.update_many(
        {"$or": [{"member_id": tara_id}, {"companion_id": ana_id}],
         "status": {"$in": ["pending_request_fee", "pending_payment", "awaiting_acceptance",
                            "payment_due", "counter_offered"]}},
        {"$set": {"status": "cancelled"}})
    yield


# 1. GET /wallet shape
class TestWalletGet:
    def test_shape_and_defaults(self, sessions):
        r = requests.get(f"{BASE_URL}/api/wallet", headers=_h(sessions["tara"]["token"]))
        assert r.status_code == 200
        j = r.json()
        for k in ("balance", "entries", "card", "min_topup", "max_topup", "free_requests_left"):
            assert k in j
        assert j["min_topup"] == 500
        assert j["max_topup"] == 200000
        assert isinstance(j["entries"], list)
        assert j["free_requests_left"] == 3  # member, quota 3, no bookings yet


# 2. Top up limits & idempotence
class TestTopUp:
    def test_below_min_rejected(self, sessions):
        r = requests.post(f"{BASE_URL}/api/wallet/topup",
                          headers=_h(sessions["tara"]["token"]), json={"amount": 100})
        assert r.status_code == 400

    def test_above_max_rejected(self, sessions):
        r = requests.post(f"{BASE_URL}/api/wallet/topup",
                          headers=_h(sessions["tara"]["token"]), json={"amount": 250000})
        assert r.status_code == 400

    def test_topup_tax_free_and_ledger(self, sessions):
        tok = sessions["tara"]["token"]
        DB.credits.delete_many({"user_id": sessions["tara"]["id"]})
        before = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()["balance"]
        t = requests.post(f"{BASE_URL}/api/wallet/topup", headers=_h(tok),
                          json={"amount": 2500}).json()
        assert t["checkout"]["kind"] == "wallet"
        assert t["checkout"]["amount"] == 2500
        order = _pay_wallet(tok, t["topup_id"], 2500)
        w = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()
        assert round(w["balance"] - before, 2) == 2500
        top_entry = w["entries"][0]
        assert top_entry["amount"] == 2500
        assert "top-up" in top_entry["reason"].lower()
        return order

    def test_topup_cannot_fulfil_twice(self, sessions):
        tok = sessions["tara"]["token"]
        DB.credits.delete_many({"user_id": sessions["tara"]["id"]})
        t = requests.post(f"{BASE_URL}/api/wallet/topup", headers=_h(tok),
                          json={"amount": 1000}).json()
        order = _pay_wallet(tok, t["topup_id"], 1000)
        bal_after_first = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()["balance"]
        # replay verify — must not double-credit
        requests.post(f"{BASE_URL}/api/payments/verify", headers=_h(tok),
                      json={"order_id": order["id"]})
        bal_after_replay = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()["balance"]
        assert bal_after_first == bal_after_replay


# 3. Saved card
class TestSavedCard:
    def test_put_stores_no_pan(self, sessions):
        tok = sessions["tara"]["token"]
        r = requests.put(f"{BASE_URL}/api/wallet/card", headers=_h(tok),
                         json={"name": "T Joshi", "number": "4242424242424242",
                               "exp_month": 12, "exp_year": 2030, "autopay": True})
        assert r.status_code == 200
        j = r.json()
        assert j["card"]["last4"] == "4242"
        assert j["card"]["brand"] == "Visa"
        db_row = DB.users.find_one({"_id": ObjectId(sessions["tara"]["id"])}, {"saved_card": 1})
        sc = db_row["saved_card"]
        assert sc.get("last4") == "4242"
        # full PAN must not be persisted anywhere on the doc
        for k, v in sc.items():
            assert "4242424242424242" not in str(v), f"leaked PAN in {k}"
        assert "number" not in sc
        assert "pan" not in sc

    def test_invalid_number_rejected(self, sessions):
        tok = sessions["tara"]["token"]
        r = requests.put(f"{BASE_URL}/api/wallet/card", headers=_h(tok),
                         json={"name": "T", "number": "12", "exp_month": 5, "exp_year": 2030})
        assert r.status_code == 400

    def test_delete_removes_card(self, sessions):
        tok = sessions["tara"]["token"]
        requests.put(f"{BASE_URL}/api/wallet/card", headers=_h(tok),
                     json={"name": "T", "number": "4242424242424242",
                           "exp_month": 5, "exp_year": 2030, "autopay": True})
        r = requests.delete(f"{BASE_URL}/api/wallet/card", headers=_h(tok))
        assert r.status_code == 200
        assert r.json()["card"] is None
        w = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()
        assert w["card"] is None


# 4. Auto-charge order of preference on accept
class TestAutoCharge:
    def _burn_free_requests(self, sessions):
        """Push Tara past the 3-free-request quota so subsequent bookings cost the fee."""
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 0}})

    def test_wallet_covers(self, sessions):
        self._burn_free_requests(sessions)
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})
        DB.credits.insert_one({"user_id": tara_id, "amount": 5000.0, "type": "grant",
                               "reason": "seed", "created_at": datetime.now(timezone.utc).isoformat()})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(6), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay_companion(tok, bid)   # pay the fee
        pre = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()["balance"]
        acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                            headers=_h(ana_tok), json={"amount": 3000})
        assert acc.status_code == 200
        assert acc.json()["paid_from"] == "wallet"
        assert acc.json()["status"] == "confirmed"
        post = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()["balance"]
        assert round(pre - post, 2) == 3000
        p = DB.payouts.find_one({"booking_id": bid})
        assert p["net"] == 2250 and p["fee"] == 750
        DB.credits.delete_many({"user_id": tara_id})
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})

    def test_saved_card_when_wallet_short(self, sessions):
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 0}})
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})
        requests.put(f"{BASE_URL}/api/wallet/card", headers=_h(tok),
                     json={"name": "Tara", "number": "4111111111111111",
                           "exp_month": 5, "exp_year": 2030, "autopay": True})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(7), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay_companion(tok, bid)
        acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                            headers=_h(ana_tok), json={"amount": 3000})
        assert acc.status_code == 200, acc.text
        assert acc.json()["paid_from"] == "card"
        assert acc.json()["status"] == "confirmed"
        # a "saved_card_sim" order + captured payment row exist
        sim_order = DB.orders.find_one({"user_id": tara_id, "kind": "companion",
                                         "gateway": "saved_card_sim", "ref_id": bid})
        assert sim_order is not None
        pay = DB.payments.find_one({"order_id": str(sim_order["_id"])})
        assert pay["status"] == "captured"
        p = DB.payouts.find_one({"booking_id": bid})
        assert p["net"] == 2250 and p["fee"] == 750
        requests.delete(f"{BASE_URL}/api/wallet/card", headers=_h(tok))
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})

    def test_no_wallet_no_card_stays_payment_due(self, sessions):
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 0}})
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})
        requests.delete(f"{BASE_URL}/api/wallet/card", headers=_h(tok))
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(8), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay_companion(tok, bid)
        acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                            headers=_h(ana_tok), json={"amount": 3000})
        assert acc.status_code == 200
        assert acc.json()["status"] == "payment_due"
        b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "payment_due"
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})

    def test_autopay_false_skipped(self, sessions):
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 0}})
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})
        requests.put(f"{BASE_URL}/api/wallet/card", headers=_h(tok),
                     json={"name": "Tara", "number": "4111111111111111",
                           "exp_month": 5, "exp_year": 2030, "autopay": False})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(9), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay_companion(tok, bid)
        acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                            headers=_h(ana_tok), json={"amount": 3000})
        assert acc.status_code == 200
        assert acc.json()["status"] == "payment_due"
        requests.delete(f"{BASE_URL}/api/wallet/card", headers=_h(tok))
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})


# 5. Fee waiver
class TestFeeWaiver:
    def test_first_three_waived_fourth_paid(self, sessions):
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok = sessions["tara"]["token"]
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})
        # ensure no bookings this month
        DB.companion_bookings.delete_many({"member_id": tara_id})
        for i in range(3):
            r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings",
                              headers=_h(tok),
                              json={"hours": 2, "starts_at": _starts(5 + i),
                                    "accept_terms": True})
            assert r.status_code == 200, r.text
            j = r.json()
            assert j["next"] == "sent"
            assert j["fee_waived"] is True
            assert j["request_fee"] == 0
            assert j["booking"]["status"] == "awaiting_acceptance"
            assert j["booking"]["due_amount"] == 0
            assert j["free_requests_left"] == 3 - (i + 1)
            # close it so the next request doesn't hit the "already have a request waiting" guard
            DB.companion_bookings.update_one({"_id": ObjectId(j["booking"]["id"])},
                                             {"$set": {"status": "cancelled"}})
        # 4th
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(20), "accept_terms": True})
        j = r.json()
        assert j["next"] == "checkout"
        assert j["fee_waived"] is False
        assert j["request_fee"] == 100
        assert j["booking"]["status"] == "pending_request_fee"

    def test_quota_zero_disables(self, sessions):
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok = sessions["tara"]["token"]
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 0}})
        DB.companion_bookings.delete_many({"member_id": tara_id})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(5), "accept_terms": True})
        j = r.json()
        assert j["next"] == "checkout"
        assert j["fee_waived"] is False
        w = requests.get(f"{BASE_URL}/api/wallet", headers=_h(tok)).json()
        assert w["free_requests_left"] == 0
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})

    def test_non_member_no_waiver(self, sessions):
        # arjun has no membership → premium gate 403 anyway; wallet also returns free=0
        r = requests.get(f"{BASE_URL}/api/wallet", headers=_h(sessions["arjun"]["token"]))
        assert r.status_code == 200
        assert r.json()["free_requests_left"] == 0


# 6. Ratings
class TestRatings:
    def _complete_a_booking(self, sessions):
        tara_id, ana_id = sessions["tara"]["id"], sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})
        DB.companion_bookings.delete_many({"member_id": tara_id})
        DB.credits.delete_many({"user_id": tara_id})
        DB.credits.insert_one({"user_id": tara_id, "amount": 5000.0, "type": "grant",
                               "reason": "seed", "created_at": datetime.now(timezone.utc).isoformat()})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(5), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        # waived free -> awaiting_acceptance directly
        acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                            headers=_h(ana_tok), json={"amount": 3000})
        assert acc.json()["status"] == "confirmed"
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        DB.companion_bookings.update_one({"_id": ObjectId(bid)}, {"$set": {"starts_at": past}})
        requests.post(f"{BASE_URL}/api/bookings/{bid}/complete", headers=_h(tok))
        return bid

    def test_rate_and_admin_only_note(self, sessions):
        ana_id = sessions["ananya"]["id"]
        tok, ana_tok = sessions["tara"]["token"], sessions["ananya"]["token"]
        DB.companion_ratings.delete_many({"companion_id": ana_id})
        bid = self._complete_a_booking(sessions)

        # invalid star
        r_bad = requests.post(f"{BASE_URL}/api/bookings/{bid}/rate", headers=_h(tok),
                              json={"stars": 6})
        assert r_bad.status_code in (400, 422)

        # companion cannot rate
        r_c = requests.post(f"{BASE_URL}/api/bookings/{bid}/rate", headers=_h(ana_tok),
                            json={"stars": 5})
        assert r_c.status_code == 403

        r = requests.post(f"{BASE_URL}/api/bookings/{bid}/rate", headers=_h(tok),
                         json={"stars": 5, "note": "private feedback"})
        assert r.status_code == 200
        assert r.json()["rating"] == 5.0
        assert r.json()["rating_count"] == 1

        # duplicate
        dup = requests.post(f"{BASE_URL}/api/bookings/{bid}/rate", headers=_h(tok),
                            json={"stars": 4})
        assert dup.status_code == 400

        # public card shows rating not note
        card = requests.get(f"{BASE_URL}/api/companions/{ana_id}", headers=_h(tok)).json()
        assert card["rating"] == 5.0
        assert card["rating_count"] == 1
        raw = requests.get(f"{BASE_URL}/api/companions/{ana_id}", headers=_h(tok)).text
        assert "private feedback" not in raw

        # admin can view notes; partner cannot
        adm = requests.get(f"{BASE_URL}/api/admin/companion-ratings",
                           headers=_h(sessions["admin"]["token"]))
        assert adm.status_code == 200
        items = adm.json()["items"]
        assert any(i["note"] == "private feedback" for i in items)

        prt = requests.get(f"{BASE_URL}/api/admin/companion-ratings",
                           headers=_h(sessions["partner"]["token"]))
        assert prt.status_code == 403

    def test_cannot_rate_before_completed(self, sessions):
        ana_id = sessions["ananya"]["id"]
        tok = sessions["tara"]["token"]
        DB.settings.update_one({}, {"$set": {"hangout_free_requests": 3}})
        DB.companion_bookings.delete_many({"member_id": sessions["tara"]["id"]})
        r = requests.post(f"{BASE_URL}/api/companions/{ana_id}/bookings", headers=_h(tok),
                          json={"hours": 2, "starts_at": _starts(5), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        r_rate = requests.post(f"{BASE_URL}/api/bookings/{bid}/rate", headers=_h(tok),
                               json={"stars": 5})
        assert r_rate.status_code == 400
