"""Iteration 9: per-neighbourhood guide photos, fuller Gulf calendar, public leaderboard."""
import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE}/api"

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _get(path, **kw):
    """These suites walk all 27 cities, so retry the odd dropped connection under load."""
    last = None
    for _ in range(4):
        try:
            r = requests.get(f"{API}{path}", timeout=20, **kw)
            if r.status_code == 200:
                return r.json()
            last = f"{r.status_code} {r.text[:120]}"
        except requests.RequestException as e:
            last = repr(e)
        time.sleep(1.5)
    raise AssertionError(f"GET {path} failed: {last}")


def _login(email, password="User@12345"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------ GUIDE PHOTOGRAPHY -------------

def test_every_neighbourhood_card_has_a_photo():
    cities = _get("/cities")["items"]
    seen = set()
    for c in cities:
        areas = _get(f"/cities/{c['slug']}")["guide"]["areas"]
        for a in areas:
            assert len(a) == 3, f"{c['slug']} area missing its photo: {a}"
            name, blurb, photo = a
            assert photo.startswith("https://images.unsplash.com/photo-"), photo
            assert "w=900" in photo, "photos should be served at card width"
            seen.add(photo)
        # inside one city the photos must not repeat
        assert len({a[2] for a in areas}) == len(areas), f"{c['slug']} repeats a photo"
    assert len(seen) >= 90, f"expected a wide photo set, got {len(seen)}"


def test_city_photos_load():
    areas = requests.get(f"{API}/cities/dubai", timeout=15).json()["guide"]["areas"]
    for _, _, photo in areas[:2]:
        r = requests.head(photo, timeout=20, allow_redirects=True)
        assert r.status_code == 200, f"{photo} -> {r.status_code}"
        assert "image" in r.headers.get("content-type", "")


# ------------ GULF CALENDAR -------------

def test_gulf_cities_have_a_full_calendar():
    counts = {c["slug"]: c for c in _get("/cities")["items"]}
    # Fixed floors, not a comparison with Delhi — other suites litter Delhi with TEST events.
    assert counts["dubai"]["events"] >= 5, counts["dubai"]
    assert counts["abu-dhabi"]["events"] >= 4, counts["abu-dhabi"]
    assert counts["dubai"]["events"] + counts["abu-dhabi"]["events"] >= 9
    assert counts["dubai"]["members"] >= 3 and counts["abu-dhabi"]["members"] >= 2


def test_gulf_events_are_priced_in_aed_and_visible():
    d = requests.get(f"{API}/cities/dubai", timeout=15).json()
    assert len(d["upcoming"]) >= 5
    assert d["members"] >= 3 and len(d["faces"]) >= 2
    assert len(d["categories"]) >= 3, d["categories"]
    for ev in d["upcoming"]:
        assert ev["price_currency"] == "AED", ev["title"]
        assert ev["price_overrides"].get("AED") == ev["price_input"]
        assert ev["cover_image"].startswith("https://"), ev["title"]

    a = requests.get(f"{API}/cities/abu-dhabi", timeout=15).json()
    assert len(a["upcoming"]) >= 4 and a["currency"] == "AED"

    # they show up in the public events feed with the city filter too
    items = requests.get(f"{API}/events", params={"city": "Abu Dhabi", "limit": 20}, timeout=15).json()["items"]
    assert len(items) >= 4 and all(i["city"] == "Abu Dhabi" for i in items)


# ------------ PUBLIC LEADERBOARD -------------

def test_leaderboard_is_public_for_guests():
    r = requests.get(f"{API}/referrals/leaderboard", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["me"] is None, "guests must not get a personal block"
    assert d["items"], "guests should still see the ranking"
    assert all(row["me"] is False for row in d["items"])
    assert d["champion"] and d["champion"]["me"] is False
    assert d["prize"]
    # only shortened names are exposed publicly
    for row in d["items"]:
        assert row["name"].endswith(".") or " " not in row["name"], row["name"]
        assert "@" not in row["name"]
        assert set(row) == {"rank", "name", "photo", "city", "invites", "credit", "badge", "me"}


def test_leaderboard_still_personalised_when_signed_in():
    h = _login("tara.joshi@example.com")
    d = requests.get(f"{API}/referrals/leaderboard", headers=h, timeout=15).json()
    assert d["me"] and d["me"]["rank"] == 1 and d["me"]["badge"]["name"]
    assert any(row["me"] for row in d["items"])
