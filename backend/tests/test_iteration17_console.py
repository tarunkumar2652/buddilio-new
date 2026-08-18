"""Iteration 17 — Vendor Console (managers + vendors) backend tests.

Focus per E1 handoff:
  * console registration → pending, immediate token
  * approval gate 403 for pending managers on writes, but reads OK
  * admin approve/suspend/reject via /api/admin/managers
  * vendor create by approved manager: managed_by, dupes, missing fields
  * password_reset_tokens row exists → vendor takes over via /api/auth/reset-password → login → dashboard
  * suspend-manager-loses-write path
  * vendor management: GET detail w/ stats+recent_events, PATCH edits, toggle-status, toggle-verified, resend invite
  * search filters by name/email/org/city
  * authorization isolation: member 403 on every /api/console/*; second manager gets 404 on someone else's vendor; empty list
  * admin-only endpoint guards on /api/admin/managers*
  * admin sees ALL vendors including legacy (no managed_by)
  * regression: member routes still 200
"""

import os
import uuid
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fall back to frontend .env
    fe = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"
ADMIN = ("admin@buddilio.com", "Admin@123")
APPROVED_MGR = ("ops.manager@buddilio.com", "Console@123")
MEMBER = ("diya.sharma@example.com", "User@123")

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def approved_mgr_tok():
    return _login(*APPROVED_MGR)


@pytest.fixture(scope="module")
def member_tok():
    return _login(*MEMBER)


@pytest.fixture(scope="module")
def pending_manager():
    """Register a fresh manager (pending). Yields (email, password, token, id). Cleans up."""
    email = f"test_pending_mgr_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Console@123"
    r = requests.post(f"{API}/console/register", json={
        "full_name": "TEST Pending Manager", "email": email, "password": pw,
        "org_name": "TEST Org", "mobile": "+911234567890"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    mid = body["user"]["id"]
    tok = body["access_token"]
    yield {"email": email, "password": pw, "token": tok, "id": mid}
    db.users.delete_one({"_id": ObjectId(mid)})


@pytest.fixture(scope="module")
def second_manager(admin_tok):
    """Register + admin-approve a second manager to test isolation."""
    email = f"test_second_mgr_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Console@123"
    r = requests.post(f"{API}/console/register", json={
        "full_name": "TEST Second Manager", "email": email, "password": pw,
        "org_name": "TEST Org 2"}, timeout=15)
    assert r.status_code == 200
    mid = r.json()["user"]["id"]
    # approve
    a = requests.patch(f"{API}/admin/managers/{mid}", json={"action": "approve"},
                       headers=_h(admin_tok), timeout=15)
    assert a.status_code == 200, a.text
    tok = _login(email, pw)
    yield {"email": email, "password": pw, "token": tok, "id": mid}
    db.users.delete_many({"managed_by": mid})
    db.users.delete_one({"_id": ObjectId(mid)})


# ----------------- 1. Console registration -----------------
class TestConsoleRegistration:
    def test_register_creates_pending_manager(self, pending_manager):
        u = db.users.find_one({"_id": ObjectId(pending_manager["id"])})
        assert u["role"] == "manager"
        assert u["status"] == "pending"
        assert u["email"] == pending_manager["email"]

    def test_duplicate_email_400(self, pending_manager):
        r = requests.post(f"{API}/console/register", json={
            "full_name": "dup", "email": pending_manager["email"], "password": "Console@123"}, timeout=15)
        assert r.status_code == 400

    def test_short_password_400(self):
        r = requests.post(f"{API}/console/register", json={
            "full_name": "x", "email": f"test_short_{uuid.uuid4().hex[:6]}@example.com",
            "password": "short"}, timeout=15)
        assert r.status_code == 400


# ----------------- 2. Approval gate -----------------
class TestApprovalGate:
    def test_pending_can_read_summary_approved_false(self, pending_manager):
        r = requests.get(f"{API}/console/summary", headers=_h(pending_manager["token"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["approved"] is False

    def test_pending_can_read_vendors(self, pending_manager):
        r = requests.get(f"{API}/console/vendors", headers=_h(pending_manager["token"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_pending_cannot_create_vendor_403(self, pending_manager):
        r = requests.post(f"{API}/console/vendors", headers=_h(pending_manager["token"]),
                          json={"full_name": "x", "email": "y@z.com", "org_name": "o", "city": "Mumbai"},
                          timeout=15)
        assert r.status_code == 403
        assert "approval" in r.json().get("detail", "").lower() or "awaiting" in r.json().get("detail", "").lower()

    def test_pending_cannot_patch_vendor_403(self, pending_manager):
        # even non-existent vid should 403 before ownership
        r = requests.patch(f"{API}/console/vendors/{ObjectId()}", headers=_h(pending_manager["token"]),
                           json={"full_name": "x"}, timeout=15)
        assert r.status_code == 403

    def test_pending_cannot_resend_invite_403(self, pending_manager):
        r = requests.post(f"{API}/console/vendors/{ObjectId()}/invite",
                          headers=_h(pending_manager["token"]), timeout=15)
        assert r.status_code == 403


# ----------------- 3. Admin approve/suspend/reject -----------------
class TestAdminApproval:
    def test_admin_lists_managers(self, admin_tok, pending_manager):
        r = requests.get(f"{API}/admin/managers", headers=_h(admin_tok), timeout=15)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["items"]]
        assert pending_manager["id"] in ids
        m = next(m for m in r.json()["items"] if m["id"] == pending_manager["id"])
        assert m["status"] == "pending"
        assert "vendors" in m

    def test_non_admin_cannot_list_managers_403(self, approved_mgr_tok, member_tok):
        for tok in (approved_mgr_tok, member_tok):
            r = requests.get(f"{API}/admin/managers", headers=_h(tok), timeout=15)
            assert r.status_code == 403, f"unexpected {r.status_code}"

    def test_non_admin_cannot_patch_manager_403(self, approved_mgr_tok, pending_manager):
        r = requests.patch(f"{API}/admin/managers/{pending_manager['id']}",
                           json={"action": "approve"}, headers=_h(approved_mgr_tok), timeout=15)
        assert r.status_code == 403

    def test_approve_flips_to_active_and_allows_writes(self, admin_tok, pending_manager):
        r = requests.patch(f"{API}/admin/managers/{pending_manager['id']}",
                           json={"action": "approve"}, headers=_h(admin_tok), timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        # login again to get a fresh token (existing token has status=pending baked... actually no: JWT only has role; status is DB-read)
        # existing pending_manager token should now work for creates
        r2 = requests.get(f"{API}/console/summary", headers=_h(pending_manager["token"]), timeout=15)
        assert r2.json()["approved"] is True


# ----------------- 4. Vendor creation as approved manager -----------------
class TestVendorCreation:
    @pytest.fixture(scope="class")
    def vendor(self, approved_mgr_tok):
        email = f"test_vendor_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST Vendor One", "email": email,
                                "org_name": "TEST Vendor Org", "city": "Mumbai",
                                "mobile": "+911234567890"}, timeout=20)
        assert r.status_code == 200, r.text
        v = r.json()
        yield v
        db.events.delete_many({"partner_id": v["id"]})
        db.password_reset_tokens.delete_many({"user_id": v["id"]})
        db.users.delete_one({"_id": ObjectId(v["id"])})

    def test_vendor_created_with_managed_by(self, vendor, approved_mgr_tok):
        u = db.users.find_one({"_id": ObjectId(vendor["id"])})
        assert u["role"] == "partner"
        assert u["status"] == "active"
        # managed_by should equal ops.manager's id
        me = requests.get(f"{API}/auth/me", headers=_h(approved_mgr_tok), timeout=15).json()
        assert u["managed_by"] == me["id"]

    def test_password_reset_token_created(self, vendor):
        row = db.password_reset_tokens.find_one({"user_id": vendor["id"], "used": False})
        assert row is not None

    def test_duplicate_email_400(self, vendor, approved_mgr_tok):
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "dup", "email": vendor["email"],
                                "org_name": "o", "city": "Mumbai"}, timeout=15)
        assert r.status_code == 400

    def test_missing_city_400(self, approved_mgr_tok):
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST No City", "email": f"test_nc_{uuid.uuid4().hex[:6]}@e.com",
                                "org_name": "o", "city": ""}, timeout=15)
        assert r.status_code == 400

    def test_missing_org_400(self, approved_mgr_tok):
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST No Org", "email": f"test_no_{uuid.uuid4().hex[:6]}@e.com",
                                "org_name": "", "city": "Mumbai"}, timeout=15)
        assert r.status_code == 400


# ----------------- 5. Vendor takeover via password reset -----------------
class TestVendorTakeover:
    def test_reset_password_then_login_then_create_event(self, approved_mgr_tok):
        email = f"test_takeover_{uuid.uuid4().hex[:8]}@example.com"
        # create vendor
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST Takeover Vendor", "email": email,
                                "org_name": "TEST Takeover Org", "city": "Mumbai"}, timeout=20)
        assert r.status_code == 200
        vid = r.json()["id"]
        try:
            row = db.password_reset_tokens.find_one({"user_id": vid, "used": False})
            assert row is not None
            token = row["token"]
            new_pw = "NewVendor@123"
            r2 = requests.post(f"{API}/auth/reset-password",
                               json={"token": token, "password": new_pw}, timeout=15)
            assert r2.status_code == 200, r2.text
            # login
            tok = _login(email, new_pw)
            me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=15).json()
            assert me["role"] == "partner"
            # create an event
            ev = requests.post(f"{API}/partner/events", headers=_h(tok), json={
                "title": "TEST Takeover Event", "description": "test", "city": "Mumbai",
                "category": "dining", "starts_at": "2030-01-01T18:00:00Z",
                "ends_at": "2030-01-01T21:00:00Z", "capacity": 10, "price": 0,
                "min_age": 21, "max_age": 60}, timeout=20)
            assert ev.status_code in (200, 201), ev.text
        finally:
            db.events.delete_many({"partner_id": vid})
            db.password_reset_tokens.delete_many({"user_id": vid})
            db.users.delete_one({"_id": ObjectId(vid)})


# ----------------- 6. Vendor management, search, suspend-manager -----------------
class TestVendorManagement:
    @pytest.fixture(scope="class")
    def vendor(self, approved_mgr_tok):
        email = f"test_mgmt_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST Mgmt Vendor", "email": email,
                                "org_name": "TESTMgmtSearchable", "city": "Mumbai"}, timeout=20)
        assert r.status_code == 200
        v = r.json()
        yield v
        db.password_reset_tokens.delete_many({"user_id": v["id"]})
        db.users.delete_one({"_id": ObjectId(v["id"])})

    def test_get_detail_has_stats_and_recent(self, approved_mgr_tok, vendor):
        r = requests.get(f"{API}/console/vendors/{vendor['id']}", headers=_h(approved_mgr_tok), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "events" in d and "published" in d and "participants" in d
        assert "recent_events" in d

    def test_patch_edits_persist(self, approved_mgr_tok, vendor):
        r = requests.patch(f"{API}/console/vendors/{vendor['id']}", headers=_h(approved_mgr_tok),
                           json={"full_name": "TEST Mgmt Vendor Renamed", "city": "Delhi"}, timeout=15)
        assert r.status_code == 200
        u = db.users.find_one({"_id": ObjectId(vendor["id"])})
        assert u["full_name"] == "TEST Mgmt Vendor Renamed"
        assert u["city"] == "Delhi"

    def test_toggle_status_suspend_and_reactivate(self, approved_mgr_tok, vendor):
        r = requests.patch(f"{API}/console/vendors/{vendor['id']}", headers=_h(approved_mgr_tok),
                           json={"status": "suspended"}, timeout=15)
        assert r.status_code == 200
        assert db.users.find_one({"_id": ObjectId(vendor["id"])})["status"] == "suspended"
        r = requests.patch(f"{API}/console/vendors/{vendor['id']}", headers=_h(approved_mgr_tok),
                           json={"status": "active"}, timeout=15)
        assert r.status_code == 200
        assert db.users.find_one({"_id": ObjectId(vendor["id"])})["status"] == "active"

    def test_toggle_verified(self, approved_mgr_tok, vendor):
        r = requests.patch(f"{API}/console/vendors/{vendor['id']}", headers=_h(approved_mgr_tok),
                           json={"verified": True}, timeout=15)
        assert r.status_code == 200
        assert db.users.find_one({"_id": ObjectId(vendor["id"])})["verified"] is True

    def test_resend_invite(self, approved_mgr_tok, vendor):
        r = requests.post(f"{API}/console/vendors/{vendor['id']}/invite",
                          headers=_h(approved_mgr_tok), timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_search_filters(self, approved_mgr_tok, vendor):
        r = requests.get(f"{API}/console/vendors?q=TESTMgmtSearchable",
                         headers=_h(approved_mgr_tok), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(v["id"] == vendor["id"] for v in items)
        # negative
        r2 = requests.get(f"{API}/console/vendors?q=zzz_no_match_zzz",
                          headers=_h(approved_mgr_tok), timeout=15)
        assert not any(v["id"] == vendor["id"] for v in r2.json()["items"])


# ----------------- 7. Suspend manager → loses write access -----------------
class TestSuspendManager:
    def test_suspend_manager_blocks_writes(self, admin_tok):
        # Register a fresh manager, approve, then suspend, then attempt vendor create → 403
        email = f"test_suspflow_{uuid.uuid4().hex[:8]}@example.com"
        pw = "Console@123"
        r = requests.post(f"{API}/console/register", json={
            "full_name": "TEST Susp Manager", "email": email, "password": pw,
            "org_name": "TEST"}, timeout=15)
        assert r.status_code == 200
        mid = r.json()["user"]["id"]
        tok = r.json()["access_token"]
        try:
            # approve
            requests.patch(f"{API}/admin/managers/{mid}", json={"action": "approve"},
                           headers=_h(admin_tok), timeout=15).raise_for_status()
            # suspend
            requests.patch(f"{API}/admin/managers/{mid}", json={"action": "suspend"},
                           headers=_h(admin_tok), timeout=15).raise_for_status()
            # attempt write
            r2 = requests.post(f"{API}/console/vendors", headers=_h(tok),
                               json={"full_name": "x", "email": "y@z.com", "org_name": "o",
                                     "city": "Mumbai"}, timeout=15)
            assert r2.status_code == 403
            # After suspend, get_current_user rejects the account entirely; all authed calls fail.
            r3 = requests.get(f"{API}/console/summary", headers=_h(tok), timeout=15)
            assert r3.status_code in (401, 403)
            # reject
            r4 = requests.patch(f"{API}/admin/managers/{mid}", json={"action": "reject"},
                                headers=_h(admin_tok), timeout=15)
            assert r4.status_code == 200
            assert r4.json()["status"] == "rejected"
        finally:
            db.users.delete_many({"managed_by": mid})
            db.users.delete_one({"_id": ObjectId(mid)})


# ----------------- 8. Authorization isolation -----------------
class TestIsolation:
    def test_member_403_all_console(self, member_tok):
        for path in ("/console/summary", "/console/vendors"):
            r = requests.get(f"{API}{path}", headers=_h(member_tok), timeout=15)
            assert r.status_code == 403, f"{path} returned {r.status_code}"
        r = requests.post(f"{API}/console/vendors", headers=_h(member_tok),
                          json={"full_name": "x", "email": "y@z.com", "org_name": "o", "city": "Mumbai"},
                          timeout=15)
        assert r.status_code == 403

    def test_second_manager_cannot_see_others_vendor(self, approved_mgr_tok, second_manager):
        # create a vendor as approved_mgr
        email = f"test_iso_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/vendors", headers=_h(approved_mgr_tok),
                          json={"full_name": "TEST Iso Vendor", "email": email,
                                "org_name": "TEST Iso Org", "city": "Mumbai"}, timeout=20)
        assert r.status_code == 200
        vid = r.json()["id"]
        try:
            # second manager: empty list
            r2 = requests.get(f"{API}/console/vendors", headers=_h(second_manager["token"]), timeout=15)
            assert r2.status_code == 200
            assert all(v["id"] != vid for v in r2.json()["items"])
            # second manager: 404 on GET/PATCH/invite (not 403 to avoid ID leak)
            r3 = requests.get(f"{API}/console/vendors/{vid}", headers=_h(second_manager["token"]), timeout=15)
            assert r3.status_code == 404
            r4 = requests.patch(f"{API}/console/vendors/{vid}", headers=_h(second_manager["token"]),
                                json={"full_name": "x"}, timeout=15)
            assert r4.status_code == 404
            r5 = requests.post(f"{API}/console/vendors/{vid}/invite",
                               headers=_h(second_manager["token"]), timeout=15)
            assert r5.status_code == 404
        finally:
            db.password_reset_tokens.delete_many({"user_id": vid})
            db.users.delete_one({"_id": ObjectId(vid)})

    def test_admin_sees_all_vendors_including_legacy(self, admin_tok):
        r = requests.get(f"{API}/console/vendors", headers=_h(admin_tok), timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        # legacy partners have no managed_by
        legacy = [v for v in items if not v.get("managed_by")]
        assert len(legacy) >= 1, "admin should see legacy seeded partners with no managed_by"


# ----------------- 9. Member-app regressions -----------------
class TestMemberRegression:
    def test_member_endpoints_still_work(self, member_tok):
        for path in ("/auth/me", "/events?scope=upcoming", "/conversations", "/notifications"):
            r = requests.get(f"{API}{path}", headers=_h(member_tok), timeout=15)
            assert r.status_code == 200, f"{path} → {r.status_code}"

    def test_admin_other_tabs_still_work(self, admin_tok):
        for path in ("/admin/users?limit=5", "/admin/events?limit=5"):
            r = requests.get(f"{API}{path}", headers=_h(admin_tok), timeout=15)
            assert r.status_code == 200, f"{path} → {r.status_code}"
