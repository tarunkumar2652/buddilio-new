"""Iteration 31 — Solo travel (trips + providers + service requests) + finance ledger/invoice/receipt/export.

Run: pytest backend/tests/test_iteration31_travel_ledger.py -v -n 0
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

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

USERS = {
    "admin":   ("admin@buddilio.com",       "Admin@123"),
    "manager": ("ops.manager@buddilio.com", "Console@123"),
    "partner": ("partner@buddilio.com",     "Partner@123"),
    "tara":    ("tara.joshi@example.com",   "User@123"),   # traveller (IN)
    "kabir":   ("kabir.nair@example.com",   "User@123"),   # provider
    "aarav":   ("aarav.mehta@example.com",  "User@123"),   # spare traveller
    "arjun":   ("arjun.sethi@example.com",  "User@123"),
}


def _h(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _login(e, p):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": e, "password": p}, timeout=30)
    assert r.status_code == 200, f"login {e}: {r.text}"
    j = r.json()
    return j["access_token"], j["user"]


def _future(days=25, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


def _uid(email):
    return str(DB.users.find_one({"email": email})["_id"])


# ------------------------------------------------------------ session fixtures
@pytest.fixture(scope="module")
def S():
    out = {}
    for k, (e, p) in USERS.items():
        tok, u = _login(e, p)
        out[k] = {"token": tok, "user": u, "id": _uid(e)}
    return out


@pytest.fixture(scope="module", autouse=True)
def _clean(S):
    """Wipe travel state before + after, reset settings."""
    tid, pid, aid = S["tara"]["id"], S["kabir"]["id"], S["aarav"]["id"]
    def reset():
        DB.trips.delete_many({"host_id": {"$in": [tid, pid, aid]}})
        DB.trip_joins.delete_many({})
        DB.travel_bookings.delete_many({"traveller_id": {"$in": [tid, pid, aid]}})
        DB.service_requests.delete_many({"traveller_id": {"$in": [tid, pid, aid]}})
        DB.service_quotes.delete_many({"provider_id": {"$in": [tid, pid, aid]}})
        DB.payouts.delete_many({"kind": "travel"})
        DB.orders.delete_many({"kind": {"$in": ["travel", "provider_fee"]}})
        DB.users.update_one({"_id": ObjectId(pid)}, {"$unset": {"provider": ""}})
        DB.users.update_one({"_id": ObjectId(tid)}, {"$unset": {"provider": ""}})
        DB.users.update_one({"_id": ObjectId(aid)}, {"$set": {"country_code": "IN"}})
        DB.settings.update_one({}, {"$set": {"provider_fee": 999, "travel_markup_percent": 18,
                                             "travel_uplift_percent": 30, "travel_cut_percent": 25,
                                             "hangout_request_fee": 100, "hangout_free_requests": 3}})
    reset()
    yield
    reset()


# ------------------------------------------------------------ helpers
def _pay(token, kind, item_id):
    o = requests.post(f"{BASE}/api/checkout", headers=_h(token),
                      json={"kind": kind, "item_id": item_id, "use_credit": False})
    assert o.status_code == 200, o.text
    order = o.json()["order"]
    v = requests.post(f"{BASE}/api/payments/verify", headers=_h(token), json={"order_id": order["id"]})
    assert v.status_code == 200, v.text
    return order


def _apply_provider(token, day_rate=2000):
    return requests.post(f"{BASE}/api/me/provider", headers=_h(token), json={
        "roles": ["trek_guide", "cook"], "day_rate": day_rate,
        "destinations": ["Dehradun", "Manali"], "languages": ["Hindi", "English"],
        "headline": "Himalayan trek lead", "about": "<p>Winter treks</p>",
        "experience_years": 8, "accept_terms": True,
        "documents": [{"url": "/api/files/test-doc.pdf", "name": "Guide licence"}]})


# =========================================================== TRIPS
class TestTrips:
    def test_create_and_list_trip(self, S):
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]), json={
            "title": "Kedarkantha", "destination": "Dehradun", "activity": "Trekking",
            "group_size": 4, "budget": 12000, "starts_at": _future(20), "notes": "<p>x</p>"})
        assert r.status_code == 200
        t = r.json()
        assert t["status"] == "open" and t["joined"] == 0
        # list mine=true shows it
        lst = requests.get(f"{BASE}/api/travel/trips?mine=true", headers=_h(S["tara"]["token"])).json()
        assert any(i["id"] == t["id"] for i in lst["items"])
        pytest.trip_id = t["id"]

    def test_create_rejects_past_date_and_bad_activity_and_bad_size(self, S):
        base = {"title": "x", "destination": "d", "starts_at": _future(20), "activity": "Trekking",
                "group_size": 4}
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]),
                          json={**base, "starts_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        assert r.status_code == 400
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]),
                          json={**base, "activity": "Skydiving"})
        assert r.status_code == 400
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]),
                          json={**base, "group_size": 1})
        assert r.status_code == 422
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]),
                          json={**base, "group_size": 100})
        assert r.status_code == 422

    def test_cap_five_open_trips(self, S):
        # tara already has 1 open; create 4 more, then 6th 400
        for i in range(4):
            r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]), json={
                "title": f"T{i}", "destination": "Goa", "activity": "Beach",
                "group_size": 3, "starts_at": _future(15 + i)})
            assert r.status_code == 200
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]), json={
            "title": "sixth", "destination": "Goa", "activity": "Beach",
            "group_size": 3, "starts_at": _future(20)})
        assert r.status_code == 400 and "five" in r.text.lower()

    def test_join_flow_and_host_only_requests(self, S):
        tid = pytest.trip_id
        # host can't join own trip
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/join", headers=_h(S["tara"]["token"]), json={})
        assert r.status_code == 400
        # kabir joins
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/join",
                          headers=_h(S["kabir"]["token"]), json={"note": "in"})
        assert r.status_code == 200
        # duplicate join
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/join",
                          headers=_h(S["kabir"]["token"]), json={})
        assert r.status_code == 400
        # list marks requested=true for kabir
        lst = requests.get(f"{BASE}/api/travel/trips", headers=_h(S["kabir"]["token"])).json()
        row = next((i for i in lst["items"] if i["id"] == tid), None)
        assert row and row["requested"] is True
        # non-host cannot see requests
        r = requests.get(f"{BASE}/api/travel/trips/{tid}/requests",
                         headers=_h(S["kabir"]["token"]))
        assert r.status_code == 403
        reqs = requests.get(f"{BASE}/api/travel/trips/{tid}/requests",
                            headers=_h(S["tara"]["token"])).json()["items"]
        assert len(reqs) == 1
        pytest.trip_join_id = reqs[0]["id"]

    def test_approve_and_double_answer(self, S):
        tid, jid = pytest.trip_id, pytest.trip_join_id
        # non-host attempt
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/requests/{jid}",
                          headers=_h(S["kabir"]["token"]), json={"action": "approve", "note": ""})
        assert r.status_code == 403
        # bad action
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/requests/{jid}",
                          headers=_h(S["tara"]["token"]), json={"action": "explode", "note": ""})
        assert r.status_code == 400
        # approve
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/requests/{jid}",
                          headers=_h(S["tara"]["token"]), json={"action": "approve", "note": ""})
        assert r.status_code == 200 and r.json()["status"] == "joined"
        # cannot answer twice
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/requests/{jid}",
                          headers=_h(S["tara"]["token"]), json={"action": "reject", "note": ""})
        assert r.status_code == 400
        # joined counter incremented and status stays open (4-person group, only 1 joined + host)
        t = DB.trips.find_one({"_id": ObjectId(tid)})
        assert t["joined"] == 1 and t["status"] == "open"

    def test_full_group_flips_status(self, S):
        # create small 2-person trip; one accepted request fills it
        r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]), json={
            "title": "Duo", "destination": "Coorg", "activity": "Camping",
            "group_size": 2, "starts_at": _future(40)})
        # tara at cap of 5 open, so we close her earliest trip first
        if r.status_code == 400:
            # close her first extra trip and retry
            first = DB.trips.find_one({"host_id": S["tara"]["id"], "status": "open",
                                       "_id": {"$ne": ObjectId(pytest.trip_id)}})
            requests.delete(f"{BASE}/api/travel/trips/{first['_id']}", headers=_h(S["tara"]["token"]))
            r = requests.post(f"{BASE}/api/travel/trips", headers=_h(S["tara"]["token"]), json={
                "title": "Duo", "destination": "Coorg", "activity": "Camping",
                "group_size": 2, "starts_at": _future(40)})
        assert r.status_code == 200
        tid = r.json()["id"]
        # kabir joins → approve → group full (group_size 2 means 1 companion + host)
        j = requests.post(f"{BASE}/api/travel/trips/{tid}/join",
                          headers=_h(S["kabir"]["token"]), json={})
        assert j.status_code == 200
        jid = requests.get(f"{BASE}/api/travel/trips/{tid}/requests",
                           headers=_h(S["tara"]["token"])).json()["items"][0]["id"]
        requests.post(f"{BASE}/api/travel/trips/{tid}/requests/{jid}",
                      headers=_h(S["tara"]["token"]), json={"action": "approve", "note": ""})
        t = DB.trips.find_one({"_id": ObjectId(tid)})
        assert t["status"] == "full"
        # further joins refused (aarav)
        r = requests.post(f"{BASE}/api/travel/trips/{tid}/join",
                          headers=_h(S["aarav"]["token"]), json={})
        assert r.status_code in (400, 404)  # 404 because trips filter status=open

    def test_close_trip_permissions(self, S):
        tid = pytest.trip_id
        # non-host, non-admin 403
        r = requests.delete(f"{BASE}/api/travel/trips/{tid}", headers=_h(S["kabir"]["token"]))
        assert r.status_code == 403
        # host closes
        r = requests.delete(f"{BASE}/api/travel/trips/{tid}", headers=_h(S["tara"]["token"]))
        assert r.status_code == 200
        assert DB.trips.find_one({"_id": ObjectId(tid)})["status"] == "closed"


# =========================================================== PROVIDER REG
class TestProviderRegistration:
    def test_validation(self, S):
        # bad url
        r = requests.post(f"{BASE}/api/me/provider", headers=_h(S["kabir"]["token"]), json={
            "roles": ["cook"], "day_rate": 2000, "accept_terms": True,
            "documents": [{"url": "https://external.example/x.pdf", "name": "x"}]})
        assert r.status_code == 400
        # no documents
        r = requests.post(f"{BASE}/api/me/provider", headers=_h(S["kabir"]["token"]), json={
            "roles": ["cook"], "day_rate": 2000, "accept_terms": True, "documents": []})
        assert r.status_code == 400
        # no roles
        r = requests.post(f"{BASE}/api/me/provider", headers=_h(S["kabir"]["token"]), json={
            "roles": [], "day_rate": 2000, "accept_terms": True,
            "documents": [{"url": "/api/files/x.pdf", "name": "x"}]})
        assert r.status_code == 400
        # not accepted terms
        r = requests.post(f"{BASE}/api/me/provider", headers=_h(S["kabir"]["token"]), json={
            "roles": ["cook"], "day_rate": 2000, "accept_terms": False,
            "documents": [{"url": "/api/files/x.pdf", "name": "x"}]})
        assert r.status_code == 400

    def test_apply_lands_in_pending_fee(self, S):
        r = _apply_provider(S["kabir"]["token"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending_fee"
        assert j["checkout"]["kind"] == "provider_fee"
        assert j["checkout"]["amount"] == 999.0  # IN, defaults
        # GET /me/provider shows day_rate + markup% + cut%
        me = requests.get(f"{BASE}/api/me/provider", headers=_h(S["kabir"]["token"])).json()
        assert me["profile"]["day_rate"] == 2000
        assert me["profile"]["cut_percent"] == 25
        assert me["profile"]["markup_percent"] == 18

    def test_pay_fee_moves_to_pending_and_tax_free(self, S):
        order = _pay(S["kabir"]["token"], "provider_fee", S["kabir"]["id"])
        # tax free: total equals fee exactly
        assert order["total"] == 999.0
        assert order["tax"] == 0.0
        u = DB.users.find_one({"_id": ObjectId(S["kabir"]["id"])}, {"provider": 1})
        assert u["provider"]["status"] == "pending"
        assert u["provider"]["fee_paid"] == 999.0

    def test_second_payment_does_not_double_charge(self, S):
        # further checkout for provider_fee should 404 (nothing due)
        r = requests.post(f"{BASE}/api/checkout", headers=_h(S["kabir"]["token"]),
                          json={"kind": "provider_fee", "item_id": S["kabir"]["id"],
                                "use_credit": False})
        assert r.status_code == 404
        # status stays pending, fee_paid unchanged
        u = DB.users.find_one({"_id": ObjectId(S["kabir"]["id"])}, {"provider": 1})
        assert u["provider"]["status"] == "pending"
        assert u["provider"]["fee_paid"] == 999.0
        # calling apply again should not reset status
        r = _apply_provider(S["kabir"]["token"])
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "pending"
        assert j.get("next") == "review"


# =========================================================== PROVIDER MODERATION
class TestProviderModeration:
    def test_admin_can_list_partner_and_member_cannot(self, S):
        r = requests.get(f"{BASE}/api/admin/providers", headers=_h(S["admin"]["token"]))
        assert r.status_code == 200
        j = r.json()
        assert "counts" in j and "roles" in j and "items" in j
        # partner + tara (member) get 403 (no verification:manage)
        assert requests.get(f"{BASE}/api/admin/providers",
                            headers=_h(S["partner"]["token"])).status_code == 403
        assert requests.get(f"{BASE}/api/admin/providers",
                            headers=_h(S["tara"]["token"])).status_code == 403

    def test_reject_unknown_action_and_bad_id(self, S):
        pid = S["kabir"]["id"]
        r = requests.post(f"{BASE}/api/admin/providers/{pid}", headers=_h(S["admin"]["token"]),
                          json={"action": "banish", "note": ""})
        assert r.status_code == 400
        # 404 for a member with no provider doc (arjun)
        r = requests.post(f"{BASE}/api/admin/providers/{S['arjun']['id']}",
                          headers=_h(S["admin"]["token"]),
                          json={"action": "approve", "note": ""})
        assert r.status_code == 404

    def test_cannot_approve_if_unpaid(self, S):
        # temporarily zero out fee_paid
        DB.users.update_one({"_id": ObjectId(S["kabir"]["id"])},
                            {"$set": {"provider.fee_paid": 0}})
        r = requests.post(f"{BASE}/api/admin/providers/{S['kabir']['id']}",
                          headers=_h(S["admin"]["token"]),
                          json={"action": "approve", "note": ""})
        assert r.status_code == 400
        # restore
        DB.users.update_one({"_id": ObjectId(S["kabir"]["id"])},
                            {"$set": {"provider.fee_paid": 999.0}})

    def test_approve_and_list_appears(self, S):
        r = requests.post(f"{BASE}/api/admin/providers/{S['kabir']['id']}",
                          headers=_h(S["admin"]["token"]),
                          json={"action": "approve", "note": ""})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        # only approved providers show in /travel/providers
        lst = requests.get(f"{BASE}/api/travel/providers",
                           headers=_h(S["tara"]["token"])).json()
        assert any(i["id"] == S["kabir"]["id"] for i in lst["items"])


# =========================================================== DYNAMIC PRICING
class TestDynamicPricing:
    def test_indian_traveller_sees_markup_only(self, S):
        lst = requests.get(f"{BASE}/api/travel/providers",
                           headers=_h(S["tara"]["token"])).json()
        card = next(i for i in lst["items"] if i["id"] == S["kabir"]["id"])
        assert card["day_price"] == 2360.0  # 2000 * 1.18

    def test_non_indian_traveller_sees_uplift(self, S):
        DB.users.update_one({"_id": ObjectId(S["aarav"]["id"])},
                            {"$set": {"country_code": "US"}})
        # aarav needs a fresh token to refresh country_code? get_current_user reads db, so cached JWT is fine
        lst = requests.get(f"{BASE}/api/travel/providers",
                           headers=_h(S["aarav"]["token"])).json()
        card = next(i for i in lst["items"] if i["id"] == S["kabir"]["id"])
        assert card["day_price"] == 3068.0  # 2360 * 1.30
        # restore
        DB.users.update_one({"_id": ObjectId(S["aarav"]["id"])},
                            {"$set": {"country_code": "IN"}})

    def test_settings_update_changes_pricing_live(self, S):
        # set markup to 20, uplift to 40, fee to 1200
        r = requests.put(f"{BASE}/api/admin/settings", headers=_h(S["admin"]["token"]),
                         json={"travel_markup_percent": 20, "travel_uplift_percent": 40,
                               "provider_fee": 1200, "travel_cut_percent": 30})
        assert r.status_code == 200
        lst = requests.get(f"{BASE}/api/travel/providers",
                           headers=_h(S["tara"]["token"])).json()
        card = next(i for i in lst["items"] if i["id"] == S["kabir"]["id"])
        assert card["day_price"] == 2400.0  # 2000 * 1.20
        meta = requests.get(f"{BASE}/api/travel/meta",
                            headers=_h(S["kabir"]["token"])).json()
        assert meta["provider_fee"] == 1200.0
        assert meta["markup_percent"] == 20.0
        assert meta["uplift_percent"] == 40.0
        # restore defaults
        requests.put(f"{BASE}/api/admin/settings", headers=_h(S["admin"]["token"]),
                     json={"travel_markup_percent": 18, "travel_uplift_percent": 30,
                           "provider_fee": 999, "travel_cut_percent": 25})

    def test_sort_options_and_invalid_sort_422(self, S):
        for s in ("rating", "experience", "price", "price_desc"):
            r = requests.get(f"{BASE}/api/travel/providers?sort={s}",
                             headers=_h(S["tara"]["token"]))
            assert r.status_code == 200, s
        r = requests.get(f"{BASE}/api/travel/providers?sort=cheapest",
                         headers=_h(S["tara"]["token"]))
        assert r.status_code == 422


# =========================================================== BOOKINGS + COMMISSION
class TestBookingsAndCommission:
    def test_book_rejects_past_self_and_unapproved(self, S):
        # past date
        r = requests.post(f"{BASE}/api/travel/providers/{S['kabir']['id']}/bookings",
                          headers=_h(S["tara"]["token"]),
                          json={"days": 2, "people": 1,
                                "starts_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        assert r.status_code == 400
        # self-booking
        r = requests.post(f"{BASE}/api/travel/providers/{S['kabir']['id']}/bookings",
                          headers=_h(S["kabir"]["token"]),
                          json={"days": 2, "people": 1, "starts_at": _future(25)})
        assert r.status_code == 400
        # unapproved provider (aarav has no provider)
        r = requests.post(f"{BASE}/api/travel/providers/{S['aarav']['id']}/bookings",
                          headers=_h(S["tara"]["token"]),
                          json={"days": 2, "people": 1, "starts_at": _future(25)})
        assert r.status_code == 400  # invalid provider id path handles not-found

    def test_booking_calc_and_payout(self, S):
        r = requests.post(f"{BASE}/api/travel/providers/{S['kabir']['id']}/bookings",
                          headers=_h(S["tara"]["token"]),
                          json={"days": 3, "people": 1, "starts_at": _future(25)})
        assert r.status_code == 200
        j = r.json()
        assert j["amount"] == 7080.0  # 2360 * 3
        bid = j["booking_id"]
        pytest.travel_booking_id = bid
        pytest.travel_order = _pay(S["tara"]["token"], "travel", bid)
        # booking confirmed
        b = DB.travel_bookings.find_one({"_id": ObjectId(bid)})
        assert b["status"] == "confirmed"
        assert b["platform_fee"] == 1770.0  # 25%
        assert b["provider_net"] == 5310.0  # 75%
        # single payout with fee=1770, net=5310
        payouts = list(DB.payouts.find({"booking_id": bid}))
        assert len(payouts) == 1
        assert payouts[0]["kind"] == "travel"
        assert payouts[0]["fee"] == 1770.0
        assert payouts[0]["net"] == 5310.0
        # trips_done incremented
        u = DB.users.find_one({"_id": ObjectId(S["kabir"]["id"])}, {"provider.trips_done": 1})
        assert u["provider"]["trips_done"] >= 1

    def test_paying_twice_no_duplicate_payout(self, S):
        # attempting to checkout the same booking after confirmed → due_amount = 0 → 404
        r = requests.post(f"{BASE}/api/checkout", headers=_h(S["tara"]["token"]),
                          json={"kind": "travel", "item_id": pytest.travel_booking_id,
                                "use_credit": False})
        assert r.status_code == 404
        # payout row still single
        assert DB.payouts.count_documents({"booking_id": pytest.travel_booking_id}) == 1


# =========================================================== SERVICE REQUESTS + QUOTES
class TestServiceRequestsQuotes:
    def test_create_and_validation(self, S):
        # bad role
        r = requests.post(f"{BASE}/api/travel/requests", headers=_h(S["tara"]["token"]),
                          json={"destination": "Manali", "roles": ["chef"], "days": 2,
                                "people": 3, "starts_at": _future(30)})
        assert r.status_code == 400
        # past date
        r = requests.post(f"{BASE}/api/travel/requests", headers=_h(S["tara"]["token"]),
                          json={"destination": "Manali", "roles": ["cook"], "days": 2,
                                "people": 3,
                                "starts_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
        assert r.status_code == 400
        # ok
        r = requests.post(f"{BASE}/api/travel/requests", headers=_h(S["tara"]["token"]),
                          json={"destination": "Manali", "roles": ["cook"], "days": 2,
                                "people": 3, "starts_at": _future(30)})
        assert r.status_code == 200
        pytest.sreq_id = r.json()["id"]

    def test_open_list_non_provider_forbidden(self, S):
        # arjun is not a provider
        r = requests.get(f"{BASE}/api/travel/requests", headers=_h(S["arjun"]["token"]))
        assert r.status_code == 403
        # tara sees her own via mine=true
        j = requests.get(f"{BASE}/api/travel/requests?mine=true",
                         headers=_h(S["tara"]["token"])).json()
        assert any(i["id"] == pytest.sreq_id for i in j["items"])

    def test_provider_only_quote_once(self, S):
        rid = pytest.sreq_id
        # tara (traveller) cannot quote
        r = requests.post(f"{BASE}/api/travel/requests/{rid}/quotes",
                          headers=_h(S["tara"]["token"]),
                          json={"amount": 5000, "note": ""})
        assert r.status_code == 403
        # kabir (approved provider) can
        r = requests.post(f"{BASE}/api/travel/requests/{rid}/quotes",
                          headers=_h(S["kabir"]["token"]),
                          json={"amount": 5000, "note": "veg + non-veg"})
        assert r.status_code == 200
        j = r.json()
        assert j["amount"] == 5900.0  # 5000 * 1.18
        pytest.sq_id = j["quote_id"]
        # duplicate quote
        r = requests.post(f"{BASE}/api/travel/requests/{rid}/quotes",
                          headers=_h(S["kabir"]["token"]),
                          json={"amount": 6000, "note": ""})
        assert r.status_code == 400

    def test_accept_quote_and_second_accept_404(self, S):
        qid = pytest.sq_id
        # non-traveller accept
        r = requests.post(f"{BASE}/api/travel/quotes/{qid}/accept",
                          headers=_h(S["kabir"]["token"]))
        assert r.status_code == 403
        # traveller accepts
        r = requests.post(f"{BASE}/api/travel/quotes/{qid}/accept",
                          headers=_h(S["tara"]["token"]))
        assert r.status_code == 200
        # request marked matched
        req = DB.service_requests.find_one({"_id": ObjectId(pytest.sreq_id)})
        assert req["status"] == "matched"
        q = DB.service_quotes.find_one({"_id": ObjectId(qid)})
        assert q["status"] == "accepted"
        # second accept 404 (status no longer open)
        r = requests.post(f"{BASE}/api/travel/quotes/{qid}/accept",
                          headers=_h(S["tara"]["token"]))
        assert r.status_code == 404


# =========================================================== LEDGER
class TestLedger:
    def test_permission_gating(self, S):
        # partner and manager don't have finance:view (per test creds)
        assert requests.get(f"{BASE}/api/admin/ledger",
                            headers=_h(S["partner"]["token"])).status_code == 403
        # ops.manager has vendor perms only — no finance:view
        assert requests.get(f"{BASE}/api/admin/ledger",
                            headers=_h(S["manager"]["token"])).status_code == 403
        assert requests.get(f"{BASE}/api/admin/ledger",
                            headers=_h(S["tara"]["token"])).status_code == 403

    def test_admin_totals_and_travel_commission(self, S):
        r = requests.get(f"{BASE}/api/admin/ledger?direction=in&kind=travel",
                         headers=_h(S["admin"]["token"]))
        assert r.status_code == 200
        j = r.json()
        assert "totals" in j and "collected" in j["totals"]
        # our travel order (7080) should be in the in-rows with commission=1770
        travel_rows = [r for r in j["items"] if r["order_no"] == pytest.travel_order["order_no"]]
        assert travel_rows, "expected our travel order in ledger"
        row = travel_rows[0]
        assert row["reference"].startswith("INV-")
        assert row["gross"] == 7080.0
        assert row["commission"] == 1770.0
        assert row["kind"] == "travel"

    def test_provider_fee_commission_is_whole_amount(self, S):
        r = requests.get(f"{BASE}/api/admin/ledger?direction=in&kind=provider_fee",
                         headers=_h(S["admin"]["token"])).json()
        rows = [x for x in r["items"] if x["kind"] == "provider_fee"]
        assert rows, "expected provider_fee row"
        # commission_for(provider_fee) = whole total
        assert rows[0]["commission"] == rows[0]["gross"]

    def test_out_direction_shows_payouts_with_PO_ref(self, S):
        r = requests.get(f"{BASE}/api/admin/ledger?direction=out",
                         headers=_h(S["admin"]["token"])).json()
        # find travel payout
        travel_p = [x for x in r["items"] if x["kind"] == "travel"]
        assert travel_p, "expected travel payout row"
        assert travel_p[0]["reference"].startswith("PO-")
        assert travel_p[0]["payout"] == 5310.0
        assert travel_p[0]["commission"] == 1770.0

    def test_filter_q_by_order_no(self, S):
        q = pytest.travel_order["order_no"]
        r = requests.get(f"{BASE}/api/admin/ledger?q={q}",
                         headers=_h(S["admin"]["token"])).json()
        assert all(x["order_no"] == q or q.lower() in x.get("description", "").lower()
                   for x in r["items"] if x["direction"] == "in")


# =========================================================== EXPORT
class TestExport:
    def test_export_csv(self, S):
        r = requests.get(f"{BASE}/api/admin/ledger/export?direction=in&kind=travel",
                         headers=_h(S["admin"]["token"]))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "buddilio-ledger" in r.headers.get("content-disposition", "")
        lines = r.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least our travel row
        # audit row written
        assert DB.audit_log.count_documents({"action": "ledger.export"}) >= 1

    def test_export_requires_finance_view(self, S):
        r = requests.get(f"{BASE}/api/admin/ledger/export",
                         headers=_h(S["tara"]["token"]))
        assert r.status_code == 403


# =========================================================== INVOICES / RECEIPTS
class TestInvoice:
    def test_invoice_shape_and_numbers(self, S):
        oid = pytest.travel_order["id"]
        r = requests.get(f"{BASE}/api/orders/{oid}/invoice",
                         headers=_h(S["tara"]["token"]))
        assert r.status_code == 200
        j = r.json()
        order_no = pytest.travel_order["order_no"]
        assert j["invoice_no"] == f"INV-{order_no}"
        assert j["receipt_no"] == f"RCP-{order_no}"  # paid
        assert j["buyer"]["email"] == "tara.joshi@example.com"
        assert j["seller"]["name"] == "Buddilio"
        assert j["total"] == 7080.0
        assert j["commission"] == 1770.0
        assert j["lines"] and j["lines"][0]["amount"] > 0
        assert j["kind"] == "travel"
        assert j["transaction_id"]

    def test_other_member_forbidden_but_finance_view_ok(self, S):
        oid = pytest.travel_order["id"]
        # kabir (the provider) is another member — 403
        r = requests.get(f"{BASE}/api/orders/{oid}/invoice",
                         headers=_h(S["kabir"]["token"]))
        assert r.status_code == 403
        # admin (finance:view) can pull
        r = requests.get(f"{BASE}/api/orders/{oid}/invoice",
                         headers=_h(S["admin"]["token"]))
        assert r.status_code == 200

    def test_bad_and_unknown_ids(self, S):
        r = requests.get(f"{BASE}/api/orders/not-an-id/invoice",
                         headers=_h(S["admin"]["token"]))
        assert r.status_code == 400
        r = requests.get(f"{BASE}/api/orders/{ObjectId()}/invoice",
                         headers=_h(S["admin"]["token"]))
        assert r.status_code == 404
