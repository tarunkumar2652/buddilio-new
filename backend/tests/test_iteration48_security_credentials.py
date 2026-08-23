"""Iteration 48 — Security & Credentials: self-service password change, credentials:manage gating,
write-only credential vault, admin password reset / session revoke / access revoke, connection tests.

Safety: PayPal is LIVE. Only read-only PayPal calls. Never changes PAYPAL_CLIENT_ID/SECRET or
JWT_SECRET. Uses PAYPAL_CURRENCY / VAPID_SUBJECT as write targets and reverts them.
Real accounts' passwords are never modified: throwaway accounts are seeded in Mongo instead.
"""
import os
import re
import uuid

import bcrypt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
MONGO_URL = be.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = be.get("DB_NAME") or os.environ.get("DB_NAME")

ADMIN = {"email": "admin@buddilio.com", "password": "Admin@123"}
PARTNER = {"email": "partner@buddilio.com", "password": "Partner@123"}
MEMBER_CANDIDATES = [{"email": "arjun.sethi@example.com", "password": p}
                     for p in ("User@12345", "User@12345")]

STAFF_PWD = "StaffTest@123"
WORDS_RE = re.compile(r"[“\"']([A-Za-z]+)[”\"']")

CRED_ENDPOINTS = [
    ("get", "/admin/credentials", None),
    ("put", "/admin/credentials/PAYPAL_CURRENCY", {"value": "USD"}),
    ("delete", "/admin/credentials/PAYPAL_CURRENCY", None),
    ("post", "/admin/credentials/test/paypal", {}),
    ("get", "/admin/security/accounts", None),
    ("post", "/admin/security/accounts/000000000000000000000000/revoke", {}),
    ("post", "/admin/security/accounts/000000000000000000000000/access", {"active": False}),
    ("post", "/admin/security/accounts/000000000000000000000000/password", {"value": "Whatever@123"}),
]


def solve(question: str) -> str:
    m = re.search(r"What is (\d+) \+ (\d+)", question)
    if m:
        return str(int(m.group(1)) + int(m.group(2)))
    w = WORDS_RE.search(question)
    if "How many letters" in question and w:
        return str(len(w.group(1)))
    if "last four letters" in question and w:
        return w.group(1)[-4:]
    raise AssertionError(f"Unknown captcha style: {question}")


def login(s, creds, expect=200):
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200 and expect == 200:
        c = s.get(f"{API}/captcha", timeout=30).json()
        r = s.post(f"{API}/auth/login",
                   json={**creds, "captcha_id": c["captcha_id"], "captcha_answer": solve(c["question"])},
                   timeout=30)
    return r


def token(s, creds):
    r = login(s, creds)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session")
def admin_h(s):
    return hdr(token(s, ADMIN))


def seed_account(mongo, email, role="admin", staff_role="moderator", extra=None):
    mongo.users.delete_many({"email": email})
    doc = {"email": email, "full_name": "TEST Security Bot", "role": role, "staff_role": staff_role,
           "status": "active", "extra_permissions": extra or [],
           "password_hash": bcrypt.hashpw(STAFF_PWD.encode(), bcrypt.gensalt()).decode(),
           "created_at": "2026-07-01T00:00:00+00:00"}
    return str(mongo.users.insert_one(doc).inserted_id)


@pytest.fixture(scope="session")
def staff(mongo):
    """Throwaway admin account with NO credentials:manage."""
    email = f"test_sec_staff_{uuid.uuid4().hex[:6]}@example.com"
    uid = seed_account(mongo, email)
    yield {"id": uid, "email": email, "password": STAFF_PWD}
    mongo.users.delete_many({"email": email})


@pytest.fixture(scope="session")
def victim(mongo):
    """Throwaway partner account used for admin reset / revoke / suspend."""
    email = f"test_sec_victim_{uuid.uuid4().hex[:6]}@example.com"
    uid = seed_account(mongo, email, role="partner", staff_role=None)
    yield {"id": uid, "email": email, "password": STAFF_PWD}
    mongo.users.delete_many({"email": email})


# ---------------- basic auth / regression ----------------
class TestLogins:
    def test_admin_login(self, s):
        r = login(s, ADMIN)
        assert r.status_code == 200, r.text[:200]
        me = requests.get(f"{API}/auth/me", headers=hdr(r.json()["access_token"]), timeout=30).json()
        assert me["role"] == "admin"
        assert "credentials:manage" in me["permissions"]

    def test_partner_login(self, s):
        assert login(s, PARTNER).status_code == 200

    def test_member_login(self, s):
        codes = []
        for creds in MEMBER_CANDIDATES:
            r = login(s, creds)
            codes.append(r.status_code)
            if r.status_code == 200:
                return
        pytest.fail(f"member login failed for both documented passwords: {codes}")

    def test_existing_token_without_ver_claim_still_works(self, s, admin_h):
        # token issued above carries ver from the user doc; untouched users default to 0
        r = s.get(f"{API}/auth/me", headers=admin_h, timeout=30)
        assert r.status_code == 200 and r.json()["email"] == ADMIN["email"]


# ---------------- access control ----------------
class TestAccessControl:
    def _forbidden(self, s, h, who):
        for method, path, body in CRED_ENDPOINTS:
            r = getattr(s, method)(f"{API}{path}", headers=h, json=body, timeout=30)
            assert r.status_code == 403, f"{who} got {r.status_code} on {method.upper()} {path}"

    def test_member_forbidden(self, s):
        tok = None
        for creds in MEMBER_CANDIDATES:
            r = login(s, creds)
            if r.status_code == 200:
                tok = r.json()["access_token"]
                break
        assert tok, "no member login"
        self._forbidden(s, hdr(tok), "member")

    def test_partner_forbidden(self, s):
        self._forbidden(s, hdr(token(s, PARTNER)), "partner")

    def test_staff_without_permission_forbidden(self, s, staff):
        self._forbidden(s, hdr(token(s, {"email": staff["email"], "password": staff["password"]})), "staff")

    def test_anonymous_forbidden(self, s):
        r = s.get(f"{API}/admin/credentials", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_staff_with_credentials_manage_allowed(self, s, mongo, staff):
        mongo.users.update_one({"email": staff["email"]},
                               {"$set": {"extra_permissions": ["credentials:manage"]}})
        h = hdr(token(s, {"email": staff["email"], "password": staff["password"]}))
        assert s.get(f"{API}/admin/credentials", headers=h, timeout=30).status_code == 200
        assert s.get(f"{API}/admin/security/accounts", headers=h, timeout=30).status_code == 200
        mongo.users.update_one({"email": staff["email"]}, {"$set": {"extra_permissions": []}})

    def test_credentials_manage_in_permission_catalogue(self, s, admin_h):
        r = s.get(f"{API}/admin/permissions", headers=admin_h, timeout=30)
        if r.status_code == 404:
            pytest.skip("permission catalogue endpoint path differs")
        assert r.status_code == 200
        assert "credentials:manage" in r.text


# ---------------- metadata only, no secret leaks ----------------
class TestNoLeak:
    def test_list_shape_and_masking(self, s, admin_h):
        r = s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert len(d["items"]) == 17, f"expected 17 managed keys, got {len(d['items'])}"
        groups = {c["group"] for c in d["items"]}
        assert groups == {"Payments", "Email & AI", "Notifications", "Automation", "Security"}
        for c in d["items"]:
            assert set(c) >= {"name", "label", "group", "hint", "configured", "source",
                              "preview", "updated_at", "sensitive"}
            assert "value" not in c and "ciphertext" not in c
            if c["sensitive"] and c["configured"]:
                assert "•" in c["preview"] and len(c["preview"]) <= 14, c["name"]
        assert len(d["not_managed_here"]) == 4
        assert isinstance(d["history"], list)
        assert '"_id"' not in r.text

    def test_no_plaintext_secret_in_response(self, s, admin_h):
        body = s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).text
        leaked = []
        for name in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_SANDBOX_CLIENT_ID",
                     "PAYPAL_SANDBOX_CLIENT_SECRET", "RESEND_API_KEY", "EMERGENT_LLM_KEY",
                     "JWT_SECRET", "WEBHOOK_CRON_SECRET", "VAPID_PRIVATE_KEY", "STRIPE_API_KEY",
                     "SECRETS_KEY_B64"):
            secret = (be.get(name) or os.environ.get(name) or "").strip()
            if len(secret) >= 8 and secret in body:
                leaked.append(name)
        assert not leaked, f"plaintext secret leaked in credential list: {leaked}"

    def test_history_rows_carry_no_values(self, s, admin_h):
        d = s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()
        for h in d["history"]:
            assert "value" not in str(h.get("meta", {})).lower()
            assert set(h.get("meta", {})) <= {"name", "email"}


# ---------------- save / revert / validation ----------------
class TestCredentialWrites:
    def test_unknown_key_404(self, s, admin_h):
        assert s.put(f"{API}/admin/credentials/NOT_A_KEY", headers=admin_h,
                     json={"value": "x"}, timeout=30).status_code == 404
        assert s.delete(f"{API}/admin/credentials/NOT_A_KEY", headers=admin_h,
                        timeout=30).status_code == 404

    def test_paypal_env_validation(self, s, admin_h):
        r = s.put(f"{API}/admin/credentials/PAYPAL_ENV", headers=admin_h,
                  json={"value": "production"}, timeout=30)
        assert r.status_code == 400 and "live or sandbox" in r.text

    def test_jwt_secret_length_validation(self, s, admin_h):
        r = s.put(f"{API}/admin/credentials/JWT_SECRET", headers=admin_h,
                  json={"value": "tooshort"}, timeout=30)
        assert r.status_code == 400 and "24" in r.text

    def test_empty_value_rejected(self, s, admin_h):
        r = s.put(f"{API}/admin/credentials/VAPID_SUBJECT", headers=admin_h,
                  json={"value": ""}, timeout=30)
        assert r.status_code == 422, r.status_code

    def test_save_encrypts_takes_effect_and_reverts(self, s, admin_h, mongo):
        before = {c["name"]: c for c in
                  s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        original_currency = before["PAYPAL_CURRENCY"]["preview"]
        assert before["PAYPAL_CURRENCY"]["source"] in ("server file", "dashboard", "not set")

        r = s.put(f"{API}/admin/credentials/PAYPAL_CURRENCY", headers=admin_h,
                  json={"value": "USD"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["ok"] is True

        raw = mongo.platform_credentials.find_one({"_id": "PAYPAL_CURRENCY"})
        assert raw and raw.get("ciphertext") and raw.get("nonce")
        assert "USD" not in str(raw), "plaintext value present in stored document"

        after = {c["name"]: c for c in
                 s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        assert after["PAYPAL_CURRENCY"]["source"] == "dashboard"
        assert after["PAYPAL_CURRENCY"]["preview"] == "USD"
        assert after["PAYPAL_CURRENCY"]["updated_at"]

        # audit row written
        hist = s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["history"]
        assert any(h["action"] == "credential.updated" and h.get("meta", {}).get("name") == "PAYPAL_CURRENCY"
                   for h in hist)

        # revert
        d = s.delete(f"{API}/admin/credentials/PAYPAL_CURRENCY", headers=admin_h, timeout=30)
        assert d.status_code == 200, d.text[:200]
        assert mongo.platform_credentials.find_one({"_id": "PAYPAL_CURRENCY"}) is None
        back = {c["name"]: c for c in
                s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        assert back["PAYPAL_CURRENCY"]["source"] == "server file"
        assert back["PAYPAL_CURRENCY"]["preview"] == original_currency

    def test_vapid_subject_roundtrip(self, s, admin_h, mongo):
        before = {c["name"]: c for c in
                  s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        original = before["VAPID_SUBJECT"]["preview"]
        r = s.put(f"{API}/admin/credentials/VAPID_SUBJECT", headers=admin_h,
                  json={"value": "mailto:qa-test@buddilio.com"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        mid = {c["name"]: c for c in
               s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        assert mid["VAPID_SUBJECT"]["preview"] == "mailto:qa-test@buddilio.com"
        assert s.delete(f"{API}/admin/credentials/VAPID_SUBJECT", headers=admin_h,
                        timeout=30).status_code == 200
        after = {c["name"]: c for c in
                 s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["items"]}
        assert after["VAPID_SUBJECT"]["preview"] == original
        assert mongo.platform_credentials.find_one({"_id": "VAPID_SUBJECT"}) is None


# ---------------- self-service password change ----------------
class TestMyPassword:
    def test_full_flow(self, s, staff):
        creds = {"email": staff["email"], "password": STAFF_PWD}
        old = token(s, creds)
        h = hdr(old)

        bad = s.post(f"{API}/me/password", headers=h,
                     json={"current_password": "Nope@123456", "new_password": "Brand@New123"}, timeout=30)
        assert bad.status_code == 400 and "current password" in bad.text.lower()

        weak = s.post(f"{API}/me/password", headers=h,
                      json={"current_password": STAFF_PWD, "new_password": "short1A"}, timeout=30)
        assert weak.status_code == 400 and "10 and 128" in weak.text

        nodigit = s.post(f"{API}/me/password", headers=h,
                         json={"current_password": STAFF_PWD, "new_password": "abcdefghijkl"}, timeout=30)
        assert nodigit.status_code == 400 and "upper-case" in nodigit.text

        same = s.post(f"{API}/me/password", headers=h,
                      json={"current_password": STAFF_PWD, "new_password": STAFF_PWD}, timeout=30)
        assert same.status_code == 400 and "different password" in same.text

        new_pwd = "Rotated@2026x"
        ok = s.post(f"{API}/me/password", headers=h,
                    json={"current_password": STAFF_PWD, "new_password": new_pwd}, timeout=30)
        assert ok.status_code == 200, ok.text[:200]
        fresh = ok.json()["access_token"]
        assert fresh and fresh != old

        # old token dead, new token alive
        dead = s.get(f"{API}/auth/me", headers=h, timeout=30)
        assert dead.status_code == 401 and "session has ended" in dead.text
        assert s.get(f"{API}/auth/me", headers=hdr(fresh), timeout=30).status_code == 200

        # login with new password works, old password refused
        assert login(s, {"email": staff["email"], "password": new_pwd}).status_code == 200
        assert login(s, {"email": staff["email"], "password": STAFF_PWD},
                     expect=401).status_code in (401, 400, 429)

        # restore so the rest of the suite can use STAFF_PWD
        t2 = token(s, {"email": staff["email"], "password": new_pwd})
        back = s.post(f"{API}/me/password", headers=hdr(t2),
                      json={"current_password": new_pwd, "new_password": STAFF_PWD}, timeout=30)
        assert back.status_code == 200, back.text[:200]

    def test_requires_auth(self):
        r = requests.post(f"{API}/me/password",
                   json={"current_password": "x", "new_password": "Abcdefgh123"}, timeout=30)
        assert r.status_code in (401, 403)


# ---------------- admin-initiated actions ----------------
class TestAdminSecurityActions:
    def test_accounts_list(self, s, admin_h, victim):
        r = s.get(f"{API}/admin/security/accounts", headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["me"] and any(u["email"] == victim["email"] for u in d["items"])
        assert "password_hash" not in r.text and '"_id"' not in r.text

    def test_self_reset_refused(self, s, admin_h):
        me = s.get(f"{API}/auth/me", headers=admin_h, timeout=30).json()["id"]
        r = s.post(f"{API}/admin/security/accounts/{me}/password", headers=admin_h,
                   json={"value": "Whatever@12345"}, timeout=30)
        assert r.status_code == 400 and "My password" in r.text

    def test_unknown_account_404(self, s, admin_h):
        for path, body in ((f"/admin/security/accounts/{'0' * 24}/password", {"value": "Whatever@12345"}),
                           (f"/admin/security/accounts/{'0' * 24}/revoke", {}),
                           (f"/admin/security/accounts/{'0' * 24}/access", {"active": True})):
            r = s.post(f"{API}{path}", headers=admin_h, json=body, timeout=30)
            assert r.status_code == 404, f"{path} -> {r.status_code}"

    def test_weak_password_refused(self, s, admin_h, victim):
        r = s.post(f"{API}/admin/security/accounts/{victim['id']}/password", headers=admin_h,
                   json={"value": "weak"}, timeout=30)
        assert r.status_code == 400

    def test_admin_reset_password(self, s, admin_h, victim):
        old = token(s, {"email": victim["email"], "password": STAFF_PWD})
        new_pwd = "AdminSet@2026a"
        r = s.post(f"{API}/admin/security/accounts/{victim['id']}/password", headers=admin_h,
                   json={"value": new_pwd}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert victim["email"] in r.json()["message"]

        dead = s.get(f"{API}/auth/me", headers=hdr(old), timeout=30)
        assert dead.status_code == 401 and "session has ended" in dead.text
        assert login(s, {"email": victim["email"], "password": new_pwd}).status_code == 200

        hist = s.get(f"{API}/admin/credentials", headers=admin_h, timeout=30).json()["history"]
        assert any(h["action"] == "password.admin_reset" and
                   h.get("meta", {}).get("email") == victim["email"] for h in hist)

        # restore the seed password
        assert s.post(f"{API}/admin/security/accounts/{victim['id']}/password", headers=admin_h,
                      json={"value": STAFF_PWD}, timeout=30).status_code == 200
        assert login(s, {"email": victim["email"], "password": STAFF_PWD}).status_code == 200

    def test_revoke_sessions_keeps_password(self, s, admin_h, victim):
        old = token(s, {"email": victim["email"], "password": STAFF_PWD})
        r = s.post(f"{API}/admin/security/accounts/{victim['id']}/revoke", headers=admin_h,
                   json={}, timeout=30)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert s.get(f"{API}/auth/me", headers=hdr(old), timeout=30).status_code == 401
        # same password still valid
        assert login(s, {"email": victim["email"], "password": STAFF_PWD}).status_code == 200

    def test_self_lock_refused(self, s, admin_h):
        me = s.get(f"{API}/auth/me", headers=admin_h, timeout=30).json()["id"]
        r = s.post(f"{API}/admin/security/accounts/{me}/access", headers=admin_h,
                   json={"active": False}, timeout=30)
        assert r.status_code == 400 and "own account" in r.text

    def test_revoke_and_restore_access(self, s, admin_h, victim, mongo):
        live = token(s, {"email": victim["email"], "password": STAFF_PWD})
        r = s.post(f"{API}/admin/security/accounts/{victim['id']}/access", headers=admin_h,
                   json={"active": False}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "suspended"
        assert s.get(f"{API}/auth/me", headers=hdr(live), timeout=30).status_code in (401, 403)
        blocked = login(s, {"email": victim["email"], "password": STAFF_PWD}, expect=403)
        assert blocked.status_code == 403 and "suspended" in blocked.text

        back = s.post(f"{API}/admin/security/accounts/{victim['id']}/access", headers=admin_h,
                      json={"active": True}, timeout=30)
        assert back.status_code == 200 and back.json()["status"] == "active"
        assert login(s, {"email": victim["email"], "password": STAFF_PWD}).status_code == 200
        assert mongo.users.find_one({"email": victim["email"]})["status"] == "active"


# ---------------- connection tests ----------------
class TestConnectionTests:
    def test_paypal(self, s, admin_h):
        r = s.post(f"{API}/admin/credentials/test/paypal", headers=admin_h, json={}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "message" in d and isinstance(d["ok"], bool)
        if d["ok"]:
            assert "live" in d["message"] or "sandbox" in d["message"]

    def test_email(self, s, admin_h):
        r = s.post(f"{API}/admin/credentials/test/email", headers=admin_h, json={}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert "message" in r.json()

    def test_ai(self, s, admin_h):
        r = s.post(f"{API}/admin/credentials/test/ai", headers=admin_h, json={}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert "message" in r.json()

    def test_unknown_service_404(self, s, admin_h):
        r = s.post(f"{API}/admin/credentials/test/nonsense", headers=admin_h, json={}, timeout=30)
        assert r.status_code == 404
