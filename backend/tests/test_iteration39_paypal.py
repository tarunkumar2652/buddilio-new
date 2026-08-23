"""Iteration 39 — PayPal integration: config, one-time orders, capture guards, webhooks,
membership subscriptions (product/plan reuse), activation guards and membership cancel.

Real PayPal SANDBOX calls are made. To keep sandbox artefacts low we reuse the already-seeded
Basic (MONTH) and Premium Annual (YEAR) plans and create at most one new PayPal plan.
"""
import os
import uuid
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
def member():
    return hdr(token("arjun.sethi@example.com", "User@12345"))


@pytest.fixture(scope="module")
def admin():
    return hdr(token("admin@buddilio.com", "Admin@123"))


@pytest.fixture(scope="module")
def product_id(db):
    p = db.products.find_one({"active": True}) or db.products.find_one({})
    assert p, "no product seeded to buy"
    return str(p["_id"])


@pytest.fixture
def fresh_user(db):
    """A throwaway TEST_ member used for membership-cancel and cross-user 404 checks."""
    email = f"TEST_pp_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"full_name": "TEST_ PayPal Tester", "email": email, "mobile": "9876500011",
               "password": "User@12345", "dob": "1990-05-05", "gender": "male", "city": "Mumbai",
               "is_adult": True, "accept_terms": True, "accept_privacy": True,
               "accept_guidelines": True}
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register failed {r.status_code} {r.text[:300]}"
    tok = r.json()["access_token"]
    me = requests.get(f"{API}/auth/me", headers=hdr(tok), timeout=30).json()
    uid = me.get("id") or (me.get("user") or {}).get("id")
    assert uid, f"could not read user id: {me}"
    yield {"email": email, "headers": hdr(tok), "id": uid}
    db.user_memberships.delete_many({"user_id": uid})
    db.orders.delete_many({"user_id": uid})
    db.users.delete_many({"email": email})


def make_order(headers, kind, item_id, currency="INR"):
    r = requests.post(f"{API}/checkout", headers=headers,
                      json={"kind": kind, "item_id": item_id, "quantity": 1,
                            "currency": currency, "use_credit": False}, timeout=TIMEOUT)
    assert r.status_code == 200, f"checkout failed {r.status_code} {r.text[:300]}"
    return r.json()["order"] if "order" in r.json() else r.json()


# ---------------- config ----------------
class TestPayPalConfig:
    def test_paypal_config(self):
        r = requests.get(f"{API}/payments/paypal/config", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["enabled"] is True
        assert d["currency"] == "USD"
        assert d["env"] in ("sandbox", "live")

    def test_payments_config_includes_paypal(self):
        r = requests.get(f"{API}/payments/config", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("paypal_enabled") is True
        assert d.get("paypal_currency") == "USD"
        assert d.get("subscriptions_via") == "paypal"


# ---------------- one-time PayPal orders ----------------
class TestPayPalOneTimeOrder:
    def test_create_order_returns_approve_url(self, member, db, product_id):
        order = make_order(member, "product", product_id)
        oid = order["id"]
        r = requests.post(f"{API}/payments/paypal/order", headers=member,
                          json={"order_id": oid, "origin_url": BASE}, timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["paypal_order_id"] and isinstance(d["paypal_order_id"], str)
        assert ".paypal.com" in d["approve_url"], d["approve_url"]
        assert d["currency"] == "USD"
        assert float(d["amount"]) >= 1.0
        assert float(d["amount"]) < float(order["total"]), "USD amount should be less than INR total"
        doc = db.orders.find_one({"_id": ObjectId(oid)})
        assert doc["gateway"] == "paypal"
        assert doc["gateway_order_id"] == d["paypal_order_id"]
        assert doc["charge_currency_paypal"] == "USD"
        assert round(float(doc["charge_total_paypal"]), 2) == round(float(d["amount"]), 2)

    def test_requires_auth(self, member, product_id):
        order = make_order(member, "product", product_id)
        r = requests.post(f"{API}/payments/paypal/order",
                          json={"order_id": order["id"]}, timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_other_users_order_404(self, member, fresh_user, product_id):
        order = make_order(member, "product", product_id)
        r = requests.post(f"{API}/payments/paypal/order", headers=fresh_user["headers"],
                          json={"order_id": order["id"]}, timeout=TIMEOUT)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_already_paid_order_400(self, member, product_id):
        order = make_order(member, "product", product_id)
        pay = requests.post(f"{API}/payments/verify", headers=member,
                            json={"order_id": order["id"], "simulate": "success"}, timeout=TIMEOUT)
        assert pay.status_code == 200, f"simulated pay failed {pay.status_code} {pay.text[:300]}"
        assert pay.json()["status"] == "paid"
        r = requests.post(f"{API}/payments/paypal/order", headers=member,
                          json={"order_id": order["id"]}, timeout=TIMEOUT)
        assert r.status_code == 400
        assert "already paid" in r.json()["detail"].lower()


# ---------------- capture guards ----------------
class TestPayPalCapture:
    def test_capture_unapproved_order_fails_cleanly(self, member, db, product_id):
        order = make_order(member, "product", product_id)
        oid = order["id"]
        c = requests.post(f"{API}/payments/paypal/order", headers=member,
                          json={"order_id": oid, "origin_url": BASE}, timeout=TIMEOUT)
        assert c.status_code == 200, c.text[:300]
        r = requests.post(f"{API}/payments/paypal/capture", headers=member,
                          json={"order_id": oid}, timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:400]}"
        detail = r.json()["detail"]
        assert isinstance(detail, str) and detail.strip()
        assert "approve" in detail.lower() or "ORDER_NOT_APPROVED" in detail
        doc = db.orders.find_one({"_id": ObjectId(oid)})
        assert doc["payment_status"] == "failed"
        assert doc["order_status"] == "failed"
        assert db.payments.count_documents({"order_id": oid, "status": "failed"}) >= 1

    def test_capture_already_paid_returns_already(self, member, product_id):
        order = make_order(member, "product", product_id)
        pay = requests.post(f"{API}/payments/verify", headers=member,
                            json={"order_id": order["id"], "simulate": "success"}, timeout=TIMEOUT)
        assert pay.status_code == 200, pay.text[:200]
        oid = order["id"]
        r = requests.post(f"{API}/payments/paypal/capture", headers=member,
                          json={"order_id": oid}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("already") is True
        assert d["order"]["payment_status"] == "paid"
        assert "_id" not in d["order"]


# ---------------- webhook fulfilment ----------------
class TestPayPalWebhookOrder:
    def test_capture_completed_webhook_fulfils_and_is_idempotent(self, member, db, product_id):
        order = make_order(member, "product", product_id)
        oid = order["id"]
        body = {"event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"id": "CAP-" + uuid.uuid4().hex[:12].upper(), "custom_id": oid,
                             "status": "COMPLETED",
                             "amount": {"currency_code": "USD", "value": "10.00"}}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        # Fail-closed: an unsigned webhook must never release an order.
        if r.json()["status"] != "ok":
            doc = db.orders.find_one({"_id": ObjectId(oid)})
            assert doc["payment_status"] != "paid", "unsigned webhook fulfilled an order"
            return
        doc = db.orders.find_one({"_id": ObjectId(oid)})
        assert doc["payment_status"] == "paid", f"webhook did not fulfil: {doc.get('payment_status')}"
        assert doc["gateway"] == "paypal"
        assert db.payments.count_documents({"order_id": oid, "status": "captured"}) == 1
        # invoice + ledger are derived views over orders/payments
        inv = requests.get(f"{API}/orders/{oid}/invoice", headers=member, timeout=TIMEOUT)
        assert inv.status_code == 200, f"invoice fetch failed {inv.status_code} {inv.text[:200]}"
        led = requests.get(f"{API}/me/ledger", headers=member, timeout=TIMEOUT)
        assert led.status_code == 200
        assert any(p["id"] == oid for p in led.json()["payments"]), "order missing from ledger"

        # replay -> idempotent
        r2 = requests.post(f"{BASE}/api/webhook/paypal", json=body, timeout=TIMEOUT)
        assert r2.status_code == 200
        assert db.payments.count_documents({"order_id": oid, "status": "captured"}) == 1, \
            "replayed webhook double-charged"

    def test_unknown_custom_id_is_ignored(self):
        body = {"event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"id": "CAP-X", "custom_id": "not-an-objectid"}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=body, timeout=TIMEOUT)
        assert r.status_code == 200


# ---------------- subscriptions ----------------
@pytest.fixture(scope="module")
def plans(db):
    # prefer a monthly plan that has no PayPal plan yet so we exercise first-time creation
    monthly = (db.membership_plans.find_one({"duration_days": {"$lt": 300}, "active": True,
                                             "paypal": {"$exists": False}})
               or db.membership_plans.find_one({"duration_days": {"$lt": 300}, "active": True}))
    annual = db.membership_plans.find_one({"duration_days": {"$gte": 300}, "active": True})
    assert monthly and annual
    return {"month": monthly, "year": annual, "month_had_paypal": bool(monthly.get("paypal"))}


@pytest.fixture(scope="module")
def pending_sub(member, db, plans):
    """A PayPal subscription in APPROVAL_PENDING. Reuses one from the DB to limit sandbox churn."""
    # Only reuse a subscription created against the CURRENT PayPal environment.
    env_plan = (db.membership_plans.find_one({"paypal.env": os.environ.get("PAYPAL_ENV", "sandbox")})
                or {})
    existing = db.paypal_subscriptions.find_one(
        {"status": "APPROVAL_PENDING", "paypal_plan_id": (env_plan.get("paypal") or {}).get("plan_id", "")},
        sort=[("created_at", -1)]) if env_plan else None
    if existing:
        return existing["subscription_id"]
    r = requests.post(f"{API}/payments/paypal/subscription", headers=member,
                      json={"plan_id": str(plans["month"]["_id"]), "origin_url": BASE}, timeout=TIMEOUT)
    assert r.status_code == 200, f"could not create subscription {r.status_code} {r.text[:300]}"
    return r.json()["subscription_id"]


class TestPayPalSubscription:
    def test_month_plan_creates_or_reuses_plan(self, member, db, plans):
        pid = str(plans["month"]["_id"])
        r = requests.post(f"{API}/payments/paypal/subscription", headers=member,
                          json={"plan_id": pid, "origin_url": BASE}, timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["subscription_id"].startswith("I-"), d
        assert ".paypal.com" in d["approve_url"], d["approve_url"]
        pp = db.membership_plans.find_one({"_id": plans["month"]["_id"]})["paypal"]
        assert pp["interval"] == "MONTH", pp
        assert pp["interval_count"] == 1, pp
        assert pp["product_id"] and pp["plan_id"]
        assert float(pp["price"]) > 0
        sub = db.paypal_subscriptions.find_one({"subscription_id": d["subscription_id"]})
        assert sub, "paypal_subscriptions row not stored"
        assert sub["status"] == "APPROVAL_PENDING"
        assert sub["plan_id"] == pid
        assert sub["paypal_plan_id"] == pp["plan_id"]
        self.__class__.plan_id_month = pp["plan_id"]

    def test_second_call_reuses_paypal_plan(self, member, db, plans):
        pid = str(plans["month"]["_id"])
        r = requests.post(f"{API}/payments/paypal/subscription", headers=member,
                          json={"plan_id": pid, "origin_url": BASE}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        pp = db.membership_plans.find_one({"_id": plans["month"]["_id"]})["paypal"]
        assert pp["plan_id"] == self.__class__.plan_id_month, "a new PayPal plan was created on reuse"
        sub = db.paypal_subscriptions.find_one({"subscription_id": r.json()["subscription_id"]})
        assert sub["paypal_plan_id"] == self.__class__.plan_id_month

    def test_annual_plan_maps_to_year_interval(self, member, db, plans):
        pid = str(plans["year"]["_id"])
        r = requests.post(f"{API}/payments/paypal/subscription", headers=member,
                          json={"plan_id": pid, "origin_url": BASE}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:400]
        pp = db.membership_plans.find_one({"_id": plans["year"]["_id"]})["paypal"]
        assert pp["interval"] == "YEAR", pp
        assert pp["interval_count"] == 1

    def test_subscription_requires_auth(self, plans):
        r = requests.post(f"{API}/payments/paypal/subscription",
                          json={"plan_id": str(plans["month"]["_id"])}, timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_unknown_plan_404(self, member):
        r = requests.post(f"{API}/payments/paypal/subscription", headers=member,
                          json={"plan_id": str(ObjectId())}, timeout=TIMEOUT)
        assert r.status_code == 404, r.text[:200]


class TestSubscriptionActivation:
    def test_pending_subscription_does_not_create_membership(self, member, db, pending_sub):
        sid = pending_sub
        r = requests.post(f"{API}/payments/paypal/subscription/activate", headers=member,
                          json={"subscription_id": sid}, timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["status"] in ("APPROVAL_PENDING", "CREATED"), d
        assert d["membership"] is None
        assert db.user_memberships.count_documents({"paypal_subscription_id": sid}) == 0

    def test_unknown_subscription_404(self, member):
        r = requests.post(f"{API}/payments/paypal/subscription/activate", headers=member,
                          json={"subscription_id": "I-DOESNOTEXIST0000"}, timeout=TIMEOUT)
        assert r.status_code == 404, r.text[:200]

    def test_other_users_subscription_404(self, fresh_user, pending_sub):
        r = requests.post(f"{API}/payments/paypal/subscription/activate",
                          headers=fresh_user["headers"],
                          json={"subscription_id": pending_sub}, timeout=TIMEOUT)
        assert r.status_code == 404, r.text[:200]

    def test_activated_webhook_does_not_falsely_create_membership(self, db, pending_sub):
        body = {"event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                "resource": {"id": pending_sub, "status": "ACTIVE"}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert db.user_memberships.count_documents({"paypal_subscription_id": pending_sub}) == 0

    def test_cancelled_webhook_marks_status(self, db, pending_sub):
        body = {"event_type": "BILLING.SUBSCRIPTION.CANCELLED", "resource": {"id": pending_sub}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=body, timeout=TIMEOUT)
        assert r.status_code == 200
        sub = db.paypal_subscriptions.find_one({"subscription_id": pending_sub})
        if r.json()["status"] == "ok":
            assert sub["status"] == "CANCELLED", sub.get("status")
        else:
            # Fail-closed without PAYPAL_WEBHOOK_ID — an unsigned event must change nothing.
            assert sub["status"] != "CANCELLED"


# ---------------- membership cancel ----------------
class TestMembershipCancel:
    def test_cancel_without_membership_400(self, fresh_user):
        r = requests.post(f"{API}/me/membership/cancel", headers=fresh_user["headers"], timeout=TIMEOUT)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        assert "active membership" in r.json()["detail"].lower()

    def test_cancel_requires_auth(self):
        r = requests.post(f"{API}/me/membership/cancel", timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_cancel_active_membership_turns_off_autorenew(self, fresh_user, db, plans):
        mid = db.user_memberships.insert_one({
            "user_id": fresh_user["id"], "plan_id": str(plans["month"]["_id"]),
            "plan_name": plans["month"]["name"], "status": "active",
            "starts_at": "2026-01-01T00:00:00+00:00", "ends_at": "2099-01-01T00:00:00+00:00",
            "order_id": "TEST_pp_order", "auto_renews": True,
            "created_at": "2026-01-01T00:00:00+00:00"}).inserted_id
        r = requests.post(f"{API}/me/membership/cancel", headers=fresh_user["headers"], timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["ok"] is True
        assert "benefits" in d["message"].lower() and "paid period" in d["message"].lower()
        doc = db.user_memberships.find_one({"_id": mid})
        assert doc["auto_renews"] is False
        assert doc.get("cancelled_at")
        db.user_memberships.delete_one({"_id": mid})


# ---------------- input validation (currently failing — raw dict bodies, no Pydantic) ----------------
class TestPayPalInputValidation:
    """These endpoints accept a raw `dict` body and index it directly, so malformed payloads
    surface as 500s instead of 400/422."""

    @pytest.mark.parametrize("path,body", [
        ("/payments/paypal/order", {}),
        ("/payments/paypal/order", {"order_id": "not-an-objectid"}),
        ("/payments/paypal/capture", {}),
        ("/payments/paypal/subscription", {}),
        ("/payments/paypal/subscription", {"plan_id": "not-an-objectid"}),
    ])
    def test_malformed_body_should_be_4xx(self, member, path, body):
        r = requests.post(f"{API}{path}", headers=member, json=body, timeout=TIMEOUT)
        assert 400 <= r.status_code < 500, f"{path} {body} -> {r.status_code} {r.text[:150]}"
