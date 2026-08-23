"""Iteration 25 — paid companion hangouts (fee-first flow, hidden rates, wallet auto-debit).

Covers:
  - premium gate (guest/free/partner/manager/min-plan)
  - hidden rates: list, detail, member's own booking view (pending fee / awaiting acceptance)
  - request fee: default 100, pending_request_fee -> checkout+verify -> awaiting_acceptance
  - admin can change hangout_request_fee; non-admin cannot
  - acceptance: member 403; no body = listed; explicit amount; >3x listed 400
  - counter-offer: > listed, <= 3x; due_amount = FULL counter
  - member pays agreed/counter: confirmed + payout 75/25 of AGREED (fee excluded)
  - 3+ consecutive confirmed companion payouts (unique-index regression)
  - wallet auto-debit
  - decline right after fee -> 0 credit; no-show -> paid_total - fee_paid credit
  - no cash refund on companion orders
  - suspend then re-approve restores companion.enabled + visibility

Run: pytest backend/tests/test_iteration25_hangouts.py -v -n 0
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
TARA = ("tara.joshi@example.com", "User@12345")
ANANYA = ("ananya.kapoor@example.com", "User@12345")
ARJUN = ("arjun.sethi@example.com", "User@12345")
PARTNER = ("partner@buddilio.com", "Partner@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")

ANANYA_SEED_COMPANION = {
    "hourly_rate": 1500.0, "min_hours": 2, "max_hours": 5,
    "headline": "Great dinner company", "about": "I love food and jazz.",
    "city": "Mumbai", "languages": ["English", "Hindi"],
    "packages": [{"label": "Dinner evening", "hours": 3, "price": 4000.0}],
    "enabled": True, "status": "approved", "completed": 0,
}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    j = r.json()
    return j["access_token"], j["user"]


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _starts_at(hours_ahead=4):
    return (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).isoformat()


def _pay(token, bid):
    o = requests.post(f"{BASE_URL}/api/checkout", headers=_h(token),
                      json={"kind": "companion", "item_id": bid, "use_credit": False})
    assert o.status_code == 200, o.text
    oid = o.json()["order"]["id"]
    v = requests.post(f"{BASE_URL}/api/payments/verify", headers=_h(token),
                      json={"order_id": oid})
    assert v.status_code == 200, v.text
    return o.json()["order"], v.json()


@pytest.fixture(scope="module")
def sessions():
    out = {}
    for k, (e, p) in {"admin": ADMIN, "tara": TARA, "ananya": ANANYA,
                      "arjun": ARJUN, "partner": PARTNER, "manager": MANAGER}.items():
        tok, u = _login(e, p)
        u_db = DB.users.find_one({"email": e}, {"_id": 1})
        out[k] = {"token": tok, "user": u, "id": str(u_db["_id"])}
    return out


@pytest.fixture(scope="module", autouse=True)
def prep_and_cleanup(sessions):
    plan = DB.membership_plans.find_one({"name": "Basic"})
    tara_id = sessions["tara"]["id"]
    ana_id = sessions["ananya"]["id"]
    DB.user_memberships.delete_many({"test_marker": "iter25_fee_flow"})
    DB.user_memberships.insert_one({
        "user_id": tara_id, "plan_id": str(plan["_id"]), "plan_name": plan["name"],
        "status": "active",
        "starts_at": datetime.now(timezone.utc).isoformat(),
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        "order_id": "", "test_marker": "iter25_fee_flow",
        "created_at": datetime.now(timezone.utc).isoformat()})
    DB.credits.delete_many({"user_id": tara_id})
    DB.companion_bookings.delete_many({"$or": [{"member_id": tara_id}, {"companion_id": ana_id}]})
    DB.payouts.delete_many({"kind": "companion"})
    DB.orders.delete_many({"kind": "companion", "user_id": tara_id})
    DB.settings.update_one({}, {"$set": {"hangout_request_fee": 100, "hangout_free_requests": 0},
                                "$unset": {"companions_min_plan": ""}})
    yield
    DB.user_memberships.delete_many({"test_marker": "iter25_fee_flow"})
    booking_ids = [str(b["_id"]) for b in DB.companion_bookings.find(
        {"$or": [{"member_id": tara_id}, {"companion_id": ana_id}]}, {"_id": 1})]
    if booking_ids:
        oids = [ObjectId(b) for b in booking_ids]
        DB.companion_bookings.delete_many({"_id": {"$in": oids}})
        DB.payouts.delete_many({"booking_id": {"$in": booking_ids}})
        DB.credits.delete_many({"booking_id": {"$in": booking_ids}})
        DB.orders.delete_many({"kind": "companion", "ref_id": {"$in": booking_ids}})
        DB.reports.delete_many({"reporter_id": tara_id, "reason": "Hangout no-show"})
    DB.credits.delete_many({"user_id": tara_id})
    DB.users.update_one({"_id": ObjectId(ana_id)}, {"$set": {"companion": {
        **ANANYA_SEED_COMPANION,
        "accepted_terms_at": datetime.now(timezone.utc).isoformat(),
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "rejected_reason": "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }}})
    DB.settings.update_one({}, {"$set": {"hangout_request_fee": 100, "hangout_free_requests": 3},
                                "$unset": {"companions_min_plan": ""}})
    print("[cleanup] iter25 hangouts artefacts purged; fee reset to 100; Ananya restored")


@pytest.fixture(autouse=True)
def _isolate(sessions):
    tara_id = sessions["tara"]["id"]
    ana_id = sessions["ananya"]["id"]
    DB.companion_bookings.update_many(
        {"$or": [{"member_id": tara_id}, {"companion_id": ana_id}],
         "status": {"$in": ["pending_request_fee", "pending_payment", "awaiting_acceptance",
                            "payment_due", "counter_offered"]}},
        {"$set": {"status": "cancelled"}})
    DB.credits.delete_many({"user_id": tara_id})
    yield


# 1. Premium gate
class TestPremiumGate:
    def test_guest_401(self):
        assert requests.get(f"{BASE_URL}/api/companions").status_code == 401

    def test_non_member_403(self, sessions):
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(sessions["arjun"]["token"]))
        assert r.status_code == 403

    def test_partner_403(self, sessions):
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(sessions["partner"]["token"]))
        assert r.status_code == 403

    def test_manager_403(self, sessions):
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(sessions["manager"]["token"]))
        assert r.status_code == 403

    def test_min_plan_enforced(self, sessions):
        DB.settings.update_one({}, {"$set": {"companions_min_plan": "Premium Annual"}})
        try:
            r = requests.get(f"{BASE_URL}/api/companions", headers=_h(sessions["tara"]["token"]))
            assert r.status_code == 403
            assert "Premium Annual" in r.json().get("detail", "")
        finally:
            DB.settings.update_one({}, {"$unset": {"companions_min_plan": ""}})


# 2. Rates hidden
class TestHiddenRates:
    def test_list_hides_rate_and_package_prices(self, sessions):
        r = requests.get(f"{BASE_URL}/api/companions", headers=_h(sessions["tara"]["token"]))
        assert r.status_code == 200
        j = r.json()
        assert j["request_fee"] == 100
        it = next(i for i in j["items"] if i["id"] == sessions["ananya"]["id"])
        assert it["hourly_rate"] == 0
        assert it.get("rate_hidden") is True
        for p in it["packages"]:
            assert "price" not in p

    def test_detail_hides_rate(self, sessions):
        aid = sessions["ananya"]["id"]
        r = requests.get(f"{BASE_URL}/api/companions/{aid}", headers=_h(sessions["tara"]["token"]))
        assert r.status_code == 200
        j = r.json()
        assert j["hourly_rate"] == 0
        assert j.get("rate_hidden") is True
        assert j["request_fee"] == 100
        for p in j["packages"]:
            assert "price" not in p


# 3. Request fee
class TestRequestFee:
    def test_create_booking_pending_fee(self, sessions):
        aid = sessions["ananya"]["id"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(sessions["tara"]["token"]),
                          json={"hours": 4, "starts_at": _starts_at(5),
                                "accept_terms": True})
        assert r.status_code == 200, r.text
        j = r.json()
        b = j["booking"]
        assert b["status"] == "pending_request_fee"
        assert b["due_amount"] == 100
        assert b["rate_hidden"] is True
        assert b["amount"] == 0
        assert j["checkout"]["item_id"] == b["id"]
        assert j["request_fee"] == 100

    def test_pay_fee_moves_to_awaiting_acceptance(self, sessions):
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 3, "starts_at": _starts_at(5), "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)
        b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "awaiting_acceptance"
        assert b["fee_paid"] == 100
        assert b["due_amount"] == 0

    def test_admin_can_change_fee_non_admin_cannot(self, sessions):
        r_bad = requests.put(f"{BASE_URL}/api/admin/settings",
                             headers=_h(sessions["partner"]["token"]),
                             json={"hangout_request_fee": 999})
        assert r_bad.status_code == 403

        assert requests.put(f"{BASE_URL}/api/admin/settings",
                            headers=_h(sessions["admin"]["token"]),
                            json={"hangout_request_fee": 250}).status_code == 200

        aid = sessions["ananya"]["id"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(sessions["tara"]["token"]),
                          json={"hours": 2, "starts_at": _starts_at(6),
                                "accept_terms": True})
        assert r.status_code == 200
        assert r.json()["booking"]["due_amount"] == 250
        assert r.json()["request_fee"] == 250

        requests.put(f"{BASE_URL}/api/admin/settings",
                     headers=_h(sessions["admin"]["token"]),
                     json={"hangout_request_fee": 100})


# 4. Acceptance
class TestAcceptance:
    def _awaiting(self, sessions, hours=4):
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": hours, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)
        return bid

    def test_member_cannot_accept(self, sessions):
        bid = self._awaiting(sessions)
        r = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                          headers=_h(sessions["tara"]["token"]), json={})
        assert r.status_code == 403

    def test_accept_no_body_uses_listed(self, sessions):
        bid = self._awaiting(sessions, hours=4)  # 6000
        r = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                          headers=_h(sessions["ananya"]["token"]))
        assert r.status_code == 200
        assert r.json()["amount"] == 6000

    def test_accept_amount_and_cap(self, sessions):
        bid = self._awaiting(sessions, hours=2)  # 3000
        assert requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                             headers=_h(sessions["ananya"]["token"]),
                             json={"amount": 15000}).status_code == 400
        r = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                          headers=_h(sessions["ananya"]["token"]),
                          json={"amount": 4000})
        assert r.status_code == 200
        assert r.json()["amount"] == 4000

    def test_member_sees_amount_after_accept(self, sessions):
        bid = self._awaiting(sessions, hours=3)  # 4500
        requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                      headers=_h(sessions["ananya"]["token"]))
        mb = requests.get(f"{BASE_URL}/api/me/bookings",
                          headers=_h(sessions["tara"]["token"])).json()
        row = next(b for b in mb["items"] if b["id"] == bid)
        assert row["rate_hidden"] is False
        assert row["amount"] == 4500
        assert row["due_amount"] == 4500


# 5. Counter
class TestCounter:
    def test_counter_full_amount(self, sessions):
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 3, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)

        assert requests.post(f"{BASE_URL}/api/bookings/{bid}/counter",
                             headers=_h(ana_tok),
                             json={"amount": 4500}).status_code == 400
        assert requests.post(f"{BASE_URL}/api/bookings/{bid}/counter",
                             headers=_h(ana_tok),
                             json={"amount": 20000}).status_code == 400
        assert requests.post(f"{BASE_URL}/api/bookings/{bid}/counter",
                             headers=_h(tara_tok),
                             json={"amount": 6000}).status_code == 403

        r_ok = requests.post(f"{BASE_URL}/api/bookings/{bid}/counter",
                             headers=_h(ana_tok), json={"amount": 6000})
        assert r_ok.status_code == 200
        b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "counter_offered"
        assert b["due_amount"] == 6000


# 6. Pay & payouts (3 consecutive)
class TestPayAndPayouts:
    def _confirm(self, sessions, hours):
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": hours, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)
        rr = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                           headers=_h(ana_tok))
        assert rr.status_code == 200
        _pay(tara_tok, bid)
        return bid

    def test_three_consecutive_payouts(self, sessions):
        DB.credits.delete_many({"user_id": sessions["tara"]["id"]})
        for hours, agreed in [(2, 3000), (3, 4500), (4, 6000)]:
            bid = self._confirm(sessions, hours)
            b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
            assert b["status"] == "confirmed", b
            assert b["amount"] == agreed
            p = DB.payouts.find_one({"booking_id": bid})
            assert p is not None
            assert p["gross"] == agreed
            assert p["net"] == round(agreed * 0.75, 2)
            assert p["fee"] == round(agreed * 0.25, 2)

    def test_counter_pay_confirms_full(self, sessions):
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": sessions["tara"]["id"]})
        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 3, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)
        assert requests.post(f"{BASE_URL}/api/bookings/{bid}/counter",
                             headers=_h(ana_tok),
                             json={"amount": 8000}).status_code == 200

        r2 = requests.post(f"{BASE_URL}/api/checkout", headers=_h(tara_tok),
                           json={"kind": "companion", "item_id": bid, "use_credit": False})
        assert r2.status_code == 200
        assert r2.json()["order"]["subtotal"] == 8000
        v = requests.post(f"{BASE_URL}/api/payments/verify", headers=_h(tara_tok),
                          json={"order_id": r2.json()["order"]["id"]})
        assert v.status_code == 200

        b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "confirmed"
        assert b["amount"] == 8000
        p = DB.payouts.find_one({"booking_id": bid})
        assert p["gross"] == 8000
        assert p["net"] == 6000
        assert p["fee"] == 2000


# 7. Wallet auto-debit
class TestWalletAutoDebit:
    def test_wallet_covers_price(self, sessions):
        tara_id = sessions["tara"]["id"]
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]

        DB.credits.delete_many({"user_id": tara_id})
        DB.credits.insert_one({"user_id": tara_id, "amount": 9000.0, "type": "grant",
                               "reason": "test", "created_at": datetime.now(timezone.utc).isoformat()})

        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 2, "starts_at": _starts_at(6),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)

        pre = requests.get(f"{BASE_URL}/api/me/bookings",
                           headers=_h(tara_tok)).json()["credit_balance"]

        r_acc = requests.post(f"{BASE_URL}/api/bookings/{bid}/accept",
                              headers=_h(ana_tok), json={"amount": 3000})
        assert r_acc.status_code == 200
        assert r_acc.json()["status"] == "confirmed"
        assert r_acc.json()["paid_from"] == "wallet"

        b = DB.companion_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "confirmed"
        assert b["amount"] == 3000

        post = requests.get(f"{BASE_URL}/api/me/bookings",
                            headers=_h(tara_tok)).json()["credit_balance"]
        assert round(pre - post, 2) == 3000

        p = DB.payouts.find_one({"booking_id": bid})
        assert p["gross"] == 3000
        assert p["net"] == 2250
        assert p["fee"] == 750

        DB.credits.delete_many({"user_id": tara_id})


# 8. Non-refundable fee
class TestNonRefundableFee:
    def test_decline_right_after_fee_zero_credit(self, sessions):
        tara_id = sessions["tara"]["id"]
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})

        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 2, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)

        r_dec = requests.post(f"{BASE_URL}/api/bookings/{bid}/decline",
                              headers=_h(ana_tok))
        assert r_dec.status_code == 200
        assert r_dec.json()["credit_issued"] == 0
        bal = requests.get(f"{BASE_URL}/api/me/bookings",
                           headers=_h(tara_tok)).json()["credit_balance"]
        assert bal == 0

    def test_no_show_credits_only_agreed(self, sessions):
        tara_id = sessions["tara"]["id"]
        aid = sessions["ananya"]["id"]
        tara_tok = sessions["tara"]["token"]
        ana_tok = sessions["ananya"]["token"]
        DB.credits.delete_many({"user_id": tara_id})

        r = requests.post(f"{BASE_URL}/api/companions/{aid}/bookings",
                          headers=_h(tara_tok),
                          json={"hours": 2, "starts_at": _starts_at(5),
                                "accept_terms": True})
        bid = r.json()["booking"]["id"]
        _pay(tara_tok, bid)
        requests.post(f"{BASE_URL}/api/bookings/{bid}/accept", headers=_h(ana_tok))
        _pay(tara_tok, bid)

        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        DB.companion_bookings.update_one({"_id": ObjectId(bid)},
                                         {"$set": {"starts_at": past}})
        r_ns = requests.post(f"{BASE_URL}/api/bookings/{bid}/no-show",
                             headers=_h(tara_tok), json={"note": "no"})
        assert r_ns.status_code == 200
        # paid_total = 100 + 3000 = 3100; fee_paid=100 -> credit=3000
        assert r_ns.json()["credit_issued"] == 3000

    def test_no_cash_refund_on_companion_orders(self, sessions):
        orders = list(DB.orders.find({"user_id": sessions["tara"]["id"], "kind": "companion"}))
        assert len(orders) > 0
        for o in orders:
            assert o.get("refund_status", "none") == "none"


# 9. Suspend & re-approve
class TestSuspendReapprove:
    def test_reapprove_restores(self, sessions):
        aid = sessions["ananya"]["id"]
        admin_tok = sessions["admin"]["token"]
        tara_tok = sessions["tara"]["token"]

        assert requests.post(f"{BASE_URL}/api/admin/companions/{aid}",
                             headers=_h(admin_tok),
                             json={"action": "suspend", "reason": "t"}).status_code == 200

        listed = requests.get(f"{BASE_URL}/api/companions",
                              headers=_h(tara_tok)).json()
        assert not any(i["id"] == aid for i in listed["items"])

        assert requests.post(f"{BASE_URL}/api/admin/companions/{aid}",
                             headers=_h(admin_tok),
                             json={"action": "approve"}).status_code == 200
        u = DB.users.find_one({"_id": ObjectId(aid)})
        assert u["companion"]["enabled"] is True
        assert u["companion"]["status"] == "approved"

        listed2 = requests.get(f"{BASE_URL}/api/companions",
                               headers=_h(tara_tok)).json()
        assert any(i["id"] == aid for i in listed2["items"])
