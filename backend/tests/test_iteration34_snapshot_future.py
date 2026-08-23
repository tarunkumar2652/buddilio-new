"""Iteration 34 (part 2) — booking commercial snapshot, snapshot immutability across an
amendment (with a real OTP acceptance) and future-dated commercial terms.

Tests are ORDER DEPENDENT and share vendor state; pytest.ini pins a module to one xdist worker.
"""
import hashlib
import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("aarav.mehta@example.com", "User@12345")
OTHER = ("diya.sharma@example.com", "User@12345")

STATE = {}


def mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def client(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def vendor_ids():
    db = mongo()
    u = db.users.find_one({"email": PARTNER[0]}, {"_id": 1})
    v = db.vendor_profiles.find_one({"user_id": str(u["_id"])}, {"_id": 1})
    return str(v["_id"]), str(u["_id"])


def recover_code(agreement_id, version):
    db = mongo()
    otp = db.agreement_otps.find_one({"agreement_id": agreement_id, "version": version})
    assert otp, "no OTP row stored for the pending agreement"
    for n in range(100000, 1000000):
        if hashlib.sha256(str(n).encode()).hexdigest() == otp["code_hash"]:
            return str(n)
    pytest.fail("could not recover the OTP code")


def amend_and_accept(admin, partner, sched_body):
    """Amend the smoke vendor's terms and complete the vendor OTP acceptance."""
    vid, _ = vendor_ids()
    ags = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30).json()["items"]
    aid = [a for a in ags if a["vendor_id"] == vid][0]["id"]
    r = admin.post(f"{BASE}/admin/vendor-agreements/{aid}/amend", json=sched_body, timeout=60)
    assert r.status_code == 200, f"amend failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["changes"], "amendment recorded no change list"

    portal = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()
    ag = portal["agreement"]
    assert ag["status"] == "amendment_pending", ag["status"]
    otp = partner.post(f"{BASE}/vendor/agreement/otp", json={"channel": "email"}, timeout=45)
    assert otp.status_code == 200, otp.text[:300]
    code = recover_code(ag["id"], ag["version"])
    missing = partner.post(f"{BASE}/vendor/agreement/accept",
                           json={"read_agreement": True, "authorised": True, "accept_commercials": False,
                                 "consent_electronic": True, "otp": code, "accepted_by": "Signatory"},
                           timeout=30)
    assert missing.status_code == 400 and "four" in missing.json()["detail"].lower(), missing.text[:200]
    ok = partner.post(f"{BASE}/vendor/agreement/accept",
                      json={"read_agreement": True, "authorised": True, "accept_commercials": True,
                            "consent_electronic": True, "otp": code, "accepted_by": "Manish Kumar (Vendor)"},
                      timeout=90)
    assert ok.status_code == 200, f"accept failed: {ok.status_code} {ok.text[:300]}"
    assert ok.json()["document_hash"].startswith("sha256:")
    after = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()
    assert after["agreement"]["status"] == "active", after["agreement"]["status"]
    pdf = partner.get(f"{BASE}/vendor-agreements/{after['agreement']['id']}/pdf", timeout=60)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code
    return body


# ---------------- 1. booking commercial snapshot ----------------
def test_paid_event_booking_creates_snapshot_and_settlement():
    vid, _ = vendor_ids()
    member = client(*MEMBER)
    admin = client(*ADMIN)
    quote = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30).json()
    STATE["cycle"] = quote["settlement_cycle"]

    db = mongo()
    pu = db.users.find_one({"email": PARTNER[0]}, {"_id": 1})
    ev = db.events.find_one({"partner_id": str(pu["_id"]), "status": "published",
                             "price": {"$gt": 0}}, {"_id": 1, "title": 1})
    assert ev, "no priced published event owned by the smoke vendor"

    co = member.post(f"{BASE}/checkout", json={"kind": "event", "item_id": str(ev["_id"]), "quantity": 1},
                     timeout=45)
    assert co.status_code == 200, co.text[:300]
    order = co.json()["order"]
    STATE["order_id"] = order["id"]
    ver = member.post(f"{BASE}/payments/verify", json={"order_id": order["id"], "simulate": "success"},
                      timeout=60)
    assert ver.status_code == 200, ver.text[:300]
    assert ver.json()["order"]["payment_status"] == "paid"
    time.sleep(2)

    snap_res = member.get(f"{BASE}/bookings/{order['id']}/commercials", timeout=30)
    assert snap_res.status_code == 200, f"no snapshot: {snap_res.status_code} {snap_res.text[:300]}"
    snap = snap_res.json()["snapshot"]
    STATE["snapshot"] = snap
    assert snap["vendor_id"] == vid
    assert snap["agreement_id"] and snap["agreement_version"], snap
    assert snap["commercial_schedule_id"] and snap["commercial_schedule_version"], snap
    for k in ("currency", "vendor_net_rate", "pricing_floor", "commission", "platform_fee",
              "tax", "customer_price", "vendor_settlement", "buddilio_earning", "settlement_cycle"):
        assert k in snap, f"{k} missing from snapshot"
    assert snap["vendor_net_rate"] == quote["quote"]["vendor_net_rate"]
    assert snap["commission"] == quote["quote"]["commission"]
    assert snap["customer_price"] == quote["quote"]["customer_price"]
    assert round(snap["vendor_settlement"] + snap["buddilio_earning"], 2) == \
        round(snap["customer_price"] - snap["tax"], 2), snap

    row = db.vendor_settlements.find_one({"booking_id": order["id"]})
    assert row, "no vendor_settlements row created for the paid booking"
    assert row["vendor_id"] == vid and row["status"] == "pending"
    assert row["net"] == snap["vendor_settlement"]
    days = {"T+1": 1, "T+3": 3, "T+7": 7, "T+15": 15}[snap["settlement_cycle"]]
    from datetime import datetime, timedelta, timezone
    due = datetime.fromisoformat(row["due_on"])
    expected = datetime.now(timezone.utc) + timedelta(days=days)
    assert abs((due - expected).total_seconds()) < 600, f"due_on {row['due_on']} not {snap['settlement_cycle']}"

    mine = client(*PARTNER).get(f"{BASE}/vendor/settlements", timeout=30)
    assert mine.status_code == 200
    assert any(i["booking_id"] == order["id"] for i in mine.json()["items"]), \
        "settlement not visible in the vendor portal"


def test_other_member_cannot_read_snapshot():
    assert STATE.get("order_id"), "previous test did not create an order"
    r = client(*OTHER).get(f"{BASE}/bookings/{STATE['order_id']}/commercials", timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    anon = requests.get(f"{BASE}/bookings/{STATE['order_id']}/commercials", timeout=30)
    assert anon.status_code == 401, anon.status_code


# ---------------- 2. amendment (real OTP) leaves the snapshot untouched ----------------
def test_snapshot_immutable_after_amendment():
    assert STATE.get("snapshot"), "no snapshot from the earlier test"
    admin, partner = client(*ADMIN), client(*PARTNER)
    amend_and_accept(admin, partner, {
        "vendor_net_rate": 1750, "pricing_floor": 1700, "commission_type": "percentage",
        "commission_value": 25, "platform_fee_percent": 12, "tax_percent": 18,
        "settlement_cycle": "T+15", "change_reason": "TEST_i34 immutability check"})

    vid, _ = vendor_ids()
    q = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30).json()["quote"]
    assert q["vendor_net_rate"] == 1750 and q["commission"] == pytest.approx(1750 * 0.25), q

    again = client(*MEMBER).get(f"{BASE}/bookings/{STATE['order_id']}/commercials", timeout=30).json()["snapshot"]
    for k in ("vendor_net_rate", "commission", "platform_fee", "customer_price", "vendor_settlement",
              "commercial_schedule_version", "agreement_version"):
        assert again[k] == STATE["snapshot"][k], f"snapshot {k} changed after the amendment"


# ---------------- 3. future-dated terms must not apply early ----------------
def test_future_dated_schedule_not_used_until_effective():
    from datetime import datetime, timedelta, timezone
    admin, partner = client(*ADMIN), client(*PARTNER)
    vid, _ = vendor_ids()
    effective = datetime.now(timezone.utc) + timedelta(seconds=75)
    amend_and_accept(admin, partner, {
        "vendor_net_rate": 1900, "pricing_floor": 1800, "commission_type": "percentage",
        "commission_value": 30, "platform_fee_percent": 12, "tax_percent": 18,
        "settlement_cycle": "T+15", "effective_from": effective.isoformat(),
        "change_reason": "TEST_i34 future dated"})

    q = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30)
    assert q.status_code == 200, f"quote broke while terms are future-dated: {q.status_code} {q.text[:300]}"
    assert q.json()["quote"]["vendor_net_rate"] == 1750, \
        f"future-dated terms applied early: {q.json()['quote']}"

    # a booking made now must snapshot the currently effective (old) numbers
    db = mongo()
    pu = db.users.find_one({"email": PARTNER[0]}, {"_id": 1})
    ev = db.events.find_one({"partner_id": str(pu["_id"]), "status": "published", "price": {"$gt": 0}},
                            {"_id": 1})
    member = client(*MEMBER)
    co = member.post(f"{BASE}/checkout", json={"kind": "event", "item_id": str(ev["_id"]), "quantity": 1},
                     timeout=45).json()["order"]
    member.post(f"{BASE}/payments/verify", json={"order_id": co["id"], "simulate": "success"}, timeout=60)
    time.sleep(2)
    snap = member.get(f"{BASE}/bookings/{co['id']}/commercials", timeout=30)
    assert snap.status_code == 200, f"snapshot missing while terms are future-dated: {snap.text[:300]}"
    assert snap.json()["snapshot"]["vendor_net_rate"] == 1750, snap.json()["snapshot"]

    # once effective_from passes the new numbers take over
    wait = (effective - datetime.now(timezone.utc)).total_seconds() + 5
    if wait > 0:
        time.sleep(wait)
    q2 = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30)
    assert q2.status_code == 200, q2.text[:300]
    assert q2.json()["quote"]["vendor_net_rate"] == 1900, \
        f"new terms not applied after effective_from: {q2.json()['quote']}"
