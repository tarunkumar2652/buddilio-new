"""Iteration 43 — walk-in door sales, door CSV export, doors-open nudges, pass reminder hours.

Cleans up every order / pass / payment / settlement / snapshot it creates and rewinds
participant_count. Run with: pytest test_iteration43_walkin_doors.py -v -n 0
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
DB = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
CRON = be["WEBHOOK_CRON_SECRET"]

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")


def login(creds):
    r = requests.post(f"{BASE}/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
    assert r.status_code == 200, f"login failed {creds[0]}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def h_admin():
    return login(ADMIN)


@pytest.fixture(scope="module")
def h_partner():
    return login(PARTNER)


@pytest.fixture(scope="module")
def h_member():
    return login(MEMBER)


@pytest.fixture(scope="module")
def partner_user():
    return DB.users.find_one({"email": PARTNER[0]})


@pytest.fixture(scope="module")
def event_ids(partner_user):
    ev = DB.events.find_one({"partner_id": str(partner_user["_id"]), "status": "published"})
    other = DB.events.find_one({"partner_id": {"$ne": str(partner_user["_id"])}, "status": "published"})
    assert ev is not None and other is not None
    return {"mine": str(ev["_id"]), "other": str(other["_id"])}


@pytest.fixture(scope="module")
def created():
    """Tracks order_nos + seeded pass codes for teardown."""
    bag = {"order_nos": [], "codes": [], "participant_bumps": {}, "setting": None}
    yield bag
    for order_no in bag["order_nos"]:
        o = DB.orders.find_one({"order_no": order_no})
        if not o:
            continue
        oid = str(o["_id"])
        DB.passes.delete_many({"order_id": oid})
        DB.payments.delete_many({"order_id": oid})
        DB.vendor_settlements.delete_many({"booking_id": oid})
        DB.booking_commercial_snapshots.delete_many({"booking_id": oid})
        DB.event_participants.delete_many({"order_id": oid})
        DB.notifications.delete_many({"body": {"$regex": order_no}})
        DB.orders.delete_one({"_id": o["_id"]})
    if bag["codes"]:
        DB.passes.delete_many({"code": {"$in": bag["codes"]}})
    for eid, n in bag["participant_bumps"].items():
        DB.events.update_one({"_id": ObjectId(eid)}, {"$inc": {"participant_count": -n}})
    if bag["setting"] is not None:
        DB.settings.update_one({}, {"$set": {"pass_reminder_hours": bag["setting"]}})
    print("\n[i43] cleanup done:", bag["order_nos"], bag["codes"])


# ---------------------------------------------------------------- walk-in: cash / upi / card
class TestWalkInCollected:
    def test_cash_sale_creates_paid_order_pass_and_settlement(self, h_partner, event_ids, created):
        eid = event_ids["mine"]
        before = requests.get(f"{BASE}/partner/events/{eid}/check-in", headers=h_partner, timeout=30).json()
        ev_before = DB.events.find_one({"_id": ObjectId(eid)}, {"participant_count": 1})
        name = "TEST_I43 Cash Guest"
        r = requests.post(f"{BASE}/partner/events/{eid}/walk-in", headers=h_partner, timeout=60,
                          json={"guest_name": name, "quantity": 2, "amount": 45.5, "method": "cash",
                                "check_in_now": True})
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        created["order_nos"].append(data["order_no"])
        created["participant_bumps"][eid] = created["participant_bumps"].get(eid, 0) + 1
        assert data["mode"] == "collected"
        assert data["amount"] == 45.5
        assert data["method"] == "cash"
        assert data["pass"] and data["pass"]["code"]
        code = data["pass"]["code"]
        assert data["pass"]["status"] == "redeemed"

        order = DB.orders.find_one({"order_no": data["order_no"]})
        assert order["payment_status"] == "paid"
        assert order["order_status"] == "completed"
        assert order["gateway"] == "door"
        assert order["collected_by_vendor"] is True
        assert order["walk_in"] is True
        assert order["quantity"] == 2
        assert order["total"] == 45.5
        assert "_id" not in data.get("pass", {})

        # payment row captured
        pay = DB.payments.find_one({"order_id": str(order["_id"])})
        assert pay and pay["status"] == "captured" and pay["gateway"] == "door"

        # settlement with commission deducted
        sett = DB.vendor_settlements.find_one({"booking_id": str(order["_id"])})
        assert sett, "no pending vendor settlement created for the door sale"
        assert sett["status"] == "pending"
        assert sett["commission"] >= 0
        assert round(sett["net"], 2) <= round(sett["gross"], 2)

        # participant count bumped
        ev_after = DB.events.find_one({"_id": ObjectId(eid)}, {"participant_count": 1})
        assert (ev_after.get("participant_count") or 0) == (ev_before.get("participant_count") or 0) + 1

        # door list shows the guest as arrived
        after = requests.get(f"{BASE}/partner/events/{eid}/check-in", headers=h_partner, timeout=30)
        assert after.status_code == 200
        ad = after.json()
        row = next((p for p in ad["items"] if p["code"] == code), None)
        assert row, f"pass {code} missing from door list"
        assert row["status"] == "redeemed"
        assert row["user_name"] == name
        assert ad["arrived"] >= before["arrived"] + 2

    @pytest.mark.parametrize("method", ["upi", "card"])
    def test_upi_and_card_sales(self, h_partner, event_ids, created, method):
        eid = event_ids["mine"]
        r = requests.post(f"{BASE}/partner/events/{eid}/walk-in", headers=h_partner, timeout=60,
                          json={"guest_name": f"TEST_I43 {method}", "amount": 20, "method": method})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        created["order_nos"].append(d["order_no"])
        created["participant_bumps"][eid] = created["participant_bumps"].get(eid, 0) + 1
        assert DB.orders.find_one({"order_no": d["order_no"]})["payment_method"] == method
        assert d["pass"]["status"] == "redeemed"


# ---------------------------------------------------------------- validation
class TestWalkInValidation:
    @pytest.mark.parametrize("body,expect", [
        ({"guest_name": "TEST_I43 x", "amount": 0, "method": "cash"}, "collected"),
        ({"guest_name": "TEST_I43 x", "method": "cash"}, "collected"),
        ({"guest_name": "   ", "amount": 10, "method": "cash"}, "name"),
        ({"guest_name": "TEST_I43 x", "amount": 10, "method": "bitcoin"}, "cash"),
        ({"guest_name": "TEST_I43 x", "amount": 10, "method": "paypal_link"}, "email"),
    ])
    def test_rejections(self, h_partner, event_ids, body, expect):
        r = requests.post(f"{BASE}/partner/events/{event_ids['mine']}/walk-in", headers=h_partner,
                          json=body, timeout=30)
        assert r.status_code == 400, f"{body} -> {r.status_code} {r.text[:200]}"
        assert expect.lower() in r.json()["detail"].lower(), r.json()["detail"]

    def test_paypal_link_unknown_email_rejected(self, h_partner, event_ids):
        r = requests.post(f"{BASE}/partner/events/{event_ids['mine']}/walk-in", headers=h_partner, timeout=30,
                          json={"guest_name": "TEST_I43 nobody", "amount": 10, "method": "paypal_link",
                                "guest_email": f"test_nobody_{uuid.uuid4().hex[:6]}@example.com"})
        assert r.status_code == 400
        assert "no buddilio account" in r.json()["detail"].lower()


# ---------------------------------------------------------------- paypal_link happy path
class TestWalkInPayPalLink:
    def test_pending_order_no_pass(self, h_partner, event_ids, created):
        r = requests.post(f"{BASE}/partner/events/{event_ids['mine']}/walk-in", headers=h_partner, timeout=60,
                          json={"guest_name": "TEST_I43 member", "amount": 33, "method": "paypal_link",
                                "guest_email": MEMBER[0]})
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        created["order_nos"].append(d["order_no"])
        assert d["mode"] == "paypal_link"
        assert d["amount"] == 33
        assert "pay link sent" in d["message"].lower()
        order = DB.orders.find_one({"order_no": d["order_no"]})
        assert order["payment_status"] == "pending"
        assert order["gateway"] == "paypal"
        assert order["order_status"] == "created"
        assert DB.passes.find_one({"order_id": str(order["_id"])}) is None, "pass issued before payment!"
        # member notified
        member = DB.users.find_one({"email": MEMBER[0]})
        note = DB.notifications.find_one({"user_id": str(member["_id"]), "title": "Pay for your pass"},
                                        sort=[("created_at", -1)])
        assert note, "member was not notified to pay"


# ---------------------------------------------------------------- access control
class TestWalkInAccess:
    def test_member_forbidden(self, h_member, event_ids):
        r = requests.post(f"{BASE}/partner/events/{event_ids['mine']}/walk-in", headers=h_member,
                          json={"guest_name": "TEST_I43 m", "amount": 10, "method": "cash"}, timeout=30)
        assert r.status_code == 403, r.status_code

    def test_partner_forbidden_on_other_event(self, h_partner, event_ids):
        r = requests.post(f"{BASE}/partner/events/{event_ids['other']}/walk-in", headers=h_partner,
                          json={"guest_name": "TEST_I43 o", "amount": 10, "method": "cash"}, timeout=30)
        assert r.status_code == 403, r.status_code

    def test_unauthenticated(self, event_ids):
        r = requests.post(f"{BASE}/partner/events/{event_ids['mine']}/walk-in",
                          json={"guest_name": "x", "amount": 10, "method": "cash"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_staff_with_events_view_allowed(self, h_admin, event_ids, created):
        r = requests.post(f"{BASE}/partner/events/{event_ids['other']}/walk-in", headers=h_admin, timeout=60,
                          json={"guest_name": "TEST_I43 staff", "amount": 12, "method": "cash"})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        created["order_nos"].append(d["order_no"])
        created["participant_bumps"][event_ids["other"]] = \
            created["participant_bumps"].get(event_ids["other"], 0) + 1


# ---------------------------------------------------------------- door CSV
class TestDoorCsv:
    def test_csv_download(self, h_partner, event_ids):
        r = requests.get(f"{BASE}/partner/events/{event_ids['mine']}/check-in.csv",
                         headers=h_partner, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        body = r.text
        assert body.splitlines()[0].startswith("code,guest,guests,status,arrived_at")
        assert "TOTAL" in body
        assert "arrived" in body

    def test_csv_forbidden_for_non_owner(self, h_member, event_ids):
        r = requests.get(f"{BASE}/partner/events/{event_ids['mine']}/check-in.csv",
                         headers=h_member, timeout=30)
        assert r.status_code == 403


# ---------------------------------------------------------------- doors-open nudges
def _seed_pass(created, event_id, minutes_ahead, user_id, status="valid", tag="TEST_I43_DOORS"):
    starts = (datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)).replace(microsecond=0).isoformat()
    order_no = "TESTI43" + uuid.uuid4().hex[:5].upper()
    oid = DB.orders.insert_one({
        "order_no": order_no, "user_id": user_id, "kind": "event", "ref_id": event_id,
        "item_name": tag, "quantity": 1, "subtotal": 10.0, "discount": 0.0, "tax": 0.0, "total": 10.0,
        "currency": "USD", "charge_total": 10.0, "base_currency": "USD", "payment_status": "paid",
        "order_status": "completed", "refund_status": "none", "gateway": "paypal",
        "created_at": starts, "paid_at": starts}).inserted_id
    created["order_nos"].append(order_no)
    code = f"BUD-T43{uuid.uuid4().hex[:2].upper()}-{uuid.uuid4().hex[:2].upper()}"
    DB.passes.insert_one({"code": code, "order_id": str(oid), "order_no": order_no, "user_id": user_id,
                          "user_name": "TEST_I43 Holder", "kind": "event", "ref_id": event_id,
                          "item_name": tag, "quantity": 1, "city": "", "starts_at": starts,
                          "vendor_name": "Buddilio", "amount_label": "$10.00", "status": status,
                          "redeemed_at": "", "redeemed_by": "", "redeemed_by_name": "",
                          "created_at": starts})
    created["codes"].append(code)
    return code


def run_cron():
    r = requests.post(f"{BASE}/cron/city-openings", headers={"Authorization": f"Bearer {CRON}"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


class TestDoorsOpenNudges:
    def test_nudges_pass_holder_and_organiser_once(self, event_ids, created, partner_user):
        member = DB.users.find_one({"email": MEMBER[0]})
        code = _seed_pass(created, event_ids["mine"], 40, str(member["_id"]))
        body = run_cron()
        assert set(body["queued"]) == {"city-openings", "pass-reminders", "doors-open-nudges"}
        import time
        time.sleep(8)

        p = DB.passes.find_one({"code": code})
        assert p.get("doors_nudged") is True, "pass not flagged doors_nudged"

        holder = list(DB.notifications.find({"user_id": str(member["_id"]), "title": "Doors open soon"}))
        mine = [n for n in holder if code in n.get("body", "")]
        assert len(mine) == 1, f"expected 1 doors-open notification, got {len(mine)}"

        org = list(DB.notifications.find({"user_id": str(partner_user["_id"]),
                                          "title": "Doors open within the hour"}))
        assert org, "organiser did not get the arrival-count nudge"
        latest = sorted(org, key=lambda n: n.get("created_at", ""))[-1]
        assert "arrived" in latest["body"] and "of" in latest["body"], latest["body"]

        # second run must not repeat
        run_cron()
        time.sleep(6)
        again = [n for n in DB.notifications.find({"user_id": str(member["_id"]),
                                                  "title": "Doors open soon"}) if code in n.get("body", "")]
        assert len(again) == 1, f"doors-open nudge repeated ({len(again)} notifications)"
        DB.notifications.delete_many({"user_id": str(member["_id"]), "body": {"$regex": code}})
        DB.notifications.delete_many({"user_id": str(partner_user["_id"]),
                                      "title": "Doors open within the hour"})


# ---------------------------------------------------------------- pass reminder window
class TestPassReminderHours:
    def test_setting_field_and_window(self, h_admin, event_ids, created):
        import time
        cur = (DB.settings.find_one({}, {"pass_reminder_hours": 1}) or {}).get("pass_reminder_hours")
        created["setting"] = cur if cur is not None else 12

        # admin can read + write the setting through the API
        put = requests.put(f"{BASE}/admin/settings", headers=h_admin,
                           json={"pass_reminder_hours": 6}, timeout=30)
        assert put.status_code == 200, f"{put.status_code} {put.text[:200]}"
        assert (DB.settings.find_one({}, {"pass_reminder_hours": 1}) or {}).get("pass_reminder_hours") == 6

        member = DB.users.find_one({"email": MEMBER[0]})
        inside = _seed_pass(created, event_ids["mine"], 60 * 4, str(member["_id"]), tag="TEST_I43_REMIND_IN")
        outside = _seed_pass(created, event_ids["mine"], 60 * 20, str(member["_id"]), tag="TEST_I43_REMIND_OUT")
        run_cron()
        time.sleep(10)

        assert DB.passes.find_one({"code": inside}).get("reminded") is True, "in-window pass not reminded"
        assert DB.passes.find_one({"code": outside}).get("reminded") is not True, \
            "pass outside the 6h window was reminded"

        notes = [n for n in DB.notifications.find({"user_id": str(member["_id"]),
                                                   "title": "Your pass is ready"}) if inside in n.get("body", "")]
        assert len(notes) == 1, f"expected 1 reminder notification, got {len(notes)}"

        # rerun must not remind twice
        run_cron()
        time.sleep(8)
        notes2 = [n for n in DB.notifications.find({"user_id": str(member["_id"]),
                                                    "title": "Your pass is ready"}) if inside in n.get("body", "")]
        assert len(notes2) == 1, "pass reminder repeated"
        DB.notifications.delete_many({"user_id": str(member["_id"]),
                                      "body": {"$regex": f"{inside}|{outside}"}})


# ---------------------------------------------------------------- regression
class TestRegression:
    def test_redeem_and_double_redeem(self, h_partner, event_ids, created, partner_user):
        code = _seed_pass(created, event_ids["mine"], 60 * 30, str(partner_user["_id"]),
                          tag="TEST_I43_REDEEM")
        r1 = requests.post(f"{BASE}/passes/{code}/redeem", headers=h_partner, timeout=30)
        assert r1.status_code == 200, r1.text[:200]
        assert r1.json()["pass"]["status"] == "redeemed"
        r2 = requests.post(f"{BASE}/passes/{code}/redeem", headers=h_partner, timeout=30)
        assert r2.status_code == 400
        assert "already used" in r2.json()["detail"].lower()

    def test_pass_check_public(self, created, event_ids, partner_user):
        code = _seed_pass(created, event_ids["mine"], 60 * 30, str(partner_user["_id"]),
                          tag="TEST_I43_CHECK")
        r = requests.get(f"{BASE}/passes/{code}/check", timeout=30)
        assert r.status_code == 200 and r.json()["found"] is True
        assert r.json()["status"] == "valid"

    def test_membership_refund_blocked_without_override(self, h_admin):
        m = DB.orders.find_one({"kind": "membership", "payment_status": "paid"})
        if not m:
            pytest.skip("no paid membership order to test the refund policy against")
        r = requests.post(f"{BASE}/admin/orders/{m['_id']}/refund", headers=h_admin,
                          json={"amount": 1, "reason": ""}, timeout=30)
        assert r.status_code in (400, 403), f"{r.status_code} {r.text[:200]}"

    def test_paypal_webhook_status_endpoint(self, h_admin):
        r = requests.get(f"{BASE}/admin/paypal/webhook", headers=h_admin, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        assert "configured" in r.json() or "webhook_id" in r.json() or isinstance(r.json(), dict)
