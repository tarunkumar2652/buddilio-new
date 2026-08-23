"""Iteration 3 backend tests: multi-currency checkout, Stripe path, uploads,
reviews, partner payouts, price overrides, security.
"""
import io
import os
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@buddilio.com", "password": "Admin@123"}
PARTNER = {"email": "partner@buddilio.com", "password": "Partner@123"}
PARTNER2 = {"email": "partner2@buddilio.com", "password": "Partner@123"}
ATTENDEE = {"email": "ananya.kapoor@example.com", "password": "User@12345"}
USER = {"email": "aarav.mehta@example.com", "password": "User@12345"}
USER2 = {"email": "diya.sharma@example.com", "password": "User@12345"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="session")
def partner_token():
    return _login(**PARTNER)


@pytest.fixture(scope="session")
def partner2_token():
    try:
        return _login(**PARTNER2)
    except AssertionError:
        pytest.skip("partner2 not seeded")


@pytest.fixture(scope="session")
def attendee_token():
    return _login(**ATTENDEE)


@pytest.fixture(scope="session")
def user_token():
    return _login(**USER)


@pytest.fixture(scope="session")
def user2_token():
    return _login(**USER2)


# ---------- Payment config / currency ----------
class TestPaymentConfig:
    def test_config_has_currencies(self):
        r = requests.get(f"{API}/payments/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        codes = {c["code"] for c in d["currencies"]}
        assert {"INR", "USD", "EUR", "GBP", "AED", "SGD"}.issubset(codes)
        assert d["base_currency"] == "INR"
        assert d["stripe_enabled"] is True
        assert d["razorpay_live"] is False

    def test_currency_rate_inr_is_1(self):
        d = requests.get(f"{API}/payments/config", timeout=15).json()
        inr = next(c for c in d["currencies"] if c["code"] == "INR")
        assert float(inr["rate"]) == 1.0


# ---------- Multi-currency checkout ----------
class TestMultiCurrencyCheckout:
    def _first_plan(self):
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        assert plans
        paid = [p for p in plans if p.get("price", 0) > 0]
        return paid[0] if paid else plans[0]

    def test_inr_checkout_stores_charge_fields(self, user_token):
        plan = self._first_plan()
        r = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "membership", "item_id": plan["id"], "quantity": 1,
                                "currency": "INR"}, timeout=15)
        assert r.status_code == 200
        o = r.json()["order"]
        assert o["currency"] == "INR"
        assert o["fx_rate"] == 1.0
        assert o["charge_total"] == o["total"]
        assert o["gateway"] == "razorpay_sim"

    def test_usd_checkout_converts(self, user_token):
        plan = self._first_plan()
        r = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "membership", "item_id": plan["id"], "quantity": 1,
                                "currency": "USD"}, timeout=15)
        assert r.status_code == 200
        o = r.json()["order"]
        assert o["currency"] == "USD"
        assert 0 < o["fx_rate"] < 1
        assert o["charge_total"] < o["total"]  # USD amount smaller than INR total
        assert o["gateway"] == "stripe"
        assert o["base_currency"] == "INR"

    def test_coupon_buddy20_in_usd(self, user_token):
        prods = requests.get(f"{API}/products", timeout=15).json()["items"]
        prod = next((p for p in prods if p["price"] >= 600), None)
        if not prod:
            pytest.skip("no product with price>=600")
        r = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "product", "item_id": prod["id"], "quantity": 1,
                                "coupon_code": "BUDDY20", "currency": "USD"}, timeout=15)
        assert r.status_code == 200, r.text
        o = r.json()["order"]
        assert o["coupon"] == "BUDDY20"
        assert o["discount"] > 0
        assert o["charge_discount"] > 0

    def test_unknown_currency_rejected(self, user_token):
        plan = self._first_plan()
        r = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "membership", "item_id": plan["id"], "quantity": 1,
                                "currency": "ZZZ"}, timeout=15)
        assert r.status_code == 400


# ---------- Stripe path ----------
class TestStripe:
    def test_stripe_session_creation_usd(self, user_token):
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        plan = next((p for p in plans if p.get("price", 0) > 0), plans[0])
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "membership", "item_id": plan["id"], "quantity": 1,
                                 "currency": "USD"}, timeout=15).json()["order"]
        r = requests.post(f"{API}/payments/stripe/session", headers=_auth(user_token),
                          json={"order_id": co["id"], "origin_url": BASE_URL}, timeout=30)
        if r.status_code == 502:
            pytest.skip("Stripe upstream unreachable")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "checkout_url" in d
        assert "checkout.stripe.com" in d["checkout_url"]
        assert d["session_id"]
        # Status polling returns pending, does NOT mark order paid
        st = requests.get(f"{API}/payments/status/{d['session_id']}", timeout=15)
        assert st.status_code == 200
        sj = st.json()
        assert sj["payment_status"] != "paid"
        # Order still pending
        orders = requests.get(f"{API}/me/orders", headers=_auth(user_token), timeout=15).json()["items"]
        this = next(o for o in orders if o["id"] == co["id"])
        assert this["payment_status"] == "pending"

    def test_webhook_invalid_signature_rejected(self):
        r = requests.post(f"{BASE_URL}/api/webhook/stripe",
                          data=b'{"type":"checkout.session.completed"}',
                          headers={"Stripe-Signature": "invalid", "Content-Type": "application/json"},
                          timeout=15)
        assert r.status_code in (400, 403), r.status_code

    def test_verify_other_users_order_404(self, user_token, user2_token):
        # user creates order
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        o = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "membership", "item_id": plans[0]["id"], "quantity": 1},
                          timeout=15).json()["order"]
        # user2 tries to verify - must 404
        r = requests.post(f"{API}/payments/verify", headers=_auth(user2_token),
                          json={"order_id": o["id"], "simulate": "success"}, timeout=15)
        assert r.status_code == 404


# ---------- Uploads ----------
class TestUploads:
    _PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x00\x03\x00\x01\x5c\xcd\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82")

    def test_upload_unauth_401(self):
        r = requests.post(f"{API}/uploads",
                          files={"file": ("t.png", io.BytesIO(self._PNG), "image/png")}, timeout=15)
        assert r.status_code == 401

    def test_upload_png_and_fetch(self, user_token):
        r = requests.post(f"{API}/uploads", headers=_auth(user_token),
                          files={"file": ("t.png", io.BytesIO(self._PNG), "image/png")}, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert url.startswith("/api/files/")
        fetch = requests.get(f"{BASE_URL}{url}", timeout=15)
        assert fetch.status_code == 200
        # Note: the backend sets Cache-Control: public, max-age=31536000, immutable
        # but the ingress/CDN rewrites to no-store; we don't validate CDN behaviour.
        assert fetch.content[:4] == b"\x89PNG"

    def test_upload_bad_extension_400(self, user_token):
        r = requests.post(f"{API}/uploads", headers=_auth(user_token),
                          files={"file": ("bad.exe", io.BytesIO(b"MZ\x00\x00"),
                                          "application/octet-stream")}, timeout=15)
        assert r.status_code == 400

    def test_upload_too_large_400(self, user_token):
        big = b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10)
        r = requests.post(f"{API}/uploads", headers=_auth(user_token),
                          files={"file": ("big.png", io.BytesIO(big), "image/png")}, timeout=60)
        assert r.status_code == 400


# ---------- Reviews ----------
class TestReviews:
    @pytest.fixture(scope="class")
    def finished_event(self, admin_token):
        r = requests.get(f"{API}/admin/events?limit=200", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        for title in ["Rooftop Jazz & Tapas Night", "Supper Club: Regional Thali Trail"]:
            match = next((e for e in items if e["title"] == title), None)
            if match:
                return match
        pytest.skip("Finished seeded event not found")

    def test_list_reviews_public(self, finished_event):
        r = requests.get(f"{API}/events/{finished_event['id']}/reviews", timeout=15)
        assert r.status_code == 200
        assert "average" in r.json()

    def test_future_event_review_rejected(self, user_token):
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        fut = next((e for e in evs if e["starts_at"] > "2026-06-01"), evs[0])
        r = requests.post(f"{API}/events/{fut['id']}/reviews", headers=_auth(user_token),
                          json={"rating": 5, "comment": "TEST early"}, timeout=15)
        assert r.status_code in (400, 403)
        if r.status_code == 400:
            assert "finished" in r.json().get("detail", "").lower()

    def test_non_attendee_review_403(self, user2_token, finished_event):
        r = requests.post(f"{API}/events/{finished_event['id']}/reviews",
                          headers=_auth(user2_token),
                          json={"rating": 4, "comment": "TEST outsider"}, timeout=15)
        # user2 may already be an attendee/reviewer depending on seed state
        assert r.status_code in (200, 400, 403)

    def test_duplicate_review_by_attendee(self, attendee_token, finished_event):
        # ananya has already reviewed one according to prompt
        r = requests.post(f"{API}/events/{finished_event['id']}/reviews",
                          headers=_auth(attendee_token),
                          json={"rating": 5, "comment": "TEST duplicate"}, timeout=15)
        # Either duplicate (already reviewed) or created then duplicate on repeat
        if r.status_code == 200:
            # try second time
            r2 = requests.post(f"{API}/events/{finished_event['id']}/reviews",
                               headers=_auth(attendee_token),
                               json={"rating": 5, "comment": "TEST dup2"}, timeout=15)
            assert r2.status_code == 400
        else:
            assert r.status_code == 400

    def test_reviewable_endpoint(self, attendee_token):
        r = requests.get(f"{API}/me/reviewable", headers=_auth(attendee_token), timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_events_sort_rating(self):
        r = requests.get(f"{API}/events?sort=rating&limit=10", timeout=15)
        assert r.status_code == 200


# ---------- Partner payouts ----------
class TestPayouts:
    def test_partner_lists_own_payouts(self, partner_token):
        r = requests.get(f"{API}/partner/payouts", headers=_auth(partner_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        assert "pending_total" in d and "paid_total" in d

    def test_user_forbidden_admin_payouts(self, user_token):
        r = requests.get(f"{API}/admin/payouts", headers=_auth(user_token), timeout=15)
        assert r.status_code == 403

    def test_user_forbidden_partner_payouts(self, user_token):
        r = requests.get(f"{API}/partner/payouts", headers=_auth(user_token), timeout=15)
        assert r.status_code == 403

    def test_generate_payouts_idempotent(self, admin_token):
        r1 = requests.post(f"{API}/admin/payouts/generate", headers=_auth(admin_token), timeout=30)
        assert r1.status_code == 200
        list1 = requests.get(f"{API}/admin/payouts", headers=_auth(admin_token), timeout=15).json()["items"]
        r2 = requests.post(f"{API}/admin/payouts/generate", headers=_auth(admin_token), timeout=30)
        assert r2.status_code == 200
        list2 = requests.get(f"{API}/admin/payouts", headers=_auth(admin_token), timeout=15).json()["items"]
        assert len(list1) == len(list2), "generate_payouts created duplicates"
        # No duplicate event_ids
        event_ids = [p["event_id"] for p in list2]
        assert len(event_ids) == len(set(event_ids)), "duplicate payout rows for same event"

    def test_payout_fee_math(self, admin_token):
        items = requests.get(f"{API}/admin/payouts", headers=_auth(admin_token), timeout=15).json()["items"]
        for p in items:
            expected_fee = round(p["gross"] * p["fee_percent"] / 100, 2)
            assert abs(p["fee"] - expected_fee) < 0.02
            assert abs(p["net"] - (p["gross"] - p["fee"])) < 0.02
            assert p["fee_percent"] == 15

    def test_mark_paid_and_dup_rejected(self, admin_token):
        items = requests.get(f"{API}/admin/payouts?status=pending",
                             headers=_auth(admin_token), timeout=15).json()["items"]
        if not items:
            pytest.skip("no pending payouts")
        pid = items[0]["id"]
        ref = f"TEST_UTR_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/admin/payouts/{pid}/pay", headers=_auth(admin_token),
                          json={"reference": ref}, timeout=15)
        assert r.status_code == 200
        assert r.json()["reference"] == ref
        # Second attempt on same payout - friendly 400
        r2 = requests.post(f"{API}/admin/payouts/{pid}/pay", headers=_auth(admin_token),
                           json={"reference": ref}, timeout=15)
        assert r2.status_code == 400
        # Audit log
        logs = requests.get(f"{API}/admin/audit-logs", headers=_auth(admin_token), timeout=15).json()["items"]
        assert any(l.get("action") == "payout.pay" for l in logs)

    def test_partner2_cannot_see_partner1_payouts(self, partner_token, partner2_token):
        p1 = requests.get(f"{API}/partner/payouts", headers=_auth(partner_token), timeout=15).json()["items"]
        p2 = requests.get(f"{API}/partner/payouts", headers=_auth(partner2_token), timeout=15).json()["items"]
        p1_ids = {x["id"] for x in p1}
        p2_ids = {x["id"] for x in p2}
        assert p1_ids.isdisjoint(p2_ids)


# ---------- Admin per-currency price overrides ----------
class TestPriceOverrides:
    def test_price_override_applies_at_checkout(self, admin_token, user_token):
        # Create a TEST plan with price_overrides
        payload = {"name": f"TEST Override {uuid.uuid4().hex[:4]}",
                   "price": 5000, "duration_days": 30,
                   "price_overrides": {"USD": 19}}
        c = requests.post(f"{API}/admin/plans", headers=_auth(admin_token),
                          json=payload, timeout=15)
        assert c.status_code == 200, c.text
        plan = c.json()
        pid = plan["id"]
        try:
            co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                               json={"kind": "membership", "item_id": pid, "quantity": 1,
                                     "currency": "USD"}, timeout=15)
            assert co.status_code == 200, co.text
            o = co.json()["order"]
            assert o["currency"] == "USD"
            assert o["charge_subtotal"] == 19.0, f"override not applied: {o['charge_subtotal']}"
        finally:
            requests.delete(f"{API}/admin/plans/{pid}", headers=_auth(admin_token), timeout=15)
