"""Iteration 44 — USD currency rebase + organiser door-takings report."""
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
def meta():
    r = requests.get(f"{API}/meta", timeout=45)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---------------- A. base currency = USD ----------------
class TestBaseCurrency:
    def test_meta_base_currency_usd(self, meta):
        assert meta.get("base_currency") == "USD", meta.get("base_currency")
        table = {c["code"]: c for c in meta["currencies"]}
        assert table["USD"]["rate"] == 1.0, table["USD"]
        assert 80 <= table["INR"]["rate"] <= 90, table["INR"]
        assert abs(table["AED"]["rate"] - 3.67) < 0.2, table["AED"]

    def test_membership_plans_usd_sized(self):
        r = requests.get(f"{API}/plans", timeout=45)
        assert r.status_code == 200, r.text[:300]
        plans = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert plans, "no plans returned"
        for p in plans:
            assert 0 <= float(p["price"]) < 2000, f"{p.get('name')} price {p['price']} looks INR-sized"

    def test_events_usd_sized(self):
        r = requests.get(f"{API}/events?limit=50", timeout=60)
        assert r.status_code == 200, r.text[:300]
        evs = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        assert evs, "no events"
        bad = [(e["title"], e["price"], e.get("price_currency"))
               for e in evs
               if (e.get("price_currency") or "USD") == "USD" and float(e.get("price") or 0) > 2000]
        assert not bad, f"USD events priced INR-sized: {bad}"

    def test_products_usd_sized(self):
        r = requests.get(f"{API}/products", timeout=45)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        bad = [(p.get("name"), p.get("price")) for p in items if float(p.get("price") or 0) > 2000]
        assert not bad, f"products priced INR-sized: {bad}"

    def test_coupons_usd_sized(self, admin):
        r = admin.get(f"{API}/admin/coupons", timeout=45)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        bad = [(c.get("code"), c.get("value"), c.get("min_order")) for c in items
               if c.get("discount_type") != "percent" and (
                   float(c.get("value") or 0) > 1000 or float(c.get("min_order") or 0) > 5000)]
        assert not bad, f"coupons still INR-sized: {bad}"


# ---------------- B. checkout maths in USD ----------------
def _first_event():
    r = requests.get(f"{API}/events?limit=50", timeout=60)
    evs = r.json().get("items", [])
    return next((e for e in evs if float(e.get("price") or 0) > 0
                 and (e.get("price_currency") or "USD") == "USD"), None)


class TestCheckoutMaths:
    created = []

    @classmethod
    def teardown_class(cls):
        pass  # pending orders are harmless; cleaned in test_cleanup

    def _checkout(self, sess, kind, item_id, currency="USD"):
        r = sess.post(f"{API}/checkout", json={"kind": kind, "item_id": item_id, "quantity": 1,
                                               "coupon_code": "", "currency": currency,
                                               "use_credit": False}, timeout=60)
        assert r.status_code == 200, f"{kind} checkout {r.status_code} {r.text[:300]}"
        o = r.json()["order"]
        TestCheckoutMaths.created.append(o["id"])
        assert "_id" not in o
        return o

    def test_event_checkout_usd(self, member):
        ev = _first_event()
        assert ev, "no priced USD event found"
        o = self._checkout(member, "event", ev["id"])
        assert o["currency"] == "USD"
        assert o["base_currency"] == "USD"
        assert abs(o["subtotal"] - float(ev["price"])) < 0.02, (o["subtotal"], ev["price"])
        assert abs(o["total"] - (o["subtotal"] - o["discount"] + o["tax"])) < 0.02
        assert abs(o["charge_total"] - o["total"]) < 0.01, "USD charge_total must equal total"
        assert o["total"] < 2000, f"total {o['total']} looks INR-sized"

    def test_product_checkout_usd(self, member):
        items = requests.get(f"{API}/products", timeout=45).json().get("items", [])
        prod = next((p for p in items if float(p.get("price") or 0) > 0), None)
        assert prod, "no priced product"
        o = self._checkout(member, "product", prod["id"])
        assert o["currency"] == "USD"
        assert abs(o["charge_total"] - o["total"]) < 0.01
        expected = round(float(prod["price"]) * (1 - float(prod.get("discount_percent") or 0) / 100), 2)
        assert abs(o["subtotal"] - expected) < 0.02, (o["subtotal"], expected)
        assert o["total"] < 2000

    def test_membership_checkout_usd(self, member):
        plans = requests.get(f"{API}/plans", timeout=45).json()
        plans = plans if isinstance(plans, list) else plans.get("items", [])
        plan = next((p for p in plans if float(p.get("price") or 0) > 0), None)
        assert plan, "no priced plan"
        o = self._checkout(member, "membership", plan["id"])
        assert o["currency"] == "USD"
        assert abs(o["charge_total"] - o["total"]) < 0.01
        assert o["total"] < 2000

    def test_paypal_order_amount_matches_usd_charge_total(self, member):
        ev = _first_event()
        o = self._checkout(member, "event", ev["id"])
        r = member.post(f"{API}/payments/paypal/order",
                        json={"order_id": o["id"], "origin_url": BASE}, timeout=90)
        assert r.status_code == 200, f"paypal order {r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["currency"] == "USD"
        assert abs(float(d["amount"]) - o["charge_total"]) < 0.01, (d["amount"], o["charge_total"])
        assert d.get("approve_url", "").startswith("http")

    def test_display_currency_switch_does_not_misscale_paypal(self, member):
        """Switching display currency to INR must still result in a correct USD PayPal amount."""
        ev = _first_event()
        usd = self._checkout(member, "event", ev["id"], currency="USD")
        inr = self._checkout(member, "event", ev["id"], currency="INR")
        rate = {c["code"]: c["rate"] for c in requests.get(f"{API}/meta", timeout=45).json()["currencies"]}["INR"]
        assert inr["currency"] == "INR"
        # INR order charge_total should be the USD total scaled by the rate (same real-world price)
        assert abs(inr["charge_total"] - inr["total"] * rate) < 1.0, (inr["charge_total"], inr["total"], rate)
        r = member.post(f"{API}/payments/paypal/order",
                        json={"order_id": inr["id"], "origin_url": BASE}, timeout=90)
        assert r.status_code == 200, r.text[:400]
        amt = float(r.json()["amount"])
        assert abs(amt - inr["total"]) < 0.01, "paypal amount must be the order base (USD) total"
        # DEFECT: display-currency choice changes the tax jurisdiction, so the USD amount actually
        # charged differs for the same item (US 16% GST vs IN 18% vs AE 5%).
        assert abs(amt - usd["charge_total"]) < 0.05, \
            f"PayPal amount {amt} for INR-display order != USD total {usd['charge_total']} " \
            f"(tax {inr['tax_percent']}% vs {usd['tax_percent']}%)"


# ---------------- C. organiser priced in a non-USD currency ----------------
class TestOrganiserCurrency:
    event_id = None

    def test_create_aed_event_and_checkout(self, partner, member):
        payload = {"title": "TEST_AED door event", "description": "<p>test</p>", "city": "Dubai",
                   "category": "Nightlife", "price": 200, "price_currency": "AED",
                   "starts_at": "2026-12-20T18:00:00Z", "ends_at": "2026-12-20T22:00:00Z",
                   "capacity": 20, "venue": "TEST venue"}
        r = partner.post(f"{API}/partner/events", json=payload, timeout=60)
        assert r.status_code in (200, 201), f"create AED event {r.status_code} {r.text[:400]}"
        ev = r.json()
        TestOrganiserCurrency.event_id = ev.get("id") or ev.get("event", {}).get("id")
        assert TestOrganiserCurrency.event_id
        lst = partner.get(f"{API}/partner/events", timeout=60).json()
        lst = lst.get("items", lst if isinstance(lst, list) else [])
        got = next(x for x in lst if x["id"] == TestOrganiserCurrency.event_id)
        assert got["price_currency"] == "AED"
        assert abs(float(got["price_overrides"]["AED"]) - 200) < 0.01, got.get("price_overrides")
        assert abs(float(got["price"]) - 200 / 3.67) < 1.0, got["price"]

        r = member.post(f"{API}/checkout", json={"kind": "event", "item_id": TestOrganiserCurrency.event_id,
                                                 "quantity": 1, "currency": "AED", "use_credit": False},
                        timeout=60)
        assert r.status_code == 200, r.text[:400]
        o = r.json()["order"]
        assert o["currency"] == "AED"
        assert abs(o["charge_subtotal"] - 200) < 0.01, f"organiser exact AED amount lost: {o['charge_subtotal']}"



# ---------------- D. receipts / orders currency ----------------
class TestOrdersCurrency:
    def test_member_orders_render(self, member):
        r = member.get(f"{API}/me/orders", timeout=60)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        assert items, "member has no orders"
        for o in items:
            assert o.get("currency"), f"order {o.get('order_no')} has no currency"
            assert "_id" not in o

    def test_invoice_of_paid_order(self, member):
        items = member.get(f"{API}/me/orders", timeout=60).json().get("items", [])
        paid = next((o for o in items if o.get("payment_status") == "paid"), None)
        if not paid:
            pytest.skip("no paid order to invoice")
        r = member.get(f"{API}/orders/{paid['id']}/invoice", timeout=60)
        assert r.status_code == 200, f"invoice {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("currency") or d.get("order", {}).get("currency")


# ---------------- E. door takings report ----------------
class TestDoorTakings:
    order_no = None
    order_id = None
    settlement_id = None
    event_id = None
    qty = 2
    amount = 40.0

    def test_partner_report_shape(self, partner):
        r = partner.get(f"{API}/partner/door-takings", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        for k in ("items", "collected", "commission_owed", "commission_recovered", "guests", "currency"):
            assert k in d, f"missing {k}"
        assert isinstance(d["items"], list)

    def test_member_sees_nothing(self, member):
        r = member.get(f"{API}/partner/door-takings", timeout=60)
        assert r.status_code in (200, 403), r.status_code
        if r.status_code == 200:
            assert r.json()["items"] == [], "plain member sees door takings rows"

    def test_walk_in_appears_in_report(self, partner):
        evs = partner.get(f"{API}/partner/events", timeout=60).json()
        evs = evs.get("items", evs if isinstance(evs, list) else [])
        ev = next((e for e in evs if (e.get("price_currency") or "USD") == "USD"), None) or evs[0]
        TestDoorTakings.event_id = ev["id"]
        before = partner.get(f"{API}/partner/door-takings", timeout=60).json()

        r = partner.post(f"{API}/partner/events/{ev['id']}/walk-in",
                         json={"guest_name": "TEST_Door Guest", "guest_phone": "9990001111",
                               "quantity": self.qty, "amount": self.amount, "method": "cash",
                               "check_in_now": False}, timeout=60)
        assert r.status_code == 200, f"walk-in {r.status_code} {r.text[:400]}"
        res = r.json()
        assert res["mode"] == "collected"
        TestDoorTakings.order_no = res["order_no"]

        after = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        row = next((i for i in after["items"] if i["order_no"] == self.order_no), None)
        assert row, f"walk-in {self.order_no} missing from door-takings"
        assert abs(row["amount"] - self.amount) < 0.01
        assert row["method"] == "cash"
        assert row["guests"] == self.qty
        assert row["settled"] is False
        assert row["commission"] >= 0
        assert abs(after["collected"] - before["collected"] - self.amount) < 0.01
        assert after["guests"] - before["guests"] == self.qty
        assert abs(after["commission_owed"] - before["commission_owed"] - row["commission"]) < 0.01

    def test_other_organiser_cannot_see_row(self, admin):
        """Admin logs in as a different organiser context - its own events only."""
        r = admin.get(f"{API}/partner/door-takings", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = [i["order_no"] for i in r.json()["items"]]
        assert self.order_no not in rows, "another account can see this organiser's door sale"

    def test_settlement_paid_moves_owed_to_recovered(self, admin, partner):
        r = admin.get(f"{API}/admin/vendor-settlements?status=pending", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json().get("items", [])
        st = next((s for s in rows if s.get("order_no") == self.order_no), None)
        assert st, f"no pending settlement for door sale {self.order_no}"
        TestDoorTakings.settlement_id = st["id"]
        commission = float(st["commission"])
        before = partner.get(f"{API}/partner/door-takings", timeout=60).json()

        p = admin.post(f"{API}/admin/vendor-settlements/{st['id']}/paid",
                       json={"utr": "TEST-UTR-44", "note": "TEST"}, timeout=60)
        assert p.status_code == 200, f"mark paid {p.status_code} {p.text[:400]}"

        after = partner.get(f"{API}/partner/door-takings", timeout=60).json()
        row = next(i for i in after["items"] if i["order_no"] == self.order_no)
        assert row["settled"] is True
        assert abs(after["commission_recovered"] - before["commission_recovered"] - commission) < 0.01
        assert abs(before["commission_owed"] - after["commission_owed"] - commission) < 0.01


# ---------------- F. regression on money screens ----------------
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/admin/stats", "/admin/orders", "/admin/cancellations", "/admin/ledger",
        "/admin/vendor-settlements", "/admin/payouts",
    ])
    def test_admin_money_screens(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=90)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"
        body = r.text
        assert "NaN" not in body, f"{path} returns NaN"

    def test_partner_dashboard(self, partner):
        r = partner.get(f"{API}/partner/stats", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("revenue", "payout_due", "payout_paid"):
            assert isinstance(d.get(k), (int, float)), (k, d.get(k))

    def test_vendor_payouts_and_invoices(self, admin):
        for path in ("/admin/vendor-commission-invoices", "/admin/vendor-scorecards"):
            r = admin.get(f"{API}{path}", timeout=90)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"

    def test_refund_policy_and_cancellation_quote(self, member):
        r = requests.get(f"{API}/me/ledger", timeout=45)
        assert r.status_code in (401, 403), r.status_code
        items = member.get(f"{API}/me/orders", timeout=60).json().get("items", [])
        paid = next((o for o in items if o.get("payment_status") == "paid"
                     and o.get("kind") == "event"), None)
        if not paid:
            pytest.skip("no paid event order for cancellation quote")
        q = member.get(f"{API}/me/orders/{paid['id']}/cancellation-quote", timeout=60)
        assert q.status_code in (200, 400), f"{q.status_code} {q.text[:300]}"
        if q.status_code == 200:
            d = q.json()
            assert d.get("currency")
            assert float(d.get("refund", 0)) >= 0


# ---------------- G. cleanup ----------------
def test_cleanup(partner, admin):
    """Remove test-created walk-in order, pass, payment, settlement and restore counts."""
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import dotenv_values as dv
    be = dv("/app/backend/.env")
    from bson import ObjectId

    async def run():
        cli = AsyncIOMotorClient(be["MONGO_URL"])
        db = cli[be["DB_NAME"]]
        no = TestDoorTakings.order_no
        removed = {}
        if no:
            o = await db.orders.find_one({"order_no": no})
            if o:
                await db.passes.delete_many({"order_id": str(o["_id"])})
                await db.payments.delete_many({"order_id": str(o["_id"])})
                await db.vendor_settlements.delete_many({"order_no": no})
                await db.event_participants.delete_many({"order_id": str(o["_id"])})
                if o.get("ref_id"):
                    await db.events.update_one({"_id": ObjectId(o["ref_id"])},
                                               {"$inc": {"participant_count": -int(o.get("quantity") or 1)}})
                await db.orders.delete_one({"_id": o["_id"]})
                removed["walk_in"] = no
        # pending checkout orders created by the tests
        ids = [ObjectId(i) for i in TestCheckoutMaths.created]
        if ids:
            res = await db.orders.delete_many({"_id": {"$in": ids}, "payment_status": "pending"})
            removed["pending_orders"] = res.deleted_count
        await db.events.delete_many({"title": "TEST_AED door event"})
        await db.orders.delete_many({"item_name": "TEST_AED door event", "payment_status": "pending"})
        cli.close()
        return removed

    print("cleanup:", asyncio.get_event_loop().run_until_complete(run())
          if False else asyncio.run(run()))
