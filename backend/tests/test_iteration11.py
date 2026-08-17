"""Iteration 11: Emergent Google sign-in + /welcome onboarding backend coverage.

Covers:
- POST /api/auth/google/session with bogus session_id -> 401 (no user created).
- POST /api/auth/onboarding: 21+ gate, missing terms, empty city, auth required, success cleans user.
- Regressions: password login (admin + member), /auth/me, register (21+), forgot-password,
  and existing users are NOT forced into onboarding (profile_complete not falsely false).
"""
import os
import asyncio
import secrets
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://lifestyle-connect-17.preview.emergentagent.com"
# Read the same URL the frontend uses
_fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
if _fe_env.exists():
    for line in _fe_env.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Google session ----------
class TestGoogleSession:
    def test_bogus_session_id_returns_401_no_user(self, s, db):
        bogus = f"bogus-session-{secrets.token_hex(8)}"
        before = db.users.count_documents({})
        r = s.post(f"{API}/auth/google/session", json={"session_id": bogus, "referral_code": ""})
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
        body = r.json()
        assert "detail" in body
        assert "expired" in body["detail"].lower() or "google" in body["detail"].lower()
        # No user created
        after = db.users.count_documents({})
        assert after == before, f"user count changed from {before} to {after}"

    def test_missing_session_id_returns_422(self, s):
        r = s.post(f"{API}/auth/google/session", json={})
        assert r.status_code in (400, 422)


# ---------- Onboarding ----------
@pytest.fixture(scope="module")
def google_user_token(db):
    """Insert a fresh google-style user w/ profile_complete=False and return a JWT."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import server  # type: ignore

    email = f"test.google.{secrets.token_hex(4)}@example.com"
    doc = {
        "full_name": "TEST Google User",
        "email": email,
        "role": "user",
        "status": "active",
        "profile_complete": False,
        "auth_provider": "google",
        "password_hash": "",
        "age": 0,
        "city": "",
        "notification_prefs": {"email": True, "in_app": True},
        "created_at": server.iso(server.now_utc()),
    }

    async def _mk():
        r = await server.db.users.insert_one(doc)
        return str(r.inserted_id), server.create_access_token(str(r.inserted_id), email, "user")

    uid, token = asyncio.get_event_loop().run_until_complete(_mk()) if not asyncio.get_event_loop().is_running() else asyncio.run(_mk())
    yield {"id": uid, "email": email, "token": token}
    # cleanup
    db.users.delete_one({"_id": ObjectId(uid)})


class TestOnboarding:
    def test_requires_auth(self, s):
        r = s.post(f"{API}/auth/onboarding", json={
            "dob": "1990-01-01", "city": "London", "is_adult": True, "accept_terms": True
        })
        assert r.status_code == 401

    def test_under_21_rejected(self, s, google_user_token):
        h = {"Authorization": f"Bearer {google_user_token['token']}"}
        r = s.post(f"{API}/auth/onboarding", headers=h, json={
            "dob": "2010-01-01", "city": "London", "is_adult": True, "accept_terms": True
        })
        assert r.status_code == 400
        assert "21" in r.json().get("detail", "")

    def test_missing_is_adult_rejected(self, s, google_user_token):
        h = {"Authorization": f"Bearer {google_user_token['token']}"}
        r = s.post(f"{API}/auth/onboarding", headers=h, json={
            "dob": "1990-01-01", "city": "London", "is_adult": False, "accept_terms": True
        })
        assert r.status_code == 400

    def test_missing_accept_terms_rejected(self, s, google_user_token):
        h = {"Authorization": f"Bearer {google_user_token['token']}"}
        r = s.post(f"{API}/auth/onboarding", headers=h, json={
            "dob": "1990-01-01", "city": "London", "is_adult": True, "accept_terms": False
        })
        assert r.status_code == 400

    def test_empty_city_rejected(self, s, google_user_token):
        h = {"Authorization": f"Bearer {google_user_token['token']}"}
        r = s.post(f"{API}/auth/onboarding", headers=h, json={
            "dob": "1990-01-01", "city": "   ", "is_adult": True, "accept_terms": True
        })
        assert r.status_code == 400

    def test_success_sets_fields_and_cleans(self, s, google_user_token, db):
        h = {"Authorization": f"Bearer {google_user_token['token']}"}
        r = s.post(f"{API}/auth/onboarding", headers=h, json={
            "dob": "1994-05-01", "city": "London", "gender": "female",
            "is_adult": True, "accept_terms": True, "interests": ["Music"]
        })
        assert r.status_code == 200, r.text
        body = r.json()
        # cleaned - no password_hash or _id
        assert "password_hash" not in body
        assert "_id" not in body
        assert body.get("profile_complete") is True
        assert body.get("city") == "London"
        assert body.get("country") == "United Kingdom"
        assert body.get("country_code") == "GB"
        assert isinstance(body.get("age"), int) and body["age"] >= 21
        # DB verification
        u = db.users.find_one({"_id": ObjectId(google_user_token["id"])})
        assert u["profile_complete"] is True
        assert u["country_code"] == "GB"


# ---------- Password auth regressions ----------
class TestPasswordAuthRegression:
    def test_admin_login_and_me(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "admin@buddilio.com", "password": "Admin@123"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert body["user"]["role"] == "admin"
        assert "password_hash" not in body["user"]
        token = body["access_token"]
        me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "admin@buddilio.com"

    def test_member_login(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "diya.sharma@example.com", "password": "User@123"})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["role"] == "user"

    def test_member_profile_complete_not_false(self, s):
        """Existing seeded members must NOT be forced into onboarding."""
        r = s.post(f"{API}/auth/login", json={"email": "diya.sharma@example.com", "password": "User@123"})
        assert r.status_code == 200
        u = r.json()["user"]
        # Either profile_complete is True or the key is absent (not falsy-forcing to /welcome).
        # The Protected component checks explicitly === false, so absence is fine, false is NOT.
        assert u.get("profile_complete") is not False, f"seeded user forced to onboarding: {u.get('profile_complete')}"

    def test_admin_profile_complete_not_false(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "admin@buddilio.com", "password": "Admin@123"})
        u = r.json()["user"]
        assert u.get("profile_complete") is not False

    def test_register_21plus_enforced(self, s, db):
        email = f"test_reg_{secrets.token_hex(4)}@example.com"
        r = s.post(f"{API}/auth/register", json={
            "full_name": "TEST Under Age", "email": email, "password": "TestPass1!",
            "mobile": "", "dob": "2010-01-01", "gender": "male", "city": "London",
            "is_adult": True, "accept_terms": True
        })
        assert r.status_code == 400
        assert "21" in r.json().get("detail", "")

    def test_register_success(self, s, db):
        email = f"test_reg_{secrets.token_hex(4)}@example.com"
        try:
            r = s.post(f"{API}/auth/register", json={
                "full_name": "TEST New Member", "email": email, "password": "TestPass1!",
                "mobile": "+919876543210", "dob": "1994-05-01", "gender": "female", "city": "London",
                "is_adult": True, "accept_terms": True, "interests": ["Music"]
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert "access_token" in body
            assert body["user"]["email"] == email
            assert "password_hash" not in body["user"]
        finally:
            db.users.delete_one({"email": email})

    def test_forgot_password(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"email": "diya.sharma@example.com"})
        assert r.status_code == 200
        body = r.json()
        # generic ok response
        assert body.get("ok") is True or "detail" in body or "message" in body
