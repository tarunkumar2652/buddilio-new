"""Iteration 2 backend tests: Razorpay simulation-mode, event group chat access
control, webhook signature rejection, email fan-out non-blocking, WebSocket
auth close-code 4401, admin refund fallback without Razorpay keys.
"""
import os
import uuid
import json
import asyncio
import requests
import pytest
import websockets

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

ADMIN = {"email": "admin@buddilio.com", "password": "Admin@123"}
PARTNER = {"email": "partner@buddilio.com", "password": "Partner@123"}
USER = {"email": "aarav.mehta@example.com", "password": "User@12345"}
USER2 = {"email": "diya.sharma@example.com", "password": "User@12345"}
USER3 = {"email": "kabir.nair@example.com", "password": "User@12345"}
USER4 = {"email": "meera.rao@example.com", "password": "User@12345"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="module")
def partner_token():
    return _login(**PARTNER)


@pytest.fixture(scope="module")
def user_token():
    return _login(**USER)


@pytest.fixture(scope="module")
def user2_token():
    return _login(**USER2)


@pytest.fixture(scope="module")
def user3_token():
    return _login(**USER3)


# ---------- payments: simulation mode ----------
class TestPaymentsConfig:
    def test_payments_config_simulation_mode(self):
        r = requests.get(f"{API}/payments/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["razorpay_live"] is False
        assert d["razorpay_key_id"] == ""
        assert d["stripe_enabled"] is True
        assert "upi" in d["methods"]["INR"]

    def test_razorpay_order_returns_503_without_keys(self, user_token):
        # Create a real order first
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "membership", "item_id": plans[0]["id"], "quantity": 1},
                           timeout=15).json()["order"]
        r = requests.post(f"{API}/payments/razorpay/order", headers=_auth(user_token),
                          json={"order_id": co["id"]}, timeout=15)
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"].lower()

    def test_razorpay_webhook_returns_503_without_keys(self):
        # Send even a well-formed webhook; must be 503
        r = requests.post(f"{API}/payments/razorpay/webhook",
                          headers={"X-Razorpay-Signature": "deadbeef"},
                          json={"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_fake"}}}},
                          timeout=15)
        assert r.status_code == 503

    def test_razorpay_webhook_cannot_mark_paid_without_signature(self, user_token):
        # Create an order, then try to hit the webhook. Must not become paid.
        plans = requests.get(f"{API}/plans", timeout=15).json()["items"]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "membership", "item_id": plans[0]["id"], "quantity": 1},
                           timeout=15).json()["order"]
        # Call webhook (503 currently) — order must remain pending
        requests.post(f"{API}/payments/razorpay/webhook",
                      json={"event": "payment.captured",
                            "payload": {"payment": {"entity": {"id": "pay_evil",
                                                                "notes": {"buddilio_order": co["id"]}}}}},
                      timeout=15)
        # Verify order is still not paid
        orders = requests.get(f"{API}/me/orders", headers=_auth(user_token), timeout=15).json()["items"]
        this = next(o for o in orders if o["id"] == co["id"])
        assert this["payment_status"] != "paid"


# ---------- purchase fulfilment via simulation ----------
class TestFulfilment:
    def test_paid_event_purchase_grants_chat_and_participation(self, user_token):
        # Find a paid event; ideally 'Street Food Crawl: Old Delhi'
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        paid_events = [e for e in evs if e.get("price", 0) > 0]
        assert paid_events, "no paid event seeded"
        ev = next((e for e in paid_events if "Street Food" in e.get("title", "")), paid_events[0])
        eid = ev["id"]
        # ensure clean state
        requests.post(f"{API}/events/{eid}/cancel", headers=_auth(user_token), timeout=15)
        # Before purchase, chat should 403
        pre = requests.get(f"{API}/events/{eid}/chat", headers=_auth(user_token), timeout=15)
        assert pre.status_code == 403
        assert "paid ticket" in pre.json()["detail"].lower()
        # Buy the pass
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "event", "item_id": eid, "quantity": 1}, timeout=15)
        assert co.status_code == 200, co.text
        order = co.json()["order"]
        pv = requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                           json={"order_id": order["id"], "simulate": "success"}, timeout=15)
        assert pv.status_code == 200
        assert pv.json()["order"]["payment_status"] == "paid"
        # Now chat should be accessible
        post = requests.get(f"{API}/events/{eid}/chat", headers=_auth(user_token), timeout=15)
        assert post.status_code == 200
        assert "conversation_id" in post.json()

    def test_pay_failure_marks_order_failed(self, user_token):
        prods = requests.get(f"{API}/products", timeout=15).json()["items"]
        p = prods[0]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "product", "item_id": p["id"], "quantity": 1}, timeout=15).json()["order"]
        rf = requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                           json={"order_id": co["id"], "simulate": "failure"}, timeout=15)
        assert rf.status_code == 402
        # verify order marked failed
        orders = requests.get(f"{API}/me/orders", headers=_auth(user_token), timeout=15).json()["items"]
        this = next(o for o in orders if o["id"] == co["id"])
        assert this["payment_status"] in ("failed", "unpaid")


# ---------- event group chat access control ----------
class TestEventChatAccess:
    def test_free_event_joiner_gets_403(self, user2_token):
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        free = [e for e in evs if e.get("price", 0) == 0]
        if not free:
            pytest.skip("no free event seeded")
        eid = free[0]["id"]
        requests.post(f"{API}/events/{eid}/cancel", headers=_auth(user2_token), timeout=15)
        j = requests.post(f"{API}/events/{eid}/join", headers=_auth(user2_token), timeout=15)
        assert j.status_code == 200
        r = requests.get(f"{API}/events/{eid}/chat", headers=_auth(user2_token), timeout=15)
        assert r.status_code == 403
        assert "paid" in r.json()["detail"].lower()

    def test_random_user_gets_403(self, user3_token):
        evs = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
        paid = [e for e in evs if e.get("price", 0) > 0]
        if not paid:
            pytest.skip("no paid event")
        eid = paid[0]["id"]
        r = requests.get(f"{API}/events/{eid}/chat", headers=_auth(user3_token), timeout=15)
        assert r.status_code == 403

    def test_organiser_gets_access(self, partner_token, admin_token):
        # Partner creates + admin approves a paid event, then partner opens chat
        title = f"TEST Chat Event {uuid.uuid4().hex[:6]}"
        payload = {
            "title": title, "description": "test", "category": "Nightlife", "city": "Delhi NCR",
            "venue": "V", "starts_at": "2030-01-01T20:00:00+00:00",
            "ends_at": "2030-01-01T23:00:00+00:00", "price": 500, "capacity": 20,
        }
        r = requests.post(f"{API}/partner/events?submit=true",
                          headers=_auth(partner_token), json=payload, timeout=15)
        assert r.status_code == 200
        eid = r.json()["id"]
        requests.post(f"{API}/admin/events/{eid}/moderate",
                      headers=_auth(admin_token), json={"action": "approve"}, timeout=15)
        # Partner is organiser -> should get 200
        c = requests.get(f"{API}/events/{eid}/chat", headers=_auth(partner_token), timeout=15)
        assert c.status_code == 200


# ---------- admin refund fallback without razorpay keys ----------
class TestRefundFallback:
    def test_admin_refund_internal_fallback(self, admin_token, user_token):
        prods = requests.get(f"{API}/products", timeout=15).json()["items"]
        p = prods[0]
        co = requests.post(f"{API}/checkout", headers=_auth(user_token),
                           json={"kind": "product", "item_id": p["id"], "quantity": 1}, timeout=15).json()["order"]
        requests.post(f"{API}/payments/verify", headers=_auth(user_token),
                      json={"order_id": co["id"], "simulate": "success"}, timeout=15)
        rf = requests.post(f"{API}/admin/orders/{co['id']}/refund",
                           headers=_auth(admin_token), timeout=15)
        assert rf.status_code == 200
        assert rf.json()["refund_status"] == "refunded"


# ---------- WebSocket auth ----------
class TestWebSocket:
    @pytest.mark.asyncio
    async def test_ws_rejects_bad_token(self):
        # Server closes before accepting -> handshake rejected with HTTP 403 (or 4401 if accepted).
        try:
            async with websockets.connect(f"{WS_URL}?token=BAD_TOKEN") as ws:
                await asyncio.wait_for(ws.recv(), timeout=5)
                pytest.fail("expected close, got a message")
        except websockets.exceptions.ConnectionClosed as e:
            assert e.code == 4401
        except websockets.exceptions.InvalidStatus as e:
            assert e.response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ws_rejects_missing_token(self):
        try:
            async with websockets.connect(WS_URL) as ws:
                await asyncio.wait_for(ws.recv(), timeout=5)
                pytest.fail("expected close")
        except websockets.exceptions.ConnectionClosed as e:
            assert e.code == 4401
        except websockets.exceptions.InvalidStatus as e:
            assert e.response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ws_valid_token_connects_and_gets_ready(self, user_token):
        async with websockets.connect(f"{WS_URL}?token={user_token}") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert msg["type"] == "ready"
            assert "online" in msg

    @pytest.mark.asyncio
    async def test_ws_two_users_typing_and_presence(self, user_token, user2_token):
        # Ensure a conversation exists between user and user2
        me2 = requests.get(f"{API}/auth/me", headers=_auth(user2_token), timeout=15).json()
        conv = requests.post(f"{API}/conversations", headers=_auth(user_token),
                             json={"user_id": me2["id"]}, timeout=15).json()
        cid = conv["id"]

        async with websockets.connect(f"{WS_URL}?token={user_token}") as ws_a:
            await asyncio.wait_for(ws_a.recv(), timeout=5)  # ready for A
            async with websockets.connect(f"{WS_URL}?token={user2_token}") as ws_b:
                await asyncio.wait_for(ws_b.recv(), timeout=5)  # ready for B
                # A may receive a presence message about B coming online
                # A sends typing on conversation cid
                await ws_a.send(json.dumps({"type": "typing", "conversation_id": cid}))
                # B should receive typing (may need to skip a presence event)
                got_typing = False
                for _ in range(3):
                    m = json.loads(await asyncio.wait_for(ws_b.recv(), timeout=5))
                    if m.get("type") == "typing" and m.get("conversation_id") == cid:
                        got_typing = True
                        break
                assert got_typing, "user B did not receive typing event"


# ---------- registration still non-blocking despite undeliverable email ----------
class TestEmailNonBlocking:
    def test_register_new_example_com_still_succeeds(self):
        # Registration must succeed even though @example.com is undeliverable
        email = f"TEST_email_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "full_name": "TEST Email", "email": email,
            "mobile": "9999999990", "password": "TestPass1", "dob": "1995-01-01",
            "gender": "male", "city": "Delhi NCR",
            "is_adult": True, "accept_terms": True}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == email.lower()
