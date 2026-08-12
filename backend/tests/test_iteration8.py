"""Iteration 8: editorial city guides, monthly leaderboard prize, city-opening waitlist emails."""
import os
import time
import uuid
import requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE}/api"

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CRON = {"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"}


def _login(email, password="User@123"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ------------ CITY GUIDES -------------

def test_every_city_has_an_editorial_guide():
    cities = requests.get(f"{API}/cities", timeout=15).json()["items"]
    assert len(cities) >= 27
    missing = []
    for c in cities:
        d = requests.get(f"{API}/cities/{c['slug']}", timeout=15).json()
        g = d.get("guide") or {}
        if not (g.get("intro") and g.get("areas") and g.get("when") and g.get("around") and g.get("tip")):
            missing.append(c["slug"])
            continue
        assert len(g["areas"]) >= 3, f"{c['slug']} has only {len(g['areas'])} areas"
        assert all(len(a) == 3 and a[0] and a[1] and a[2] for a in g["areas"]), c["slug"]
        assert len(g["intro"]) > 80, f"{c['slug']} intro too thin for SEO"
    assert not missing, f"cities without a guide: {missing}"


def test_guide_content_is_city_specific():
    dubai = requests.get(f"{API}/cities/dubai", timeout=15).json()["guide"]
    london = requests.get(f"{API}/cities/london", timeout=15).json()["guide"]
    assert "Dubai Marina & JBR" in [a[0] for a in dubai["areas"]]
    assert "Soho" in [a[0] for a in london["areas"]]
    assert dubai["intro"] != london["intro"]


# ------------ CRON AUTH -------------

def test_cron_endpoints_require_the_shared_secret():
    for path in ("monthly-prize", "city-openings"):
        assert requests.post(f"{API}/cron/{path}", timeout=15).status_code == 401
        assert requests.post(f"{API}/cron/{path}", headers={"Authorization": "Bearer wrong"},
                             timeout=15).status_code == 401
        r = requests.post(f"{API}/cron/{path}", headers=CRON, timeout=15)
        assert r.status_code == 200 and r.json()["ok"] is True, r.text


# ------------ MONTHLY PRIZE -------------

def test_monthly_prize_awards_a_free_pass_and_is_idempotent():
    r = requests.post(f"{API}/cron/monthly-prize", headers=CRON, timeout=15)
    month = r.json()["month"]
    time.sleep(3)
    prizes = list(_db.prizes.find({"month": month}))
    assert len(prizes) == 1, f"expected exactly one prize for {month}, got {len(prizes)}"
    prize = prizes[0]
    assert prize["invites"] >= 1 and prize["name"].endswith(".")
    order = _db.orders.find_one({"_id": __import__("bson").ObjectId(prize["order_id"])})
    assert order and order["total"] == 0 and order["payment_status"] == "paid"
    assert order["gateway"] == "leaderboard_prize" and order["user_id"] == prize["user_id"]

    # winner + runners-up were told
    assert _db.notifications.count_documents({"user_id": prize["user_id"],
                                              "title": {"$regex": "won"}}) >= 1

    # running it again must not double-award
    requests.post(f"{API}/cron/monthly-prize", headers=CRON, timeout=15)
    time.sleep(2)
    assert _db.prizes.count_documents({"month": month}) == 1
    assert _db.orders.count_documents({"gateway": "leaderboard_prize", "prize_month": month}) == 1


def test_leaderboard_announces_the_champion_and_the_prize():
    h = _login("tara.joshi@example.com")
    d = requests.get(f"{API}/referrals/leaderboard", headers=h, timeout=15).json()
    assert d["prize"], "leaderboard should say what the winner gets"
    champ = d["champion"]
    assert champ, "no champion announced — run POST /api/cron/monthly-prize"
    assert champ["invites"] >= 1 and champ["name"].endswith(".")
    assert len(champ["month"]) == 7 and champ["month_label"]
    assert champ["prize"]


# ------------ CITY OPENING EMAILS -------------

def _poll(fn, seconds=20):
    for _ in range(seconds * 2):
        val = fn()
        if val:
            return val
        time.sleep(0.5)
    return None


def _run_cron(path):
    for _ in range(5):
        r = requests.post(f"{API}/cron/{path}", headers=CRON, timeout=15)
        if r.status_code == 200:
            return r.json()
        time.sleep(2)          # shared preview backend rate-limits bursts
    raise AssertionError(f"cron/{path} never accepted: {r.status_code} {r.text}")


def test_waitlist_is_emailed_only_once_a_city_is_live():
    sleepy = f"test_wait_{uuid.uuid4().hex[:8]}@example.com"   # Vancouver: no events yet
    live = f"test_live_{uuid.uuid4().hex[:8]}@example.com"     # Dubai: already live
    try:
        r = requests.post(f"{API}/cities/vancouver/waitlist", json={"email": sleepy}, timeout=15)
        assert r.status_code == 200 and r.json()["live"] is False

        r = requests.post(f"{API}/cities/dubai/waitlist", json={"email": live}, timeout=15)
        assert r.status_code == 200 and r.json()["live"] is True
        assert "already live" in r.json()["message"]

        _run_cron("city-openings")
        opened = _poll(lambda: (_db.city_waitlist.find_one({"email": live}) or {}).get("notified_at"))
        assert opened, "a live city should have emailed its waitlist"
        assert not (_db.city_waitlist.find_one({"email": sleepy}) or {}).get("notified_at"), \
            "a closed city must not email its waitlist"

        # second run must not email the same person twice
        _run_cron("city-openings")
        time.sleep(3)
        assert _db.city_waitlist.find_one({"email": live})["notified_at"] == opened
    finally:
        _db.city_waitlist.delete_many({"email": {"$in": [sleepy, live]}})
