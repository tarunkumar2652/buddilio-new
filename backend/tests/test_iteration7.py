"""Iteration 7: city SEO pages, referral leaderboard, organiser local pricing."""
import os
import uuid
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE}/api"

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _purge_event(event_id: str):
    _db.orders.delete_many({"ref_id": event_id})
    _db.events.delete_one({"_id": ObjectId(event_id)})


def _login(email, password="User@123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------ CITY PAGES -------------

def test_city_index_lists_every_city():
    r = requests.get(f"{API}/cities", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cities"] >= 27 and d["countries"] == 12
    slugs = {c["slug"] for c in d["items"]}
    for s in ["dubai", "london", "delhi-ncr", "new-york", "abu-dhabi", "tokyo"]:
        assert s in slugs, f"{s} missing"
    assert d["live_cities"] >= 1
    dubai = next(c for c in d["items"] if c["slug"] == "dubai")
    assert dubai["currency"] == "AED" and dubai["country"] == "United Arab Emirates"


def test_city_page_dubai_and_london():
    for slug, city, currency, tax in [("dubai", "Dubai", "AED", "VAT"), ("london", "London", "GBP", "VAT")]:
        r = requests.get(f"{API}/cities/{slug}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == city and d["currency"] == currency and d["tax_label"] == tax
        assert d["slug"] == slug and d["emergency"]
        assert isinstance(d["upcoming"], list) and isinstance(d["categories"], list)
        assert d["events_total"] >= 0 and d["members"] >= 0
        for ev in d["upcoming"]:
            assert ev["city"] == city and ev["status"] == "published"
            assert "_id" not in ev and ev["id"]


def test_city_page_unknown_slug_is_404():
    r = requests.get(f"{API}/cities/atlantis", timeout=15)
    assert r.status_code == 404
    assert "city" in r.json()["detail"].lower()


def test_city_waitlist_capture():
    email = f"TEST_wait_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/cities/vancouver/waitlist", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    first = r.json()["waiting"]
    assert first >= 1 and "Vancouver" in r.json()["message"]
    # same email twice must not double count
    r = requests.post(f"{API}/cities/vancouver/waitlist", json={"email": email}, timeout=15)
    assert r.status_code == 200 and r.json()["waiting"] == first
    r = requests.post(f"{API}/cities/vancouver/waitlist", json={"email": "not-an-email"}, timeout=15)
    assert r.status_code == 400
    r = requests.post(f"{API}/cities/atlantis/waitlist", json={"email": email}, timeout=15)
    assert r.status_code == 404


# ------------ REFERRAL LEADERBOARD -------------

def test_leaderboard_ranks_and_badges():
    h = _login("tara.joshi@example.com")
    r = requests.get(f"{API}/referrals/leaderboard", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["month"]) == 7 and d["reward"] > 0
    rows = d["items"]
    assert rows, "leaderboard is empty — run backend/seed_referrals.py"
    assert [x["rank"] for x in rows] == list(range(1, len(rows) + 1))
    assert all(rows[i]["invites"] >= rows[i + 1]["invites"] for i in range(len(rows) - 1))
    top = rows[0]
    assert top["credit"] == top["invites"] * d["reward"]
    assert top["badge"] in ("Starter", "Connector", "Ambassador", "Legend")
    # names are shortened to first name + last initial, never a full surname
    assert top["name"].endswith(".") or " " not in top["name"], top["name"]
    assert any(x["me"] for x in rows), "signed-in member should be flagged on the board"
    me = d["me"]
    assert me["rank"] >= 1 and me["invites"] >= 1 and me["badge"]["name"]


def test_leaderboard_month_filter_and_public_access():
    h = _login("tara.joshi@example.com")
    d = requests.get(f"{API}/referrals/leaderboard", params={"month": "2019-01"}, headers=h, timeout=15).json()
    assert d["month"] == "2019-01" and d["items"] == [] and d["me"]["rank"] == 0
    # the board is public social proof — guests see the ranking but no personal block
    guest = requests.get(f"{API}/referrals/leaderboard", timeout=15)
    assert guest.status_code == 200 and guest.json()["me"] is None


def test_referral_code_lookup_still_works():
    h = _login("tara.joshi@example.com")
    mine = requests.get(f"{API}/me/referrals", headers=h, timeout=15).json()
    assert mine["badge"]["name"], mine
    r = requests.get(f"{API}/referrals/{mine['code']}", timeout=15)
    assert r.status_code == 200 and r.json()["referrer_name"] == "Tara"


# ------------ ORGANISER LOCAL PRICING -------------

def _event_payload(**over):
    body = {"title": f"TEST Local Pricing {uuid.uuid4().hex[:6]}", "category": "Nightlife",
            "city": "Dubai", "venue": "Marina", "starts_at": "2026-12-20T19:00",
            "ends_at": "2026-12-20T23:00", "price": 250, "price_currency": "AED", "capacity": 30}
    body.update(over)
    return body


def test_partner_prices_in_local_currency():
    h = _login("partner@buddilio.com", "Partner@123")
    r = requests.post(f"{API}/partner/events", json=_event_payload(), headers=h, timeout=20)
    assert r.status_code == 200, r.text
    ev = r.json()
    try:
        assert ev["price_currency"] == "AED" and ev["price_input"] == 250
        assert ev["price_overrides"] == {"AED": 250}
        assert ev["price"] > 250, "base amount should be the converted INR value"
        assert ev["country_code"] == "AE"

        # editing keeps the local amount authoritative
        r = requests.put(f"{API}/partner/events/{ev['id']}", json=_event_payload(price=300), headers=h, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["price_overrides"] == {"AED": 300}

        # locals pay the exact amount the organiser typed, plus their own tax
        buyer = _login("omar.alrashid@example.com")
        o = requests.post(f"{API}/checkout", json={"kind": "event", "item_id": ev["id"],
                                                   "quantity": 1, "currency": "AED",
                                                   "use_credit": False},
                          headers=buyer, timeout=20).json()["order"]
        assert o["charge_subtotal"] == 300 and o["tax_label"] == "VAT"
        assert o["charge_total"] == 315, o

        # unsupported currency is rejected
        r = requests.put(f"{API}/partner/events/{ev['id']}", json=_event_payload(price_currency="XYZ"),
                         headers=h, timeout=20)
        assert r.status_code == 400
    finally:
        _purge_event(ev["id"])


def test_base_currency_pricing_has_no_override():
    h = _login("partner@buddilio.com", "Partner@123")
    r = requests.post(f"{API}/partner/events",
                      json=_event_payload(city="Mumbai", price=1500, price_currency="INR"),
                      headers=h, timeout=20)
    assert r.status_code == 200, r.text
    ev = r.json()
    try:
        assert ev["price"] == 1500 and ev["price_input"] == 1500
        assert ev["price_overrides"] == {} and ev["price_currency"] == "INR"
    finally:
        _purge_event(ev["id"])
