"""Iteration 42 — PayPal webhook self-service admin card, organiser door check-in, pass reminders,
plus a regression pass over the iteration-41 refund/cancellation policy fixes."""
import os
import subprocess
import time

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
CRON = be["WEBHOOK_CRON_SECRET"]
db = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")
SEED = "/app/backend/tests/i42_seed.py"


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds[0]}: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def client(creds):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {login(creds)}"})
    return s


@pytest.fixture(scope="session")
def seed():
    out = subprocess.run(["python", SEED], capture_output=True, text=True, check=True).stdout
    data = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line and
                line.split("=", 1)[0].isupper())
    yield data
    subprocess.run(["python", SEED, "--clean"], capture_output=True, text=True, check=False)


@pytest.fixture(scope="session")
def admin():
    return client(ADMIN)


@pytest.fixture(scope="session")
def partner():
    return client(PARTNER)


@pytest.fixture(scope="session")
def member():
    return client(MEMBER)


# ---------------- PayPal webhook admin card ----------------
class TestPaypalWebhookStatus:
    def test_status_as_admin(self, admin):
        r = admin.get(f"{API}/admin/paypal/webhook", timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        for key in ("env", "url", "webhook_id", "events", "registered", "matches"):
            assert key in d, f"missing {key} in {d}"
        assert d["url"].endswith("/api/webhook/paypal")
        assert isinstance(d["events"], list) and d["events"]
        assert isinstance(d["registered"], list)
        assert isinstance(d["matches"], bool)
        blob = r.text.lower()
        for secret in ("client_secret", "paypal_client_secret", "access_token"):
            assert secret not in blob, f"secret-ish key leaked: {secret}"
        for env_key in ("PAYPAL_CLIENT_SECRET", "PAYPAL_SANDBOX_CLIENT_SECRET"):
            val = be.get(env_key)
            if val:
                assert val not in r.text, f"{env_key} value leaked"
        print("webhook status:", {k: d[k] for k in ("env", "url", "webhook_id", "matches", "error")},
              "registered:", len(d["registered"]))

    def test_status_forbidden_for_member(self, member):
        assert member.get(f"{API}/admin/paypal/webhook", timeout=30).status_code == 403

    def test_status_requires_auth(self):
        assert requests.get(f"{API}/admin/paypal/webhook", timeout=30).status_code in (401, 403)

    # LIVE PayPal: only permissions are checked, the setup itself is never executed as admin.
    def test_setup_forbidden_for_member(self, member):
        assert member.post(f"{API}/admin/paypal/webhook/setup", timeout=30).status_code == 403

    def test_setup_forbidden_for_partner(self, partner):
        assert partner.post(f"{API}/admin/paypal/webhook/setup", timeout=30).status_code == 403

    def test_setup_requires_auth(self):
        assert requests.post(f"{API}/admin/paypal/webhook/setup", timeout=30).status_code in (401, 403)


class TestPaypalWebhookFailsClosed:
    def test_forged_event_is_unverified_and_fulfils_nothing(self, seed):
        oid = seed["ORDER_ID"]
        forged = {"id": "WH-FORGED-1", "event_type": "PAYMENT.CAPTURE.COMPLETED",
                  "resource": {"id": "FORGEDCAPTURE1", "custom_id": oid, "status": "COMPLETED"}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=forged, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("status") == "unverified", r.text[:300]

    def test_forged_subscription_activation_does_nothing(self):
        before = db.paypal_subscriptions.count_documents({"subscription_id": "I-FORGED42"})
        forged = {"event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                  "resource": {"id": "I-FORGED42", "status": "ACTIVE"}}
        r = requests.post(f"{BASE}/api/webhook/paypal", json=forged, timeout=30)
        assert r.json().get("status") == "unverified"
        assert db.paypal_subscriptions.count_documents({"subscription_id": "I-FORGED42"}) == before


# ---------------- organiser door check-in ----------------
class TestDoorCheckIn:
    def test_own_event_list(self, partner, seed):
        r = partner.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["event"]["id"] == seed["EVENT_ID"]
        assert isinstance(d["items"], list) and d["items"]
        assert all("_id" not in i for i in d["items"]), "mongo _id leaked in door list"
        codes = {i["code"] for i in d["items"]}
        assert seed["DOOR_CODE"] in codes
        assert d["guests"] >= 4 and d["arrived"] >= 0

    def test_other_partner_event_forbidden(self, partner, seed):
        r = partner.get(f"{API}/partner/events/{seed['OTHER_EVENT_ID']}/check-in", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_member_forbidden(self, member, seed):
        r = member.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_unauthenticated_rejected(self, seed):
        r = requests.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30)
        assert r.status_code in (401, 403)

    def test_admin_can_view(self, admin, seed):
        r = admin.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_redeem_then_counts_move(self, partner, seed):
        code = seed["DOOR_CODE"]
        before = partner.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30).json()
        r = partner.post(f"{API}/passes/{code}/redeem", timeout=30)
        assert r.status_code == 200, r.text[:300]
        p = r.json()["pass"]
        assert p["status"] == "redeemed" and p["code"] == code
        assert p.get("redeemed_at")
        after = partner.get(f"{API}/partner/events/{seed['EVENT_ID']}/check-in", timeout=30).json()
        assert after["arrived"] == before["arrived"] + 2, (before["arrived"], after["arrived"])

    def test_second_redeem_rejected_already_used(self, partner, seed):
        r = partner.post(f"{API}/passes/{seed['DOOR_CODE']}/redeem", timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "already used" in r.json()["detail"].lower(), r.text[:300]

    def test_unknown_code_404(self, partner):
        r = partner.post(f"{API}/passes/BUD-ZZZZ-00/redeem", timeout=30)
        assert r.status_code == 404
        assert "couldn't find" in r.json()["detail"].lower()


# ---------------- pass reminder (day-before voucher email) ----------------
class TestPassReminder:
    def test_template_present_in_admin_emails(self, admin):
        r = admin.get(f"{API}/admin/email-templates", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
        tpl = next((t for t in items if t.get("key") == "pass_reminder"), None)
        assert tpl, f"pass_reminder template missing; keys={[t.get('key') for t in items][:40]}"
        assert set(tpl["vars"]) >= {"first_name", "item", "code", "when", "where", "qr_url", "pass_url"}

    def test_cron_queues_pass_reminders_and_marks_once(self, seed):
        code = seed["REMIND_CODE"]
        assert db.passes.find_one({"code": code}).get("reminded") is None
        r = requests.post(f"{API}/cron/daily-maintenance",
                          headers={"Authorization": f"Bearer {CRON}"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "pass-reminders" in r.json()["queued"]
        doc = None
        for _ in range(20):
            time.sleep(1.5)
            doc = db.passes.find_one({"code": code})
            if doc.get("reminded"):
                break
        assert doc.get("reminded") is True, "pass was not marked reminded after cron"
        first_at = doc.get("reminded_at")
        assert first_at

        # second run must not re-send
        r2 = requests.post(f"{API}/cron/daily-maintenance",
                           headers={"Authorization": f"Bearer {CRON}"}, timeout=60)
        assert r2.status_code == 200
        time.sleep(6)
        again = db.passes.find_one({"code": code})
        assert again.get("reminded_at") == first_at, "reminder re-sent on second cron run"

    def test_cron_requires_secret(self):
        assert requests.post(f"{API}/cron/daily-maintenance", timeout=30).status_code in (401, 403)
        assert requests.post(f"{API}/cron/daily-maintenance",
                             headers={"Authorization": "Bearer nope"},
                             timeout=30).status_code in (401, 403)


# ---------------- regression: iteration-41 refund / cancellation policy ----------------
class TestRefundPolicyRegression:
    def test_membership_refund_blocked_without_override(self, admin):
        m = db.orders.find_one({"kind": "membership", "payment_status": "paid",
                                "refund_status": {"$in": [None, "none"]}})
        assert m, "no paid membership order available to test"
        r = admin.post(f"{API}/admin/orders/{m['_id']}/refund",
                       json={"amount": 1.0, "reason": ""}, timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "non-refundable" in r.json()["detail"].lower(), r.text[:300]
        assert db.orders.find_one({"_id": m["_id"]}).get("refund_status") in (None, "none")

    def test_membership_refund_blocked_when_override_has_no_reason(self, admin):
        m = db.orders.find_one({"kind": "membership", "payment_status": "paid",
                                "refund_status": {"$in": [None, "none"]}})
        r = admin.post(f"{API}/admin/orders/{m['_id']}/refund",
                       json={"amount": 1.0, "reason": "  ", "override_policy": True}, timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "reason is required" in r.json()["detail"].lower(), r.text[:300]
        assert db.orders.find_one({"_id": m["_id"]}).get("refund_status") in (None, "none")

    def test_refund_above_cancellation_quote_blocked(self, admin, seed):
        oid = seed["ORDER_ID"]
        r = admin.post(f"{API}/admin/orders/{oid}/refund", json={"amount": 100.0}, timeout=30)
        assert r.status_code == 400, r.text[:300]
        detail = r.json()["detail"].lower()
        assert "30" in detail and "override" in detail, r.text[:300]
        assert db.orders.find_one({"_id": __import__("bson").ObjectId(oid)}).get("refund_status") == "none"

    def test_refund_over_order_total_blocked(self, admin, seed):
        r = admin.post(f"{API}/admin/orders/{seed['ORDER_ID']}/refund",
                       json={"amount": 5000.0, "override_policy": True, "reason": "test"}, timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "between 0 and" in r.json()["detail"].lower()

    def test_refund_requires_finance_permission(self, member, seed):
        r = member.post(f"{API}/admin/orders/{seed['ORDER_ID']}/refund", json={"amount": 1.0}, timeout=30)
        assert r.status_code == 403


class TestCancellationsScreen:
    def test_admin_cancellations_lists_pending(self, admin, seed):
        r = admin.get(f"{API}/admin/cancellations", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d["items"], list) and d.get("tiers")
        assert all("_id" not in i for i in d["items"]), "mongo _id leaked"
        assert any(i["id"] == seed["ORDER_ID"] for i in d["items"]), "seeded cancellation not listed"

    def test_cancellations_forbidden_for_member(self, member):
        assert member.get(f"{API}/admin/cancellations", timeout=30).status_code == 403

    def test_settle_validates_amount(self, admin, seed):
        r = admin.post(f"{API}/admin/orders/{seed['ORDER_ID']}/settle-cancellation",
                       json={"amount": 99999.0}, timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "between 0 and" in r.json()["detail"].lower()

    def test_member_cancellation_quote_shape(self, member):
        orders = member.get(f"{API}/me/orders", timeout=30)
        assert orders.status_code == 200, orders.text[:200]
        items = orders.json().get("items", [])
        target = next((o for o in items if o.get("payment_status") == "paid"
                       and o.get("refund_status", "none") == "none"), None)
        if not target:
            pytest.skip("member has no paid, un-refunded order to quote")
        q = member.get(f"{API}/me/orders/{target['id']}/cancellation-quote", timeout=30)
        assert q.status_code == 200, q.text[:300]
        d = q.json()
        for key in ("paid", "deduction_percent", "refundable", "cancellable"):
            assert key in d, f"missing {key}"
        assert d["refundable"] <= d["paid"] + 0.01
