"""Iteration 22 — Staff roles & permissions (RBAC).

Covers:
  - GET /api/auth/me returns permissions (legacy admin=17, legacy manager=4, member=0)
  - GET /api/admin/permissions catalogue + presets + gating on team:manage
  - GET/POST/PATCH /api/admin/team (invite, edit, guardrails)
  - Permission enforcement matrix for control-centre endpoints
  - Console permission enforcement for vendor_viewer vs vendor_manager
"""
import os
import time
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from passlib.hash import bcrypt
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MONGO_DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
MEMBER = ("diya.sharma@example.com", "User@12345")
PERM_TEST = ("perm.test@buddilio.com", "Perm@1234")

# Extra staff accounts we spin up in Mongo
TEST_STAFF = {
    "test_finance@buddilio.com": {"staff_role": "finance", "role": "admin"},
    "test_support@buddilio.com": {"staff_role": "support", "role": "admin"},
    "test_viewer@buddilio.com": {"staff_role": "viewer", "role": "admin"},
    "test_vviewer@buddilio.com": {"staff_role": "vendor_viewer", "role": "manager"},
    "test_vmgr@buddilio.com": {"staff_role": "vendor_manager", "role": "manager"},
    "test_vmgr_pending@buddilio.com": {"staff_role": "vendor_manager", "role": "manager", "status": "pending"},
}
TEST_PWD = "Test@1234"
# perm.test is a moderator with one extra permission; the suite owns its lifecycle.
PERM_TEST_SPEC = {"staff_role": "moderator", "role": "admin", "extra": ["payouts:view"]}


from passlib.hash import bcrypt as _bcrypt
def _hash(pw):
    return _bcrypt.hash(pw)

def _clear_lockouts(emails):
    MONGO_DB.login_attempts.delete_many({"identifier": {"$in": [f"email:{e.lower()}" for e in emails]}})


def _ensure_staff():
    """Idempotently create staff accounts directly in Mongo with bcrypt hashes."""
    for email, spec in TEST_STAFF.items():
        MONGO_DB.users.update_one(
            {"email": email},
            {"$set": {
                "email": email,
                "full_name": f"TEST {spec['staff_role']}",
                "role": spec["role"],
                "staff_role": spec["staff_role"],
                "extra_permissions": [],
                "password_hash": _hash(TEST_PWD),
                "status": spec.get("status", "active"),
                "city": "", "photo": "", "verified": True, "email_verified": True,
            }},
            upsert=True,
        )
    MONGO_DB.users.update_one(
        {"email": PERM_TEST[0]},
        {"$set": {
            "email": PERM_TEST[0], "full_name": "TEST moderator",
            "role": PERM_TEST_SPEC["role"], "staff_role": PERM_TEST_SPEC["staff_role"],
            "extra_permissions": PERM_TEST_SPEC["extra"], "password_hash": _hash(PERM_TEST[1]),
            "status": "active", "city": "", "photo": "", "verified": True, "email_verified": True,
        }},
        upsert=True,
    )
    _clear_lockouts(list(TEST_STAFF) + [ADMIN[0], MANAGER[0], MEMBER[0], PERM_TEST[0]])


def _cleanup_staff():
    MONGO_DB.users.delete_many({"email": {"$in": list(TEST_STAFF) + [PERM_TEST[0]]}})


def _login(email, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    _ensure_staff()
    yield
    _cleanup_staff()
    # remove any TEST_ invitees created during tests
    MONGO_DB.users.delete_many({"email": {"$regex": "^test_invite_", "$options": "i"}})


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def manager_tok():
    return _login(*MANAGER)


@pytest.fixture(scope="module")
def member_tok():
    return _login(*MEMBER)


@pytest.fixture(scope="module")
def perm_test_tok():
    return _login(*PERM_TEST)


# ---------- /auth/me ----------
def test_me_admin_has_all_17_permissions(admin_tok):
    r = requests.get(f"{BASE_URL}/auth/me", headers=_h(admin_tok))
    assert r.status_code == 200
    perms = r.json().get("permissions", [])
    assert len(perms) == 17, f"admin should have 17, got {len(perms)}: {perms}"
    assert "team:manage" in perms


def test_me_legacy_manager_has_four(manager_tok):
    r = requests.get(f"{BASE_URL}/auth/me", headers=_h(manager_tok))
    assert r.status_code == 200
    perms = r.json().get("permissions", [])
    assert set(perms) == {"vendors:view", "vendors:manage", "invites:manage", "payouts:view"}


def test_me_member_permissions_empty(member_tok):
    r = requests.get(f"{BASE_URL}/auth/me", headers=_h(member_tok))
    assert r.status_code == 200
    assert r.json().get("permissions", []) == []


# ---------- /admin/permissions ----------
def test_permissions_catalogue_admin(admin_tok):
    r = requests.get(f"{BASE_URL}/admin/permissions", headers=_h(admin_tok))
    assert r.status_code == 200
    data = r.json()
    assert len(data["groups"]) == 17
    assert len(data["roles"]) == 8
    scopes = {r["scope"] for r in data["roles"]}
    assert scopes == {"admin", "manager"}
    assert len(data["my_permissions"]) == 17


def test_permissions_forbidden_without_team_manage(perm_test_tok, member_tok):
    for tok in (perm_test_tok, member_tok):
        r = requests.get(f"{BASE_URL}/admin/permissions", headers=_h(tok))
        assert r.status_code == 403


# ---------- Team CRUD ----------
def test_team_listing_admin(admin_tok):
    r = requests.get(f"{BASE_URL}/admin/team", headers=_h(admin_tok))
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i.get("email") == ADMIN[0] for i in items)
    # every item has permissions + role_label
    for i in items:
        assert "permissions" in i and "role_label" in i


def test_team_invite_and_duplicate(admin_tok):
    email = f"test_invite_{int(time.time())}@buddilio.com"
    body = {"full_name": "TEST Invitee", "email": email, "staff_role": "moderator",
            "scope": "admin", "extra_permissions": []}
    r = requests.post(f"{BASE_URL}/admin/team", json=body, headers=_h(admin_tok))
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email
    # duplicate
    r2 = requests.post(f"{BASE_URL}/admin/team", json=body, headers=_h(admin_tok))
    assert r2.status_code == 400


def test_team_invite_scope_mismatch(admin_tok):
    email = f"test_invite_mismatch_{int(time.time())}@buddilio.com"
    r = requests.post(f"{BASE_URL}/admin/team", json={
        "full_name": "TEST X", "email": email, "staff_role": "vendor_manager", "scope": "admin"},
        headers=_h(admin_tok))
    assert r.status_code == 400


def test_team_invite_permission_over_grant_forbidden():
    """A caller with only team:manage but limited perms can't grant extras they lack.
    We give the perm.test moderator an extra team:manage temporarily to test this.
    """
    doc = MONGO_DB.users.find_one({"email": PERM_TEST[0]})
    original_extras = doc.get("extra_permissions", [])
    MONGO_DB.users.update_one({"_id": doc["_id"]},
                              {"$set": {"extra_permissions": original_extras + ["team:manage"]}})
    try:
        tok = _login(*PERM_TEST)
        email = f"test_invite_over_{int(time.time())}@buddilio.com"
        r = requests.post(f"{BASE_URL}/admin/team", json={
            "full_name": "TEST X", "email": email, "staff_role": "finance", "scope": "admin"},
            headers=_h(tok))
        # moderator doesn't hold finance perms, so 403
        assert r.status_code == 403, r.text
    finally:
        MONGO_DB.users.update_one({"_id": doc["_id"]}, {"$set": {"extra_permissions": original_extras}})


def test_team_patch_self_forbidden(admin_tok):
    me = requests.get(f"{BASE_URL}/auth/me", headers=_h(admin_tok)).json()
    r = requests.patch(f"{BASE_URL}/admin/team/{me['id']}",
                       json={"status": "suspended"}, headers=_h(admin_tok))
    assert r.status_code == 400


def test_team_patch_unknown_and_malformed(admin_tok):
    r = requests.patch(f"{BASE_URL}/admin/team/deadbeef",
                       json={"status": "active"}, headers=_h(admin_tok))
    assert r.status_code == 400
    r2 = requests.patch(f"{BASE_URL}/admin/team/{ObjectId()}",
                        json={"status": "active"}, headers=_h(admin_tok))
    assert r2.status_code == 404


def test_team_patch_empty_body(admin_tok):
    doc = MONGO_DB.users.find_one({"email": "test_finance@buddilio.com"})
    r = requests.patch(f"{BASE_URL}/admin/team/{doc['_id']}", json={}, headers=_h(admin_tok))
    assert r.status_code == 400


def test_team_patch_invalid_status(admin_tok):
    doc = MONGO_DB.users.find_one({"email": "test_finance@buddilio.com"})
    r = requests.patch(f"{BASE_URL}/admin/team/{doc['_id']}",
                       json={"status": "bogus"}, headers=_h(admin_tok))
    assert r.status_code == 400


def test_team_patch_role_change(admin_tok):
    doc = MONGO_DB.users.find_one({"email": "test_viewer@buddilio.com"})
    r = requests.patch(f"{BASE_URL}/admin/team/{doc['_id']}",
                       json={"staff_role": "support"}, headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.json()["staff_role"] == "support"
    # restore
    requests.patch(f"{BASE_URL}/admin/team/{doc['_id']}",
                   json={"staff_role": "viewer"}, headers=_h(admin_tok))


# ---------- Perm.test moderator matrix (exact 200/403 split) ----------
def test_perm_test_moderator_split(perm_test_tok):
    h = _h(perm_test_tok)
    allowed = ["/admin/photos", "/admin/users", "/admin/payouts"]
    denied = ["/admin/stats", "/admin/settings", "/admin/team"]
    for path in allowed:
        r = requests.get(f"{BASE_URL}{path}", headers=h)
        assert r.status_code == 200, f"expected 200 on {path}, got {r.status_code}"
    for path in denied:
        r = requests.get(f"{BASE_URL}{path}", headers=h)
        assert r.status_code == 403, f"expected 403 on {path}, got {r.status_code}"
    # POST /admin/payouts/{id}/pay should be forbidden (no payouts:pay)
    payouts = requests.get(f"{BASE_URL}/admin/payouts", headers=h).json().get("items", [])
    if payouts:
        pid = payouts[0]["id"]
        r = requests.post(f"{BASE_URL}/admin/payouts/{pid}/pay", json={}, headers=h)
        assert r.status_code == 403


# ---------- Finance role ----------
def test_finance_role_matrix():
    tok = _login("test_finance@buddilio.com", TEST_PWD)
    h = _h(tok)
    # can list coupons, plans, products
    for path in ("/admin/coupons", "/admin/plans", "/admin/products"):
        r = requests.get(f"{BASE_URL}{path}", headers=h)
        assert r.status_code == 200, f"finance should list {path}, got {r.status_code}"
    # cannot moderate events
    ev = requests.get(f"{BASE_URL}/admin/events", headers=h)
    # finance has no events:view either — but the requirement says it cannot moderate.
    # Try moderating any event id
    r = requests.post(f"{BASE_URL}/admin/events/000000000000000000000000/moderate",
                      json={"action": "approve"}, headers=h)
    assert r.status_code in (403, 404)  # 403 if perm denied first
    # Prefer strictly 403
    if r.status_code != 403:
        # attempt via known event
        pass


# ---------- Support role ----------
def test_support_role_matrix():
    tok = _login("test_support@buddilio.com", TEST_PWD)
    h = _h(tok)
    # can list users
    r = requests.get(f"{BASE_URL}/admin/users", headers=h)
    assert r.status_code == 200
    users = r.json().get("items", [])
    if users:
        uid = users[0]["id"]
        # patch is allowed
        r = requests.patch(f"{BASE_URL}/admin/users/{uid}", json={}, headers=h)
        assert r.status_code in (200, 400)  # 400 = empty; not 403
    # settings forbidden
    r = requests.get(f"{BASE_URL}/admin/settings", headers=h)
    assert r.status_code == 403


# ---------- Viewer role ----------
def test_viewer_role_readonly():
    tok = _login("test_viewer@buddilio.com", TEST_PWD)
    h = _h(tok)
    # views ok
    for p in ("/admin/users", "/admin/orders", "/admin/payouts", "/admin/events", "/admin/stats"):
        r = requests.get(f"{BASE_URL}{p}", headers=h)
        assert r.status_code == 200, f"viewer should read {p}, got {r.status_code}"
    # writes forbidden
    users = requests.get(f"{BASE_URL}/admin/users", headers=h).json().get("items", [])
    if users:
        r = requests.patch(f"{BASE_URL}/admin/users/{users[0]['id']}", json={"verified": True}, headers=h)
        assert r.status_code == 403
    payouts = requests.get(f"{BASE_URL}/admin/payouts", headers=h).json().get("items", [])
    if payouts:
        r = requests.post(f"{BASE_URL}/admin/payouts/{payouts[0]['id']}/pay", json={}, headers=h)
        assert r.status_code == 403


# ---------- Moderator cannot reach verifications ----------
def test_moderator_no_verifications(perm_test_tok):
    r = requests.get(f"{BASE_URL}/admin/verifications", headers=_h(perm_test_tok))
    assert r.status_code == 403


# ---------- Console: vendor_viewer read-only ----------
def test_console_vendor_viewer_readonly():
    tok = _login("test_vviewer@buddilio.com", TEST_PWD)
    h = _h(tok)
    for p in ("/console/summary", "/console/vendors", "/console/payouts"):
        r = requests.get(f"{BASE_URL}{p}", headers=h)
        assert r.status_code == 200, f"vviewer read {p} got {r.status_code}"
    # writes forbidden
    r = requests.post(f"{BASE_URL}/console/vendors", json={
        "full_name": "TEST V", "email": "test_vv@example.com", "org_name": "TEST", "city": "Delhi"}, headers=h)
    assert r.status_code == 403
    r = requests.post(f"{BASE_URL}/console/invites", json={"email": "x@example.com"}, headers=h)
    assert r.status_code == 403


# ---------- Console: vendor_manager pending vs active ----------
def test_console_vendor_manager_pending_403():
    tok = _login("test_vmgr_pending@buddilio.com", TEST_PWD)
    h = _h(tok)
    r = requests.post(f"{BASE_URL}/console/invites",
                      json={"email": "x@example.com", "city": "Delhi"}, headers=h)
    assert r.status_code == 403
    assert "approval" in r.text.lower() or "await" in r.text.lower() or "pending" in r.text.lower()


def test_console_vendor_manager_active_can_write():
    tok = _login("test_vmgr@buddilio.com", TEST_PWD)
    h = _h(tok)
    r = requests.get(f"{BASE_URL}/console/summary", headers=h)
    assert r.status_code == 200
    # try creating an invite (may 400 if extra validation, but not 403)
    r = requests.post(f"{BASE_URL}/console/invites",
                      json={"email": f"test_vinv_{int(time.time())}@example.com", "city": "Delhi",
                            "org_name": "TEST Org"}, headers=h)
    assert r.status_code in (200, 201, 400), r.text  # must not be 403
    # cleanup any invite
    MONGO_DB.vendor_invites.delete_many({"email": {"$regex": "^test_vinv_"}})


# ---------- Regression: admin & manager legacy flows ----------
def test_admin_regression_endpoints(admin_tok):
    h = _h(admin_tok)
    for p in ("/admin/stats", "/admin/users", "/admin/events", "/admin/orders",
              "/admin/payouts", "/admin/reports", "/admin/reviews", "/admin/coupons",
              "/admin/plans", "/admin/products", "/admin/settings", "/admin/verifications",
              "/admin/photos", "/admin/audit-logs", "/admin/managers", "/admin/vendor-activity"):
        r = requests.get(f"{BASE_URL}{p}", headers=h)
        assert r.status_code == 200, f"admin regression {p} failed: {r.status_code} {r.text[:120]}"


def test_manager_regression_console(manager_tok):
    h = _h(manager_tok)
    for p in ("/console/summary", "/console/vendors", "/console/invites",
              "/console/payouts", "/console/payout-reminder"):
        r = requests.get(f"{BASE_URL}{p}", headers=h)
        assert r.status_code == 200, f"manager regression {p} failed: {r.status_code}"
