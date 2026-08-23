"""Iteration 40 — payment retry, admin partial/full refunds, membership renewal reminders,
and the two new email templates.

SAFETY: PayPal is LIVE. Every refund here runs against a SIMULATED (gateway="stripe_sim")
paid order seeded directly in Mongo, so no real money moves and no PayPal API is hit.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
TIMEOUT = 60
CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]


def iso(dt):
    return dt.isoformat()


def now():
    return datetime.now(timezone.utc)


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
def member_tok():
    return token("arjun.sethi@example.com", "User@12345")


@pytest.fixture(scope="module")
def member(member_tok):
    return hdr(member_tok)


@pytest.fixture(scope="module")
def member_id(member):
    return requests.get(f"{API}/auth/me", headers=member, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def admin():
    return hdr(token("admin@buddilio.com", "Admin@123"))


@pytest.fixture(scope="module")
def product_id(db):
    p = db.products.find_one({"active": True}) or db.products.find_one({})
    assert p, "no product seeded"
    return str(p["_id"])


@pytest.fixture
def fresh_user(db):
    email = f"TEST_i40_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"full_name": "TEST_ Iter40 Tester", "email": email, "mobile": "9876500042",
               "password": "User@12345", "dob": "1990-05-05", "gender": "male", "city": "Mumbai",
               "is_adult": True, "accept_terms": True, "accept_privacy": True,
               "accept_guidelines": True}
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register failed {r.status_code} {r.text[:300]}"
    tok = r.json()["access_token"]
    uid = requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30).json()["id"]
    yield {"email": email, "headers": hdr(tok), "id": uid}
    db.user_memberships.delete_many({"user_id": uid})
    db.orders.delete_many({"user_id": uid})
    db.notifications.delete_many({"user_id": uid})
    db.users.delete_many({"email": email})


def make_order(headers, kind, item_id, currency="INR"):
    r = requests.post(f"{API}/checkout", headers=headers,
                      json={"kind": kind, "item_id": item_id, "quantity": 1,
                            "currency": currency, "use_credit": False}, timeout=TIMEOUT)
    assert r.status_code == 200, f"checkout failed {r.status_code} {r.text[:300]}"
    return r.json()["order"]


def seed_paid_order(db, uid, email, kind, ref_id, item_name, total=1000.0):
    """A simulated captured order — refundable without touching a real gateway."""
    doc = {"order_no": "TEST" + uuid.uuid4().hex[:8].upper(), "user_id": uid,
           "user_email": email, "user_name": "TEST_ Iter40 Tester", "kind": kind,
           "ref_id": ref_id, "item_name": item_name, "quantity": 1,
           "subtotal": total, "discount": 0.0, "tax": 0.0, "total": total,
           "tax_percent": 0.0, "tax_label": "No tax", "credit_applied": 0.0,
           "charge_credit": 0.0, "coupon": "", "currency": "INR", "fx_rate": 1.0,
           "base_currency": "INR", "charge_subtotal": total, "charge_discount": 0.0,
           "charge_tax": 0.0, "charge_total": total,
           "payment_status": "paid", "order_status": "completed", "refund_status": "none",
           "gateway": "stripe_sim", "transaction_id": "TEST_sim_" + uuid.uuid4().hex[:8],
           "created_at": iso(now()), "paid_at": iso(now())}
    return str(db.orders.insert_one(doc).inserted_id)


# ---------------- payment retry ----------------
class TestPaymentRetry:
    def test_retry_pending_order_resets_state(self, member, db, product_id):
        order = make_order(member, "product", product_id)
        oid = order["id"]
        db.orders.update_one({"_id": ObjectId(oid)},
                             {"$set": {"payment_status": "failed", "order_status": "failed",
                                       "failure_reason": "card declined",
                                       "gateway_order_id": "ord_stale"}})
        r = requests.post(f"{API}/me/orders/{oid}/retry", headers=member, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        o = r.json()["order"]
        assert o["payment_status"] == "pending"
        assert o["order_status"] == "created"
        assert o["failure_reason"] == ""
        assert o["gateway_order_id"] == ""
        assert o["retry_count"] == 1
        assert "_id" not in o
        # second retry increments again
        r2 = requests.post(f"{API}/me/orders/{oid}/retry", headers=member, timeout=TIMEOUT)
        assert r2.status_code == 200
        assert r2.json()["order"]["retry_count"] == 2
        # persisted
        fresh = db.orders.find_one({"_id": ObjectId(oid)})
        assert fresh["payment_status"] == "pending" and fresh["retry_count"] == 2
        db.orders.delete_one({"_id": ObjectId(oid)})

    def test_retry_requires_auth(self, member, db, product_id):
        order = make_order(member, "product", product_id)
        r = requests.post(f"{API}/me/orders/{order['id']}/retry", timeout=TIMEOUT)
        assert r.status_code in (401, 403), r.status_code
        db.orders.delete_one({"_id": ObjectId(order["id"])})

    def test_retry_other_members_order_404(self, member, fresh_user, db, product_id):
        order = make_order(member, "product", product_id)
        r = requests.post(f"{API}/me/orders/{order['id']}/retry",
                          headers=fresh_user["headers"], timeout=TIMEOUT)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"
        db.orders.delete_one({"_id": ObjectId(order["id"])})

    def test_retry_unknown_id_404(self, member):
        r = requests.post(f"{API}/me/orders/{ObjectId()}/retry", headers=member, timeout=TIMEOUT)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_retry_malformed_id_400(self, member):
        r = requests.post(f"{API}/me/orders/not-an-id/retry", headers=member, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_retry_paid_order_400(self, member, member_id, db):
        oid = seed_paid_order(db, member_id, "arjun.sethi@example.com", "product",
                              str(ObjectId()), "TEST_ Retry Paid")
        r = requests.post(f"{API}/me/orders/{oid}/retry", headers=member, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert "already paid" in r.json()["detail"].lower()
        db.orders.delete_one({"_id": ObjectId(oid)})


# ---------------- admin refunds (simulated gateway only) ----------------
class TestAdminRefund:
    def test_refund_unpaid_order_400(self, admin, member, db, product_id):
        order = make_order(member, "product", product_id)
        r = requests.post(f"{API}/admin/orders/{order['id']}/refund", headers=admin,
                          json={"amount": 10, "reason": "TEST"}, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert "paid" in r.json()["detail"].lower()
        db.orders.delete_one({"_id": ObjectId(order["id"])})

    def test_refund_requires_finance_manage(self, member, fresh_user, db):
        oid = seed_paid_order(db, fresh_user["id"], fresh_user["email"], "product",
                              str(ObjectId()), "TEST_ RBAC Order")
        anon = requests.post(f"{API}/admin/orders/{oid}/refund", json={"amount": 10}, timeout=TIMEOUT)
        assert anon.status_code in (401, 403), anon.status_code
        as_member = requests.post(f"{API}/admin/orders/{oid}/refund", headers=member,
                                  json={"amount": 10}, timeout=TIMEOUT)
        assert as_member.status_code == 403, f"{as_member.status_code} {as_member.text[:200]}"
        db.orders.delete_one({"_id": ObjectId(oid)})

    def test_amount_validation(self, admin, fresh_user, db):
        oid = seed_paid_order(db, fresh_user["id"], fresh_user["email"], "product",
                              str(ObjectId()), "TEST_ Validation Order", total=500.0)
        for bad in (-5, 501, 10000):
            r = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                              json={"amount": bad, "reason": "TEST"}, timeout=TIMEOUT)
            assert r.status_code == 400, f"amount {bad} accepted: {r.status_code} {r.text[:200]}"
        assert db.orders.find_one({"_id": ObjectId(oid)})["refund_status"] == "none"
        db.orders.delete_one({"_id": ObjectId(oid)})

    def test_cent_over_refund_rejected(self, admin, fresh_user, db):
        """Known bug: the +0.01 tolerance lets an admin refund a cent more than was charged."""
        oid = seed_paid_order(db, fresh_user["id"], fresh_user["email"], "product",
                              str(ObjectId()), "TEST_ Cent Order", total=500.0)
        r = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                          json={"amount": 500.01, "reason": "TEST cent"}, timeout=TIMEOUT)
        db.orders.delete_one({"_id": ObjectId(oid)})
        assert r.status_code == 400, f"over-refund accepted: {r.status_code} {r.text[:200]}"

    def test_partial_then_full_refund_membership(self, admin, fresh_user, db):
        plan = db.membership_plans.find_one({}) or {}
        oid = seed_paid_order(db, fresh_user["id"], fresh_user["email"], "membership",
                             str(plan.get("_id", ObjectId())), "TEST_ Membership Order", total=1000.0)
        db.user_memberships.insert_one({
            "user_id": fresh_user["id"], "plan_id": str(plan.get("_id", ObjectId())),
            "plan_name": "TEST_ Plan", "order_id": oid, "status": "active",
            "starts_at": iso(now()), "ends_at": iso(now() + timedelta(days=30)),
            "auto_renews": False})

        # (c) partial
        r = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                          json={"amount": 400, "reason": "TEST partial"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["refund_status"] == "partial"
        assert d["refunded_amount"] == 400.0
        doc = db.orders.find_one({"_id": ObjectId(oid)})
        assert doc["refund_status"] == "partial" and doc["refunded_amount"] == 400.0
        assert doc["order_status"] == "completed", "partial refund must not close the order"
        assert db.user_memberships.find_one({"order_id": oid})["status"] == "active"

        # remaining refundable is now 600 → 601 must fail
        over = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                             json={"amount": 601, "reason": "TEST over"}, timeout=TIMEOUT)
        assert over.status_code == 400, f"{over.status_code} {over.text[:200]}"

        # (d) top up to full
        r2 = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                           json={"amount": 600, "reason": "TEST rest"}, timeout=TIMEOUT)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json()["refund_status"] == "refunded"
        assert r2.json()["refunded_amount"] == 1000.0
        doc = db.orders.find_one({"_id": ObjectId(oid)})
        assert doc["refund_status"] == "refunded" and doc["order_status"] == "refunded"
        assert db.user_memberships.find_one({"order_id": oid})["status"] == "cancelled"

        # (e) further attempt
        r3 = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                           json={"amount": 10, "reason": "TEST again"}, timeout=TIMEOUT)
        assert r3.status_code == 400
        assert "already been refunded" in r3.json()["detail"].lower()

        # (g) member notification
        nres = requests.get(f"{API}/notifications", headers=fresh_user["headers"], timeout=TIMEOUT)
        assert nres.status_code == 200, f"notifications {nres.status_code} {nres.text[:200]}"
        items = nres.json()["items"]
        assert any("refund" in (n.get("title", "") + n.get("body", "")).lower() for n in items), items

        # admin list surfaces refunded amount
        lst = requests.get(f"{API}/admin/orders", headers=admin, timeout=TIMEOUT).json()["items"]
        row = next((o for o in lst if o["id"] == oid), None)
        assert row, "refunded order missing from admin list"
        assert row.get("refunded_amount") == 1000.0, row
        db.user_memberships.delete_many({"order_id": oid})
        db.orders.delete_one({"_id": ObjectId(oid)})

    def test_full_refund_removes_event_participant(self, admin, fresh_user, db):
        ev = db.events.find_one({"status": "published"}) or db.events.find_one({})
        assert ev, "no event seeded"
        eid = str(ev["_id"])
        oid = seed_paid_order(db, fresh_user["id"], fresh_user["email"], "event", eid,
                             "TEST_ Event Order", total=800.0)
        db.event_participants.insert_one({"event_id": eid, "user_id": fresh_user["id"],
                                         "order_id": oid, "status": "confirmed",
                                         "created_at": iso(now())})
        r = requests.post(f"{API}/admin/orders/{oid}/refund", headers=admin,
                          json={"amount": 0, "reason": "TEST full"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["refund_status"] == "refunded"
        assert r.json()["amount"] == 800.0, "empty amount must default to the full remainder"
        assert db.event_participants.find_one({"order_id": oid}) is None, "participant not removed"
        db.event_participants.delete_many({"order_id": oid})
        db.orders.delete_one({"_id": ObjectId(oid)})


# ---------------- renewal reminders ----------------
class TestRenewalReminders:
    def _seed(self, db, uid, auto_renews, days=7):
        return str(db.user_memberships.insert_one({
            "user_id": uid, "plan_id": str(ObjectId()), "plan_name": "TEST_ Premium Monthly",
            "order_id": "TEST_i40_renewal", "status": "active",
            "starts_at": iso(now() - timedelta(days=23)),
            "ends_at": iso(now() + timedelta(days=days)),
            "auto_renews": auto_renews}).inserted_id)

    def test_cron_requires_secret(self):
        r = requests.post(f"{API}/cron/daily-maintenance", timeout=TIMEOUT)
        assert r.status_code in (401, 403), r.status_code
        r2 = requests.post(f"{API}/cron/daily-maintenance",
                           headers={"Authorization": "Bearer wrong"}, timeout=TIMEOUT)
        assert r2.status_code in (401, 403), r2.status_code

    def test_reminder_sent_once_and_skips_autorenew(self, member, member_id, db):
        # The seeded member is used (not a TEST_ user) so a parallel worker's session-level
        # purge cannot delete the account mid-test.
        card_id = self._seed(db, member_id, False)
        auto_id = self._seed(db, member_id, True)
        try:
            r = requests.post(f"{API}/cron/daily-maintenance",
                              headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=TIMEOUT)
            assert r.status_code == 200, r.text[:300]
            assert "membership-renewal-reminders" in r.json()["queued"]
            import time
            time.sleep(6)

            card = db.user_memberships.find_one({"_id": ObjectId(card_id)})
            assert card.get("renewal_reminded") is True, card
            assert card.get("renewal_reminded_at"), "no reminder timestamp"
            stamp = card["renewal_reminded_at"]

            auto = db.user_memberships.find_one({"_id": ObjectId(auto_id)})
            assert not auto.get("renewal_reminded"), "auto-renewing membership was reminded"

            nres = requests.get(f"{API}/notifications", headers=member, timeout=TIMEOUT)
            assert nres.status_code == 200, f"notifications {nres.status_code} {nres.text[:200]}"
            items = nres.json()["items"]
            assert any("membership ends in a week" in n.get("title", "").lower()
                       for n in items), items[:5]

            # idempotent second run
            r2 = requests.post(f"{API}/cron/daily-maintenance",
                               headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=TIMEOUT)
            assert r2.status_code == 200
            time.sleep(5)
            again = db.user_memberships.find_one({"_id": ObjectId(card_id)})
            assert again["renewal_reminded_at"] == stamp, "reminder was re-sent"
        finally:
            db.user_memberships.delete_many({"order_id": "TEST_i40_renewal"})
            db.notifications.delete_many({"user_id": member_id,
                                          "title": "Your membership ends in a week"})


# ---------------- email templates ----------------
class TestEmailTemplates:
    def test_new_templates_listed_with_vars(self, admin):
        r = requests.get(f"{API}/admin/email-templates", headers=admin, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        items = {t["key"]: t for t in r.json()["items"]}
        for key, need in (("order_refunded", {"amount", "item", "order_no"}),
                          ("membership_expiring", {"plan_name", "ends_on", "days"})):
            assert key in items, f"{key} missing from templates"
            t = items[key]
            assert need.issubset(set(t["vars"])), t["vars"]
            assert t["subject"] and t["body"] and t["group"] == "Payments"

    def test_template_can_be_saved_and_reset(self, admin):
        cur = requests.get(f"{API}/admin/email-templates", headers=admin, timeout=TIMEOUT).json()
        base = next(t for t in cur["items"] if t["key"] == "membership_expiring")
        payload = {k: base[k] for k in ("subject", "title", "body", "cta_label", "cta_url")}
        payload["subject"] = "TEST_ expiring in {{days}} days"
        up = requests.put(f"{API}/admin/email-templates/membership_expiring", headers=admin,
                          json=payload, timeout=TIMEOUT)
        assert up.status_code == 200, up.text[:300]
        after = requests.get(f"{API}/admin/email-templates", headers=admin, timeout=TIMEOUT).json()
        saved = next(t for t in after["items"] if t["key"] == "membership_expiring")
        assert saved["subject"] == "TEST_ expiring in {{days}} days"
        assert saved["customised"] is True
        rs = requests.delete(f"{API}/admin/email-templates/membership_expiring", headers=admin,
                             timeout=TIMEOUT)
        assert rs.status_code == 200
        back = requests.get(f"{API}/admin/email-templates", headers=admin, timeout=TIMEOUT).json()
        reset = next(t for t in back["items"] if t["key"] == "membership_expiring")
        assert reset["customised"] is False
        assert reset["subject"] == cur["defaults"]["membership_expiring"]["subject"]
