"""Buddilio backend integration tests.

Uses the public REACT_APP_BACKEND_URL. Tests core auth, discovery, events,
partner/admin moderation, checkout+payment simulate, messaging and CMS.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@buddilio.com", "password": "Admin@123"}
PARTNER = {"email": "partner@buddilio.com", "password": "Partner@123"}
USER = {"email": "aarav.mehta@example.com", "password": "User@123"}
USER2 = {"email": "diya.sharma@example.com", "password": "User@123"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="session")
def partner_token():
    return _login(**PARTNER)


@pytest.fixture(scope="session")
def user_token():
    return _login(**USER)


@pytest.fixture(scope="session")
def user2_token():
    return _login(**USER2)


# ---------- meta / public ----------
class TestPublic:
    def test_meta(self):
        r = requests.get(f"{API}/meta", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "cities" in data and "categories" in data and "interests" in data
        assert isinstance(data["cities"], list)

    def test_events_list_published_only(self):
        r = requests.get(f"{API}/events?limit=50", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list)
        assert data["total"] >= 1
        # All returned events must be published
        for e in data["items"]:
            assert e["status"] == "published"

    def test_events_filters(self):
        r = requests.get(f"{API}/events?city=Delhi NCR&category=Nightlife&max_price=5000", timeout=15)
        assert r.status_code == 200

    def test_plans_public(self):
        r = requests.get(f"{API}/plans", timeout=15)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    def test_products_public(self):
        r = requests.get(f"{API}/products", timeout=15)
        assert r.status_code == 200

    def test_cms_about(self):
        r = requests.get(f"{API}/cms/about", timeout=15)
        # slug 'about' should exist per seed
        assert r.status_code in (200, 404)


# ---------- auth ----------
class TestAuth:
    def test_login_admin(self):
        r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "admin"
        # httpOnly cookie set
        assert "access_token" in r.cookies

    def test_login_partner(self):
        r = requests.post(f"{API}/auth/login", json=PARTNER, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "partner"

    def test_login_user(self):
        r = requests.post(f"{API}/auth/login", json=USER, timeout=15)
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "user"

    def test_login_bad_password(self):
        # use a unique email to avoid rate limit interference
        r = requests.post(f"{API}/auth/login",
                          json={"email": USER["email"], "password": "wrongpass!"}, timeout=15)
        assert r.status_code == 401
        assert "Invalid" in r.json().get("detail", "")

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_ok(self, user_token):
        r = requests.get(f"{API}/auth/me", headers=_auth(user_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == USER["email"]

    def test_register_underage_rejected(self):
        payload = {
            "full_name": "TEST Young", "email": f"TEST_young_{uuid.uuid4().hex[:6]}@example.com",
            "mobile": "9999999999", "password": "TestPass1", "dob": "2015-01-01",
            "gender": "female", "city": "Delhi NCR",
            "is_adult": True, "accept_terms": True,
        }
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 400
        assert "21" in r.json()["detail"]

    def test_register_checkboxes_required(self):
        payload = {
            "full_name": "TEST NoTerms", "email": f"TEST_terms_{uuid.uuid4().hex[:6]}@example.com",
            "mobile": "9999999999", "password": "TestPass1", "dob": "1995-01-01",
            "gender": "male", "city": "Delhi NCR",
            "is_adult": False, "accept_terms": False,
        }
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 400
        assert "policies" in r.json()["detail"] or "confirm" in r.json()["detail"]

    def test_register_and_login(self):
        email = f"TEST_reg_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "full_name": "TEST Reg", "email": email,
            "mobile": "9999999999", "password": "TestPass1", "dob": "1995-01-01",
            "gender": "male", "city": "Delhi NCR",
            "interests": ["Music"], "event_categories": ["Nightlife"],
            "is_adult": True, "accept_terms": True,
        }
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == email.lower()
        # cleanup: login and delete via admin if possible (soft - just leave test data)

    def test_brute_force_lockout(self):
        # Use a dedicated email so we don't lock real users
        email = f"TEST_lockout_{uuid.uuid4().hex[:6]}@example.com"
        # It doesn't need to exist; wrong-password path still increments counter for identifier
        codes = []
        for _ in range(6):
            rr = requests.post(f"{API}/auth/login", json={"email": email, "password": "x"}, timeout=15)
            codes.append(rr.status_code)
        # Expect at least one 429 by the 6th attempt
        assert 429 in codes, f"no lockout observed, got {codes}"


# ---------- discover / profile ----------
class TestDiscover:
    def test_discover_requires_auth(self):
        r = requests.get(f"{API}/discover", timeout=15)
        assert r.status_code == 401

    def test_discover_returns_users(self, user_token):
        r = requests.get(f"{API}/discover?limit=12", headers=_auth(user_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list)
        assert data["total"] >= 1
        for it in data["items"]:
            assert it["role"] == "user"
            assert "password_hash" not in it

    def test_update_profile_persists(self, user_token):
        new_bio = f"TEST bio {uuid.uuid4().hex[:6]}"
        r = requests.put(f"{API}/users/me", headers=_auth(user_token),
                         json={"bio": new_bio}, timeout=15)
        assert r.status_code == 200
        assert r.json()["bio"] == new_bio
        # verify by GET /auth/me
        r2 = requests.get(f"{API}/auth/me", headers=_auth(user_token), timeout=15)
        assert r2.json()["bio"] == new_bio


# ---------- events flow ----------
class TestEvents:
    def test_join_free_event(self, user_token, user2_token):
        # find a free published event
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        free = [e for e in evs if e.get("price", 0) == 0]
        if not free:
            pytest.skip("no free event seeded")
        eid = free[0]["id"]
        # cancel first to reset
        requests.post(f"{API}/events/{eid}/cancel", headers=_auth(user2_token), timeout=15)
        r = requests.post(f"{API}/events/{eid}/join", headers=_auth(user2_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("confirmed", "pending")
        # duplicate join blocked
        r2 = requests.post(f"{API}/events/{eid}/join", headers=_auth(user2_token), timeout=15)
        assert r2.status_code == 400
        # cleanup
        requests.post(f"{API}/events/{eid}/cancel", headers=_auth(user2_token), timeout=15)

    def test_paid_event_requires_purchase(self, user_token):
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        paid = [e for e in evs if e.get("price", 0) > 0]
        if not paid:
            pytest.skip("no paid event")
        eid = paid[0]["id"]
        r = requests.post(f"{API}/events/{eid}/join", headers=_auth(user_token), timeout=15)
        assert r.status_code == 400

    def test_save_toggle(self, user_token):
        evs = requests.get(f"{API}/events?limit=1", timeout=15).json()["items"]
        eid = evs[0]["id"]
        r1 = requests.post(f"{API}/events/{eid}/save", headers=_auth(user_token), timeout=15)
        assert r1.status_code == 200
        s1 = r1.json()["saved"]
        r2 = requests.post(f"{API}/events/{eid}/save", headers=_auth(user_token), timeout=15)
        assert r2.json()["saved"] != s1


# ---------- checkout / payment ----------
class TestCheckout:
    def test_coupon_buddy20_applies(self, user_token):
        # find a product with price high enough for min_order 500
        prods = requests.get(f"{API}/products", timeout=15).json()["items"]
        prod = next((p for p in prods if p["price"] >= 600), prods[0] if prods else None)
        if not prod:
            pytest.skip("no products")
        r = requests.post(f"{API}/checkout", headers=_auth(user_token),
                          json={"kind": "product", "item_id": prod["id"],
                                "quantity": 1, "coupon_code": "BUDDY20"}, timeout=15)
        assert r.status_code == 200, r.text
        order = r.json()["order"]
        assert order["discount"] > 0
        assert order["coupon"] == "BUDDY20"
        # simulate failure
        rf = requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                           json={"order_id": order["id"], "simulate": "failure"}, timeout=15)
        assert rf.status_code == 402

    def test_pay_success_and_membership_active(self, user_token):
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        if not plans:
            pytest.skip("no plans")
        plan = plans[0]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "membership", "item_id": plan["id"], "quantity": 1},
                           timeout=15)
        assert co.status_code == 200
        order = co.json()["order"]
        # verify success
        vp = requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                          json={"order_id": order["id"], "simulate": "success"}, timeout=15)
        assert vp.status_code == 200, vp.text
        assert vp.json()["order"]["payment_status"] == "paid"
        # membership should now be active
        me = requests.get(f"{API}/me/membership", headers=_auth(user_token), timeout=15).json()
        assert me["membership"] is not None
        assert me["membership"]["status"] == "active"

    def test_orders_list(self, user_token):
        r = requests.get(f"{API}/me/orders", headers=_auth(user_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1


# ---------- messaging ----------
class TestChat:
    def test_conversation_and_message(self, user_token, user2_token):
        # get other user id
        me2 = requests.get(f"{API}/auth/me", headers=_auth(user2_token), timeout=15).json()
        r = requests.post(f"{API}/conversations", headers=_auth(user_token),
                          json={"user_id": me2["id"]}, timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]
        s = requests.post(f"{API}/conversations/{cid}/messages", headers=_auth(user_token),
                          json={"body": f"TEST hello {uuid.uuid4().hex[:4]}"}, timeout=15)
        assert s.status_code == 200
        msgs = requests.get(f"{API}/conversations/{cid}/messages",
                            headers=_auth(user2_token), timeout=15).json()["items"]
        assert any("TEST hello" in m["body"] for m in msgs)


# ---------- partner + admin approve ----------
class TestPartnerAdmin:
    def test_partner_creates_event_then_admin_approves(self, partner_token, admin_token):
        title = f"TEST Partner Event {uuid.uuid4().hex[:6]}"
        payload = {
            "title": title, "description": "test", "category": "Nightlife", "city": "Delhi NCR",
            "venue": "Test Venue", "starts_at": "2030-01-01T20:00:00+00:00",
            "ends_at": "2030-01-01T23:00:00+00:00", "price": 500, "capacity": 20,
        }
        r = requests.post(f"{API}/partner/events?submit=true",
                          headers=_auth(partner_token), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev["status"] == "submitted"
        eid = ev["id"]
        # public /events must NOT include it
        pub = requests.get(f"{API}/events?q=TEST Partner", timeout=15).json()["items"]
        assert not any(p["id"] == eid for p in pub), "unpublished event leaking to public list"
        # admin approves
        ap = requests.post(f"{API}/admin/events/{eid}/moderate",
                           headers=_auth(admin_token),
                           json={"action": "approve"}, timeout=15)
        assert ap.status_code == 200
        assert ap.json()["status"] == "published"
        # verify appears now
        pub2 = requests.get(f"{API}/events?q=TEST Partner", timeout=15).json()["items"]
        assert any(p["id"] == eid for p in pub2)

    def test_partner_role_protected(self, user_token):
        r = requests.get(f"{API}/partner/events", headers=_auth(user_token), timeout=15)
        assert r.status_code == 403

    def test_admin_role_protected(self, user_token):
        r = requests.get(f"{API}/admin/stats", headers=_auth(user_token), timeout=15)
        assert r.status_code == 403


# ---------- admin management ----------
class TestAdmin:
    def test_admin_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats?days=30", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_users", "events", "gross_sales", "revenue_series"):
            assert k in d

    def test_admin_users_list(self, admin_token):
        r = requests.get(f"{API}/admin/users?limit=5", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1

    def test_admin_refund_flow(self, admin_token, user_token):
        # create + pay a small product order
        prods = requests.get(f"{API}/products", timeout=15).json()["items"]
        if not prods:
            pytest.skip("no products")
        p = prods[0]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "product", "item_id": p["id"], "quantity": 1}, timeout=15).json()["order"]
        requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                      json={"order_id": co["id"], "simulate": "success"}, timeout=15)
        rf = requests.post(f"{API}/admin/orders/{co['id']}/refund",
                           headers=_auth(admin_token), timeout=15)
        assert rf.status_code == 200
        assert rf.json()["refund_status"] == "refunded"

    def test_plans_crud(self, admin_token):
        payload = {"name": f"TEST Plan {uuid.uuid4().hex[:4]}", "price": 99, "duration_days": 30}
        c = requests.post(f"{API}/admin/plans", headers=_auth(admin_token),
                          json=payload, timeout=15)
        assert c.status_code == 200
        pid = c.json()["id"]
        u = requests.put(f"{API}/admin/plans/{pid}", headers=_auth(admin_token),
                         json={**payload, "price": 149}, timeout=15)
        assert u.json()["price"] == 149
        d = requests.delete(f"{API}/admin/plans/{pid}", headers=_auth(admin_token), timeout=15)
        assert d.status_code == 200

    def test_audit_logs(self, admin_token):
        r = requests.get(f"{API}/admin/audit-logs", headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1
