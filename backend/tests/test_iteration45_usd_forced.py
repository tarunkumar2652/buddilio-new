"""Iteration 45 — re-test of the two HIGH issues from iteration 44.

FIX 1: POST /api/checkout ignores payload currency and always charges BASE_CURRENCY (USD).
FIX 2: GET /api/partner/door-takings converts every row to USD before summing.
Plus credit/wallet/referral-reward conversion and door/pass/refund regressions.

Run with: pytest /app/backend/tests/test_iteration45_usd_forced.py -n 0
PayPal is LIVE — orders are created only, never approved.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")

TRASH = {"order_ids": [], "order_nos": [], "event_ids": []}


def login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=45)
    if r.status_code != 200:
        pytest.fail(f"login {email} -> {r.status_code} {r.text[:300]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin():
    return login(*ADMIN)


@pytest.fixture(scope="session")
def partner():
    return login(*PARTNER)


@pytest.fixture(scope="session")
def member():
    return login(*MEMBER)


@pytest.fixture(scope="session")
def rates():
    r = requests.get(f"{API}/meta", timeout=45)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get("base_currency") == "USD", d.get("base_currency")
    return {c["code"]: float(c["rate"]) for c in d["currencies"]}


def usd_event():
    r = requests.get(f"{API}/events?limit=50", timeout=60)
    evs = r.json().get("items", [])
    return next((e for e in evs if float(e.get("price") or 0) > 0
                 and (e.get("price_currency") or "USD") == "USD"), None)


def do_checkout(sess, kind, item_id, currency="USD", use_credit=False, qty=1):
    r = sess.post(f"{API}/checkout", json={"kind": kind, "item_id": item_id, "quantity": qty,
                                           "coupon_code": "", "currency": currency,
                                           "use_credit": use_credit}, timeout=60)
    assert r.status_code == 200, f"checkout({currency}) {r.status_code} {r.text[:300]}"
    body = r.json()
    o = body["order"]
    TRASH["order_ids"].append(o["id"])
    assert "_id" not in o
    return o, body


# ---------------- FIX 1: checkout currency is display-only ----------------
class TestCheckoutForcedUSD:
    def test_all_display_currencies_produce_identical_usd_order(self, member):
        ev = usd_event()
        assert ev, "no priced USD event available"
        orders = {c: do_checkout(member, "event", ev["id"], currency=c)[0]
                  for c in ("USD", "INR", "AED")}
        for cur, o in orders.items():
            assert o["currency"] == "USD", f"{cur} display -> order currency {o['currency']}"
            assert o["base_currency"] == "USD"
            assert o["fx_rate"] == 1.0, (cur, o["fx_rate"])
            assert o["gateway"] in ("stripe", "paypal"), f"{cur} -> gateway {o['gateway']}"
            assert o["gateway"] != "razorpay_sim"
        ref = orders["USD"]
        for cur in ("INR", "AED"):
            o = orders[cur]
            assert abs(o["charge_total"] - ref["charge_total"]) < 0.01, \
                f"{cur} charge_total {o['charge_total']} != USD {ref['charge_total']}"
            assert abs(o["total"] - ref["total"]) < 0.01
            assert o["tax_percent"] == ref["tax_percent"], (cur, o["tax_percent"], ref["tax_percent"])
            assert o["tax_label"] == ref["tax_label"], (cur, o["tax_label"], ref["tax_label"])
            assert abs(o["charge_total"] - o["total"]) < 0.01

    def test_paypal_amount_equals_usd_charge_total(self, member):
        ev = usd_event()
        o, _ = do_checkout(member, "event", ev["id"], currency="INR")
        r = member.post(f"{API}/payments/paypal/order",
                        json={"order_id": o["id"], "origin_url": BASE}, timeout=90)
        assert r.status_code == 200, f"paypal order {r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["currency"] == "USD", d
        assert abs(float(d["amount"]) - o["charge_total"]) < 0.01, (d["amount"], o["charge_total"])
        assert d.get("approve_url", "").startswith("http")

    def test_membership_and_product_forced_usd(self, member):
        plans = requests.get(f"{API}/plans", timeout=45).json()
        plans = plans if isinstance(plans, list) else plans.get("items", [])
        plan = next((p for p in plans if float(p.get("price") or 0) > 0), None)
        prods = requests.get(f"{API}/products", timeout=45).json().get("items", [])
        prod = next((p for p in prods if float(p.get("price") or 0) > 0), None)
        for kind, item in (("membership", plan), ("product", prod)):
            if not item:
                continue
            o, _ = do_checkout(member, kind, item["id"], currency="INR")
            assert o["currency"] == "USD", (kind, o["currency"])
            assert o["total"] < 2000, (kind, o["total"])
            assert abs(o["charge_total"] - o["total"]) < 0.01

    def test_organiser_non_usd_event_charges_converted_usd(self, partner, member, rates):
        payload = {"title": "TEST45_AED event", "description": "<p>test</p>", "city": "Dubai",
                   "category": "Nightlife", "price": 200, "price_currency": "AED",
                   "starts_at": "2026-12-21T18:00:00Z", "ends_at": "2026-12-21T22:00:00Z",
                   "capacity": 20, "venue": "TEST venue"}
        r = partner.post(f"{API}/partner/events", json=payload, timeout=60)
        assert r.status_code in (200, 201), f"create AED event {r.status_code} {r.text[:400]}"
        ev = r.json()
        eid = ev.get("id") or ev.get("event", {}).get("id")
        assert eid
        TRASH["event_ids"].append(eid)
        o, _ = do_checkout(member, "event", eid, currency="AED")
        assert o["currency"] == "USD", o["currency"]
        expected_sub = round(200 / rates["AED"], 2)
        assert abs(o["subtotal"] - expected_sub) < 1.0, (o["subtotal"], expected_sub)


# ---------------- FIX 2: door takings converted to USD ----------------
class TestDoorTakingsUSD:
    aed_event = None
    usd_event_id = None

    def test_setup_two_door_sales_in_different_currencies(self, partner, rates):
        evs = partner.get(f"{API}/partner/events", timeout=60).json()
        evs = evs.get("items", evs if isinstance(evs, list) else [])
        aed = next((e for e in evs if e.get("price_currency") == "AED"), None)
        usd = next((e for e in evs if (e.get("price_currency") or "USD") == "USD"), None)
        assert aed and usd, "need one AED and one USD event on this organiser"
        TestDoorTakingsUSD.aed_event, TestDoorTakingsUSD.usd_event_id = aed["id"], usd["id"]

        before = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        assert before["currency"] == "USD", before["currency"]

        r1 = partner.post(f"{API}/partner/events/{aed['id']}/walk-in",
                          json={"guest_name": "TEST45_AED Guest", "guest_phone": "9990002222",
                                "quantity": 1, "amount": 25.50, "method": "cash",
                                "check_in_now": False}, timeout=60)
        assert r1.status_code == 200, f"AED walk-in {r1.status_code} {r1.text[:400]}"
        no1 = r1.json()["order_no"]
        TRASH["order_nos"].append(no1)

        r2 = partner.post(f"{API}/partner/events/{usd['id']}/walk-in",
                          json={"guest_name": "TEST45_USD Guest", "guest_phone": "9990003333",
                                "quantity": 2, "amount": 10.00, "method": "cash",
                                "check_in_now": False}, timeout=60)
        assert r2.status_code == 200, f"USD walk-in {r2.status_code} {r2.text[:400]}"
        no2 = r2.json()["order_no"]
        TRASH["order_nos"].append(no2)

        after = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        assert after["currency"] == "USD"
        row1 = next((i for i in after["items"] if i["order_no"] == no1), None)
        row2 = next((i for i in after["items"] if i["order_no"] == no2), None)
        assert row1 and row2, "walk-ins missing from door takings"
        # rows keep their own currency for the table
        assert row1["currency"] == "AED", row1["currency"]
        assert abs(row1["amount"] - 25.50) < 0.01
        assert row2["currency"] == "USD", row2["currency"]
        assert abs(row2["amount"] - 10.00) < 0.01

        expected_delta = round(25.50 / rates["AED"], 2) + 10.00
        got_delta = after["collected"] - before["collected"]
        assert abs(got_delta - expected_delta) < 0.05, \
            f"collected delta {got_delta} != USD-converted {expected_delta} (AED row not converted?)"
        assert after["guests"] - before["guests"] == 3

        owed_delta = after["commission_owed"] - before["commission_owed"]
        expected_owed = round(row1["commission"] / rates["AED"], 2) + row2["commission"]
        assert abs(owed_delta - expected_owed) < 0.05, \
            f"commission_owed delta {owed_delta} != USD-converted {expected_owed}"
        # sanity: the AED row's own commission is bigger than its USD contribution
        assert row1["commission"] > 0

    def test_settlement_paid_moves_to_recovered_in_usd(self, admin, partner, rates):
        no = TRASH["order_nos"][0]          # the AED door sale
        rows = admin.get(f"{API}/admin/vendor-settlements?status=pending", timeout=60).json().get("items", [])
        st = next((s for s in rows if s.get("order_no") == no), None)
        assert st, f"no pending settlement for {no}"
        before = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        p = admin.post(f"{API}/admin/vendor-settlements/{st['id']}/paid",
                       json={"utr": "TEST45-UTR", "note": "TEST45"}, timeout=60)
        assert p.status_code == 200, f"mark paid {p.status_code} {p.text[:400]}"
        after = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        row = next(i for i in after["items"] if i["order_no"] == no)
        assert row["settled"] is True
        usd_commission = round(float(st["commission"]) / rates[row["currency"]], 2)
        assert abs(after["commission_recovered"] - before["commission_recovered"] - usd_commission) < 0.05, \
            (after["commission_recovered"], before["commission_recovered"], usd_commission)
        assert abs(before["commission_owed"] - after["commission_owed"] - usd_commission) < 0.05

    def test_member_cannot_see_rows(self, member):
        r = member.get(f"{API}/partner/door-takings", timeout=60)
        assert r.status_code in (200, 403), r.status_code
        if r.status_code == 200:
            assert r.json()["items"] == []


# ---------------- credits / wallet / referral reward ----------------
class TestCreditWallet:
    def test_referral_reward_is_usd_sized(self, member):
        r = member.get(f"{API}/me/referrals", timeout=45)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert abs(float(d["reward"]) - 3.0) < 0.01, d["reward"]
        assert float(d["balance"]) < 200, f"wallet/credit balance {d['balance']} looks INR-sized"

    def test_credit_applied_at_checkout(self, member):
        bal = float(member.get(f"{API}/me/referrals", timeout=45).json()["balance"])
        ev = usd_event()
        plain, _ = do_checkout(member, "event", ev["id"], use_credit=False)
        o, body = do_checkout(member, "event", ev["id"], use_credit=True)
        if bal <= 0:
            assert o["credit_applied"] == 0
            pytest.skip("member has no credit balance")
        expected = round(min(bal, plain["total"] - 1), 2)
        assert abs(o["credit_applied"] - expected) < 0.02, (o["credit_applied"], expected, bal)
        assert abs(o["total"] - (plain["total"] - o["credit_applied"])) < 0.02
        assert abs(o["charge_total"] - o["total"]) < 0.02
        assert o["currency"] == "USD"


# ---------------- regressions ----------------
class TestRegression:
    def test_walk_in_validation(self, partner):
        eid = TestDoorTakingsUSD.usd_event_id
        assert eid
        r = partner.post(f"{API}/partner/events/{eid}/walk-in",
                         json={"guest_name": "TEST45_NoEmail", "method": "paypal_link",
                               "quantity": 1, "amount": 10}, timeout=60)
        assert r.status_code == 400, f"paypal_link without email -> {r.status_code} {r.text[:200]}"
        r = partner.post(f"{API}/partner/events/{eid}/walk-in",
                         json={"guest_name": "TEST45_Ghost", "method": "paypal_link",
                               "guest_email": "nobody-TEST45@example.com", "quantity": 1,
                               "amount": 10}, timeout=60)
        assert r.status_code == 400, f"paypal_link unknown email -> {r.status_code}"
        r = partner.post(f"{API}/partner/events/{eid}/walk-in",
                         json={"guest_name": "", "method": "cash", "amount": 10}, timeout=60)
        assert r.status_code == 400
        r = partner.post(f"{API}/partner/events/{eid}/walk-in",
                         json={"guest_name": "TEST45_Zero", "method": "cash", "amount": 0}, timeout=60)
        assert r.status_code == 400

    def test_pass_redeem_and_double_redeem(self, partner):
        eid = TestDoorTakingsUSD.usd_event_id
        r = partner.post(f"{API}/partner/events/{eid}/walk-in",
                         json={"guest_name": "TEST45_Redeem", "quantity": 1, "amount": 12.0,
                               "method": "cash", "check_in_now": False}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        TRASH["order_nos"].append(body["order_no"])
        code = (body.get("pass") or {}).get("code") or body.get("code")
        assert code, f"walk-in returned no pass code: {list(body)}"
        r1 = partner.post(f"{API}/passes/{code}/redeem", timeout=60)
        assert r1.status_code == 200, f"redeem {r1.status_code} {r1.text[:300]}"
        r2 = partner.post(f"{API}/passes/{code}/redeem", timeout=60)
        assert r2.status_code in (400, 409), f"double redeem allowed: {r2.status_code}"
        assert "already" in r2.text.lower()

    def test_cancellation_quote(self, member):
        items = member.get(f"{API}/me/orders", timeout=60).json().get("items", [])
        paid = next((o for o in items if o.get("payment_status") == "paid"
                     and o.get("kind") == "event"), None)
        if not paid:
            pytest.skip("no paid event order")
        q = member.get(f"{API}/me/orders/{paid['id']}/cancellation-quote", timeout=60)
        assert q.status_code in (200, 400), f"{q.status_code} {q.text[:300]}"
        if q.status_code == 200:
            d = q.json()
            assert d.get("currency")
            assert float(d.get("refund", 0)) >= 0

    def test_membership_refund_requires_override(self, admin):
        rows = admin.get(f"{API}/admin/orders?kind=membership", timeout=90).json()
        rows = rows.get("items", rows if isinstance(rows, list) else [])
        paid = next((o for o in rows if o.get("payment_status") == "paid"
                     and o.get("kind") == "membership"
                     and o.get("refund_status", "none") == "none"), None)
        if not paid:
            pytest.skip("no refundable paid membership order")
        r = admin.post(f"{API}/admin/orders/{paid['id']}/refund",
                       json={"amount": 1, "reason": ""}, timeout=60)
        assert r.status_code == 400, f"membership refund allowed without override: {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", [
        "/admin/stats", "/admin/orders", "/admin/cancellations", "/admin/ledger",
        "/admin/vendor-settlements", "/admin/payouts", "/admin/paypal/webhook",
    ])
    def test_admin_money_screens(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=90)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"
        assert "NaN" not in r.text, f"{path} returns NaN"
        assert "\u20b9" not in r.text, f"{path} returns a hardcoded rupee symbol"

    def test_invoice_renders(self, member):
        items = member.get(f"{API}/me/orders", timeout=60).json().get("items", [])
        paid = next((o for o in items if o.get("payment_status") == "paid"), None)
        if not paid:
            pytest.skip("no paid order")
        r = member.get(f"{API}/orders/{paid['id']}/invoice", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("currency") or d.get("order", {}).get("currency")

    def test_payment_config_base_currency(self):
        r = requests.get(f"{API}/payments/config", timeout=45)
        if r.status_code == 404:
            pytest.skip("no public payment config endpoint")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("base_currency") == "USD", d


# ---------------- cleanup ----------------
def test_zz_cleanup():
    import asyncio

    from bson import ObjectId
    from dotenv import dotenv_values as dv
    from motor.motor_asyncio import AsyncIOMotorClient

    be = dv("/app/backend/.env")

    async def run():
        cli = AsyncIOMotorClient(be["MONGO_URL"])
        db = cli[be["DB_NAME"]]
        removed = {"door": 0, "pending": 0, "events": 0}
        for no in TRASH["order_nos"]:
            o = await db.orders.find_one({"order_no": no})
            if not o:
                continue
            oid = str(o["_id"])
            await db.passes.delete_many({"order_id": oid})
            await db.payments.delete_many({"order_id": oid})
            await db.vendor_settlements.delete_many({"order_no": no})
            await db.event_participants.delete_many({"order_id": oid})
            if o.get("ref_id"):
                await db.events.update_one({"_id": ObjectId(o["ref_id"])},
                                           {"$inc": {"participant_count": -int(o.get("quantity") or 1)}})
            await db.orders.delete_one({"_id": o["_id"]})
            removed["door"] += 1
        ids = [ObjectId(i) for i in TRASH["order_ids"]]
        if ids:
            res = await db.orders.delete_many({"_id": {"$in": ids}, "payment_status": "pending"})
            removed["pending"] = res.deleted_count
        for eid in TRASH["event_ids"]:
            await db.events.delete_one({"_id": ObjectId(eid)})
            removed["events"] += 1
        await db.events.delete_many({"title": "TEST45_AED event"})
        left = await db.orders.count_documents({"item_name": "TEST45_AED event"})
        cli.close()
        return removed, left

    removed, left = asyncio.run(run())
    print("cleanup:", removed, "leftover TEST45 orders:", left)
    assert left == 0
