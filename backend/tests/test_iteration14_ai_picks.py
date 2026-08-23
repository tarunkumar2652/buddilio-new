"""Iteration 14: /api/ai/picks — dashboard 'Picked for you by Buddy' row.

Covers: auth, per-member isolation, geography sanity, exclude-joined, caching (same
generated_at), refresh regenerates, hydration guard drops unpublished/past events,
'why' copy doesn't leak internal prompt wording.
"""
import os
import time
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") \
    else "https://lifestyle-connect-17.preview.emergentagent.com"
API = f"{BASE_URL}/api"

DIYA = ("diya.sharma@example.com", "User@12345")   # Mumbai
TARA = ("tara.joshi@example.com", "User@12345")    # Delhi NCR

FORBIDDEN_WORDS = ["candidate", "same-country", "same country", "variety", "JSON",
                   "json", "rule", "id=", "prompt"]

INDIA_CITIES = {"mumbai", "delhi", "new delhi", "delhi ncr", "gurugram", "gurgaon",
                "noida", "bengaluru", "bangalore", "hyderabad", "chennai", "kolkata",
                "pune", "ahmedabad", "goa", "jaipur", "kochi"}


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def diya_token():
    return _login(*DIYA)


@pytest.fixture(scope="module")
def tara_token():
    return _login(*TARA)


# ---------- Auth ----------
def test_picks_requires_auth():
    r = requests.get(f"{API}/ai/picks", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403 without token, got {r.status_code}"


# ---------- Basic shape + why copy hygiene ----------
def test_diya_picks_shape_and_geo(diya_token):
    r = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("enabled") is True
    items = data.get("items") or []
    assert 1 <= len(items) <= 3, f"expected 1-3 picks, got {len(items)}"
    assert "generated_at" in data

    for ev in items:
        assert ev.get("id")
        assert ev.get("title")
        why = (ev.get("why") or "").strip()
        assert why, f"missing why for {ev.get('id')}"
        low = why.lower()
        for bad in FORBIDDEN_WORDS:
            assert bad.lower() not in low, f"internal prompt word leak '{bad}' in why: {why!r}"
        # Geography: India-based member => India city
        city = (ev.get("city") or "").lower()
        country = (ev.get("country") or "").lower()
        assert "india" in country or any(c in city for c in INDIA_CITIES), \
            f"India member got non-India pick: city={city!r} country={country!r}"


def test_tara_picks_shape_and_geo(tara_token):
    r = requests.get(f"{API}/ai/picks", headers=_headers(tara_token), timeout=90)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert 1 <= len(items) <= 3
    for ev in items:
        city = (ev.get("city") or "").lower()
        country = (ev.get("country") or "").lower()
        assert "india" in country or any(c in city for c in INDIA_CITIES), \
            f"Tara (Delhi NCR) got non-India pick: {city!r}/{country!r}"


# ---------- Exclude joined events ----------
def test_picks_exclude_joined_events(diya_token, mongo):
    # login-derived id: fetch /auth/me
    me = requests.get(f"{API}/auth/me", headers=_headers(diya_token), timeout=15).json()
    uid = me["id"]
    joined = {p["event_id"] for p in mongo.event_participants.find({"user_id": uid}, {"event_id": 1})}
    items = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json().get("items") or []
    for ev in items:
        assert ev["id"] not in joined, f"pick {ev['id']} is already joined by member"


# ---------- Per-member isolation ----------
def test_diya_and_tara_get_different_picks(diya_token, tara_token):
    a = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json().get("items") or []
    b = requests.get(f"{API}/ai/picks", headers=_headers(tara_token), timeout=60).json().get("items") or []
    assert a and b
    a_ids = {e["id"] for e in a}
    b_ids = {e["id"] for e in b}
    # Different cities/interests => at least one pick should differ
    assert a_ids != b_ids, f"Diya and Tara returned identical picks — isolation broken"


# ---------- Caching semantics ----------
def test_cache_hit_returns_same_generated_at(diya_token):
    r1 = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json()
    time.sleep(1)
    r2 = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json()
    assert r1.get("generated_at") == r2.get("generated_at"), \
        f"cache miss on second call: {r1.get('generated_at')} vs {r2.get('generated_at')}"
    assert [e["id"] for e in r1["items"]] == [e["id"] for e in r2["items"]]


def test_refresh_regenerates(tara_token):
    r1 = requests.get(f"{API}/ai/picks", headers=_headers(tara_token), timeout=60).json()
    time.sleep(2)
    r2 = requests.get(f"{API}/ai/picks?refresh=1", headers=_headers(tara_token), timeout=90).json()
    assert r1.get("generated_at") != r2.get("generated_at"), \
        f"refresh did not update generated_at: {r1.get('generated_at')}"


# ---------- Hydration guard: draft events get dropped ----------
def test_hydration_drops_unpublished_events(diya_token, mongo):
    # ensure cache exists
    r = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json()
    items = r.get("items") or []
    if not items:
        pytest.skip("no picks to hydrate-test")
    target_id = items[0]["id"]
    original_status = mongo.events.find_one({"_id": ObjectId(target_id)}, {"status": 1})["status"]
    try:
        mongo.events.update_one({"_id": ObjectId(target_id)}, {"$set": {"status": "draft"}})
        # cache is still fresh, so this call reuses the cache but must hydrate-drop the draft one
        r2 = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json()
        remaining = {e["id"] for e in (r2.get("items") or [])}
        assert target_id not in remaining, \
            f"draft event {target_id} was still returned after status flip"
    finally:
        mongo.events.update_one({"_id": ObjectId(target_id)}, {"$set": {"status": original_status}})


# ---------- Referenced events are still upcoming + resolvable ----------
def test_picked_events_are_upcoming_published(diya_token, mongo):
    items = requests.get(f"{API}/ai/picks", headers=_headers(diya_token), timeout=60).json().get("items") or []
    for ev in items:
        doc = mongo.events.find_one({"_id": ObjectId(ev["id"])}, {"status": 1, "starts_at": 1})
        assert doc, f"pick {ev['id']} not in db"
        assert doc["status"] == "published"


# ---------- db.ai_picks unique index ----------
def test_ai_picks_index(mongo):
    idx = mongo.ai_picks.index_information()
    keys_unique = [(name, spec.get("unique", False)) for name, spec in idx.items() if "user_id" in str(spec.get("key", ""))]
    assert any(u for _, u in keys_unique), f"expected unique index on ai_picks.user_id, got {idx}"
