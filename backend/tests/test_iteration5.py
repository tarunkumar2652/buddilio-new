"""Iteration 5: globalization, referrals+credit, push, review highlights."""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE}/api"


def _login(email, password="User@123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------ META -------------

def test_meta_countries_currencies():
    r = requests.get(f"{API}/meta", timeout=15)
    assert r.status_code == 200
    d = r.json()
    countries = d.get("countries") or []
    codes = {c["code"] for c in countries}
    assert len(countries) == 12, f"countries={len(countries)}"
    for c in ["IN", "AE", "GB", "US", "SG", "TH", "CA", "AU", "JP", "ES"]:
        assert c in codes
    cities = d.get("cities") or []
    assert len(cities) >= 27
    currencies = d.get("currencies") or []
    if isinstance(currencies, list):
        cur_codes = {c["code"] for c in currencies}
    else:
        cur_codes = set(currencies.keys())
    for cur in ["INR", "USD", "EUR", "GBP", "AED", "SGD", "CAD", "AUD", "THB", "JPY"]:
        assert cur in cur_codes, f"{cur} missing"


# ------------ EVENTS -------------

def test_events_country_filter_and_top_review():
    all_items = requests.get(f"{API}/events?limit=50", timeout=15).json()["items"]
    assert len(all_items) >= 20, f"only {len(all_items)} events"
    # UAE by NAME
    ae = requests.get(f"{API}/events?country=United%20Arab%20Emirates", timeout=15).json()["items"]
    assert any("Marina" in i["title"] for i in ae), f"Dubai event missing: {ae}"
    # Japan by NAME
    jp = requests.get(f"{API}/events?country=Japan", timeout=15).json()["items"]
    assert any(i.get("city") == "Tokyo" for i in jp), f"Tokyo missing: {jp}"
    # international cities represented
    all_cities = {i.get("city") for i in all_items}
    for expected_city in ["Dubai", "London", "Singapore", "Bangkok", "New York", "Sydney", "Tokyo", "Barcelona"]:
        # not all may be in first page — fetch by city
        r = requests.get(f"{API}/events?city={expected_city}", timeout=15).json()["items"]
        assert r, f"no events for {expected_city}"
        assert r[0].get("cover_image"), f"no cover_image for {expected_city} event"

    # top_review on past events
    past = requests.get(f"{API}/events?when=past", timeout=15).json()["items"]
    with_top = [e for e in past if e.get("top_review")]
    assert with_top, "no past events have top_review"
    tr = with_top[0]["top_review"]
    for k in ("rating", "comment", "user_name"):
        assert k in tr
    assert tr["comment"] and "TEST outsider" not in tr["comment"]


# ------------ CHECKOUT tax labels -------------

@pytest.mark.parametrize("email,currency,label,pct", [
    ("liam.oconnor@example.com", "GBP", "VAT", 20.0),
    ("omar.alrashid@example.com", "AED", "VAT", 5.0),
    ("amara.okafor@example.com", "USD", "Sales tax", 8.875),
    ("yuki.tanaka@example.com", "JPY", "Consumption tax", 10.0),
    ("tara.joshi@example.com", "INR", "GST", 18.0),
])
def test_checkout_tax_labels(email, currency, label, pct):
    h = _login(email)
    products = requests.get(f"{API}/products", timeout=15).json()
    products = products.get("items") or products
    pid = products[0]["id"]
    r = requests.post(f"{API}/checkout",
                      json={"kind": "product", "item_id": pid, "quantity": 1, "currency": currency},
                      headers=h, timeout=15)
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["currency"] == currency
    assert o["tax_label"] == label, f"expected {label}, got {o['tax_label']}"
    assert abs(o["tax_percent"] - pct) < 0.01


# ------------ REFERRALS -------------

def test_referrals_flow_end_to_end():
    inviter = _login("tara.joshi@example.com")
    data = requests.get(f"{API}/me/referrals", headers=inviter, timeout=15).json()
    code = data["code"]
    assert code and len(code) >= 4
    init_balance = data["balance"]
    init_joined = data["joined"]

    # lookup
    r = requests.get(f"{API}/referrals/{code}", timeout=15)
    assert r.status_code == 200
    assert r.json()["referrer_name"] == "Tara"

    # register invitee via referral link
    uniq = uuid.uuid4().hex[:8]
    payload = {
        "email": f"TEST_ref_{uniq}@example.com", "password": "User@123",
        "full_name": f"TEST Referral {uniq}", "mobile": f"+441234{uniq[:6]}",
        "dob": "1995-01-01", "gender": "female", "city": "London",
        "interests": ["dining"], "is_adult": True, "accept_terms": True,
        "referral_code": code,
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    invitee_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    d2 = requests.get(f"{API}/me/referrals", headers=inviter, timeout=15).json()
    assert d2["joined"] == init_joined + 1, f"joined {d2['joined']} vs {init_joined}"
    # newest invite awaiting
    latest = d2["invites"][0]
    assert latest["status"] in ("pending", "joined", "awaiting")

    # invitee pays for a pass (INR simulated)
    products = requests.get(f"{API}/products", timeout=15).json()
    products = products.get("items") or products
    pid = products[0]["id"]
    r = requests.post(f"{API}/checkout",
                      json={"kind": "product", "item_id": pid, "quantity": 1, "currency": "INR"},
                      headers=invitee_h, timeout=15)
    assert r.status_code == 200, r.text
    oid = r.json()["order"]["id"]
    r = requests.post(f"{API}/payments/verify",
                      json={"order_id": oid, "simulate": "success"},
                      headers=invitee_h, timeout=15)
    assert r.status_code == 200, r.text

    time.sleep(1)
    d3 = requests.get(f"{API}/me/referrals", headers=inviter, timeout=15).json()
    assert d3["balance"] >= init_balance + 250, f"balance {d3['balance']} vs {init_balance}"
    assert d3["rewarded"] >= 1

    # inviter starts checkout: credit auto-applied
    r = requests.post(f"{API}/checkout",
                      json={"kind": "product", "item_id": pid, "quantity": 1, "currency": "INR",
                            "use_credit": True},
                      headers=inviter, timeout=15)
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o.get("credit_applied", 0) > 0, f"credit not applied: {o}"

    # unticking → no credit
    r = requests.post(f"{API}/checkout",
                      json={"kind": "product", "item_id": pid, "quantity": 1, "currency": "INR",
                            "use_credit": False},
                      headers=inviter, timeout=15)
    o2 = r.json()["order"]
    assert o2.get("credit_applied", 0) == 0
    assert o2["total"] > o["total"]


# ------------ PUSH -------------

def test_push_config():
    d = requests.get(f"{API}/push/config", timeout=15).json()
    assert d.get("enabled") is True
    assert d.get("public_key") and len(d["public_key"]) > 30


def test_push_test_without_subscription_returns_friendly_400():
    h = _login("chloe.nguyen@example.com")
    # clean any existing subs on any endpoint
    requests.post(f"{API}/push/unsubscribe", json={"endpoint": ""}, headers=h, timeout=15)
    r = requests.post(f"{API}/push/test", headers=h, timeout=15)
    assert r.status_code == 400
    detail = (r.json().get("detail") or "").lower()
    assert "device" in detail or "alert" in detail


def test_push_subscribe_and_unsubscribe():
    h = _login("chloe.nguyen@example.com")
    endpoint = f"https://fcm.googleapis.com/fcm/send/TEST_{uuid.uuid4().hex[:8]}"
    sub = {"endpoint": endpoint, "keys": {"p256dh": "BOa" + "A" * 85, "auth": "B" * 22}}
    r = requests.post(f"{API}/push/subscribe", json=sub, headers=h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r = requests.post(f"{API}/push/unsubscribe", json={"endpoint": endpoint}, headers=h, timeout=15)
    assert r.status_code == 200


# ------------ PROFILE country auto-derived -------------

def test_profile_city_change_updates_country():
    h = _login("liam.oconnor@example.com")
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
    original_city = me.get("city")
    r = requests.put(f"{API}/users/me", json={"city": "Berlin"}, headers=h, timeout=15)
    assert r.status_code == 200, r.text
    me2 = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
    assert me2.get("country_code") == "DE", f"country_code={me2.get('country_code')} country={me2.get('country')}"
    # restore
    requests.put(f"{API}/users/me", json={"city": original_city}, headers=h, timeout=15)


def test_discover_country_filter_by_name():
    h = _login("tara.joshi@example.com")
    r = requests.get(f"{API}/discover?country=United%20Kingdom", headers=h, timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items, "no UK members via discover"
    assert any((i.get("city") or "") == "London" for i in items)
