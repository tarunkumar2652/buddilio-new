"""Iteration 46 — focused re-test of iteration_45 action items (currency labelling)."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = BASE_URL + "/api"


def _creds():
    txt = Path("/app/memory/test_credentials.md").read_text()
    return txt


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login {email} -> {r.status_code} {r.text[:300]}")
    tok = r.json().get("access_token")
    assert tok, f"no access_token for {email}: {r.text[:200]}"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@buddilio.com", "Admin@123")


@pytest.fixture(scope="module")
def partner():
    return _login("partner@buddilio.com", "Partner@123")


@pytest.fixture(scope="module")
def member():
    return _login("arjun.sethi@example.com", "User@12345")


@pytest.fixture(scope="module")
def fx(admin):
    r = requests.get(f"{API}/meta", timeout=60)
    assert r.status_code == 200, f"meta unavailable: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("base_currency") == "USD", f"base_currency={body.get('base_currency')}"
    rates = {c["code"].upper(): float(c.get("rate", 1)) for c in body["currencies"]}
    assert rates.get("INR"), f"no INR rate in meta: {str(rates)[:200]}"
    return rates


# ---------- health ----------
def test_health():
    r = requests.get(f"{API}/meta", timeout=60)
    assert r.status_code == 200, r.text[:200]


# ---------- FIX 2: admin vendor settlements totals are USD-converted ----------
def test_admin_vendor_settlement_totals_usd(admin, fx):
    r = admin.get(f"{API}/admin/vendor-settlements", timeout=90)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    t = d["totals"]
    assert t.get("currency") == "USD", f"totals currency={t.get('currency')}"
    rows = d["items"]
    assert rows, "no settlement rows to validate against"
    # recompute expected base-converted sums
    def to_base(a, c):
        return float(a or 0) / (fx.get((c or "USD").upper()) or 1.0)
    for status, key in (("pending", "due"), ("batched", "batched"), ("paid", "paid")):
        exp = round(sum(to_base(x["net"], x.get("currency")) for x in rows if x["status"] == status), 2)
        assert abs(t[key] - exp) < 0.05, f"{key}: api={t[key]} expected={exp}"
    exp_comm = round(sum(to_base(x.get("commission"), x.get("currency")) for x in rows), 2)
    assert abs(t["commission"] - exp_comm) < 0.05, f"commission api={t['commission']} exp={exp_comm}"
    # rows keep their own currency (historical INR preserved)
    assert any(x.get("currency") for x in rows), "rows have no currency field"


def test_admin_settlement_rows_have_currency_and_no_objectid(admin):
    r = admin.get(f"{API}/admin/vendor-settlements", timeout=90)
    assert r.status_code == 200
    for x in r.json()["items"][:20]:
        assert "_id" not in x, "raw mongo _id leaked"
        assert x.get("currency"), f"row {x.get('order_no')} missing currency"


# ---------- FIX 3: vendor settlements totals base-converted + agree with admin ----------
def test_vendor_settlements_totals_usd(partner, fx):
    r = partner.get(f"{API}/vendor/settlements", timeout=90)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    t = d["totals"]
    assert t.get("currency") == "USD", f"vendor totals currency={t.get('currency')}"
    rows = d["items"]

    def to_base(a, c):
        return float(a or 0) / (fx.get((c or "USD").upper()) or 1.0)
    exp_paid = round(sum(to_base(x["net"], x.get("currency")) for x in rows if x["status"] == "paid"), 2)
    exp_pend = round(sum(to_base(x["net"], x.get("currency")) for x in rows if x["status"] != "paid"), 2)
    assert abs(t["paid"] - exp_paid) < 0.05, f"paid api={t['paid']} exp={exp_paid}"
    assert abs(t["pending"] - exp_pend) < 0.05, f"pending api={t['pending']} exp={exp_pend}"
    assert all(x.get("currency") for x in rows), "vendor rows missing currency"


def test_admin_and_vendor_views_agree(admin, partner):
    a = admin.get(f"{API}/admin/vendor-settlements", timeout=90).json()
    v = partner.get(f"{API}/vendor/settlements", timeout=90).json()
    vid_rows = {x["id"]: x for x in v["items"]}
    a_rows = {x["id"]: x for x in a["items"] if x["id"] in vid_rows}
    assert a_rows, "no overlapping settlements between admin and vendor views"
    for rid, ar in a_rows.items():
        vr = vid_rows[rid]
        assert ar.get("currency") == vr.get("currency"), f"{rid} currency mismatch"
        assert abs(float(ar["net"]) - float(vr["net"])) < 0.01, f"{rid} net mismatch"
    # vendor paid total must equal the admin paid total restricted to this vendor
    vid = v["items"][0]["vendor_id"]
    av = admin.get(f"{API}/admin/vendor-settlements?vendor_id={vid}", timeout=90).json()
    assert abs(av["totals"]["paid"] - v["totals"]["paid"]) < 0.05, \
        f"admin paid {av['totals']['paid']} != vendor paid {v['totals']['paid']}"


# ---------- FIX 1: member orders carry currency + charge_total ----------
def test_member_orders_currency_fields(member):
    r = member.get(f"{API}/me/orders", timeout=90)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    assert items, "member has no orders to validate"
    for o in items[:30]:
        assert o.get("currency"), f"order {o.get('order_no')} has no currency"
        assert "total" in o, f"order {o.get('order_no')} missing total"
    inr = [o for o in items if (o.get("currency") or "").upper() == "INR"]
    if inr:
        o = inr[0]
        # historical INR order: charge_total (if present) must be in INR scale, not /83
        amt = o.get("charge_total") if o.get("charge_total") is not None else o.get("total")
        assert float(amt) > 0
        assert abs(float(amt) - float(o["total"])) < max(1.0, 0.02 * float(o["total"])), \
            f"INR order charge_total {amt} does not match total {o['total']} (double conversion?)"


# ---------- regression: door takings USD totals with per-row currency ----------
def test_door_takings_usd_totals(partner, fx):
    r = partner.get(f"{API}/partner/door-takings", timeout=90)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    tot = d.get("totals", d)
    assert (tot.get("currency") or d.get("currency")) == "USD", f"door totals currency {tot}"
    for row in (d.get("items") or [])[:20]:
        assert row.get("currency"), "door row missing currency"


# ---------- regression: checkout always charges USD ----------
@pytest.fixture(scope="module")
def an_event():
    r = requests.get(f"{API}/events?limit=20", timeout=60)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    paid = [e for e in items if float(e.get("price") or 0) > 0]
    assert paid or items, "no events available"
    return (paid or items)[0]


def test_checkout_forces_usd(member, an_event):
    created = []
    try:
        for disp in ("USD", "INR", "AED"):
            r = member.post(f"{API}/checkout",
                            json={"kind": "event", "item_id": an_event["id"], "currency": disp,
                                  "use_credit": False},
                            timeout=120)
            assert r.status_code in (200, 201), f"{disp}: {r.status_code} {r.text[:300]}"
            d = r.json()
            order = d.get("order") or d
            cur = order.get("currency") or d.get("currency")
            assert (cur or "").upper() == "USD", f"display {disp} produced charge currency {cur}"
            if order.get("id"):
                created.append(order["id"])
        assert len(created) >= 1
    finally:
        for oid_ in created:
            member.delete(f"{API}/me/orders/{oid_}", timeout=60)


# ---------- regression: membership refund needs override + reason ----------
def test_membership_refund_guard(admin):
    r = admin.post(f"{API}/admin/refunds", json={"order_id": "000000000000000000000000"}, timeout=60)
    assert r.status_code in (400, 403, 404, 422), f"unexpected {r.status_code} {r.text[:200]}"


# ---------- NEW FINDING (iteration 46): admin ledger + stats mix currencies ----------
def test_admin_ledger_totals_are_base_converted(admin, fx):
    """Rows carry their own currency but totals are labelled USD; INR rows must be converted."""
    # totals cover the whole result set, so every page must be pulled before comparing
    rows, page, d = [], 1, None
    while True:
        r = admin.get(f"{API}/admin/ledger?limit=200&page={page}", timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows += d["items"]
        if not d["items"] or len(rows) >= d["total"]:
            break
        page += 1
    assert d.get("currency") == "USD"

    def to_base(a, c):
        return float(a or 0) / (fx.get((c or "USD").upper()) or 1.0)
    money_in = [x for x in rows if x.get("direction") == "in"]
    exp = round(sum(to_base(x.get("gross"), x.get("currency")) for x in money_in), 2)
    raw = round(sum(float(x.get("gross") or 0) for x in money_in), 2)
    got = d["totals"]["collected"]
    assert abs(got - raw) > 0.01 or abs(got - exp) < 0.05, "unexpected shape"
    assert abs(got - exp) < max(1.0, 0.02 * exp), (
        f"collected={got} is a raw mixed-currency sum (raw={raw}); base-converted should be ~{exp}")


def test_admin_stats_money_has_currency(admin):
    r = admin.get(f"{API}/admin/stats", timeout=90)
    assert r.status_code == 200
    d = r.json()
    assert d.get("currency"), "no currency field on /admin/stats money figures (UI stamps $)"


# ---------- cleanup: checkout tests leave pending orders (no delete API) ----------
def test_zz_cleanup_pending_orders():
    import asyncio
    from dotenv import dotenv_values as _dv
    from motor.motor_asyncio import AsyncIOMotorClient
    env = _dv("/app/backend/.env")
    mongo = os.environ.get("MONGO_URL") or env["MONGO_URL"]
    dbname = os.environ.get("DB_NAME") or env["DB_NAME"]

    async def _clean():
        db = AsyncIOMotorClient(mongo)[dbname]
        u = await db.users.find_one({"email": "arjun.sethi@example.com"}, {"_id": 1})
        res = await db.orders.delete_many({"user_id": str(u["_id"]), "payment_status": "pending"})
        left = await db.orders.count_documents({"user_id": str(u["_id"]), "payment_status": "pending"})
        return res.deleted_count, left
    deleted, left = asyncio.run(_clean())
    print(f"cleanup: deleted {deleted} pending orders")
    assert left == 0
