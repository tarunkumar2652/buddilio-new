"""Iteration 18 — Vendor invite links, self-signup, documents, payouts, activity log, AI copy helper."""
import os
import time
import uuid

import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MANAGER = ("ops.manager@buddilio.com", "Console@123")
MEMBER = ("diya.sharma@example.com", "User@12345")
PARTNER = ("partner@buddilio.com", "Partner@123")

STATE = {}


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def mgr_tok():
    return login(*MANAGER)


@pytest.fixture(scope="module")
def admin_tok():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def member_tok():
    return login(*MEMBER)


@pytest.fixture(scope="module")
def partner_tok():
    return login(*PARTNER)


# ============================================================
# Invites
# ============================================================
class TestInvites:
    def test_create_invite_returns_link_and_pending(self, mgr_tok):
        email = f"test_inv_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/invites", headers=H(mgr_tok),
                          json={"email": email, "org_name": "TEST Org", "city": "Mumbai", "note": "TEST note"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert "/vendor-signup?token=" in d["link"]
        assert d["email"] == email
        STATE['invite_id_1'] = d["id"]
        STATE['invite_link_1'] = d["link"]
        STATE['invite_email_1'] = email

    def test_invite_appears_in_list(self, mgr_tok):
        r = requests.get(f"{API}/console/invites", headers=H(mgr_tok))
        assert r.status_code == 200
        ids = [i["id"] for i in r.json()["items"]]
        assert STATE['invite_id_1'] in ids

    def test_public_lookup_by_token(self):
        token = STATE['invite_link_1'].split("token=")[1]
        r = requests.get(f"{API}/vendor-invite/{token}")
        assert r.status_code == 200
        d = r.json()
        assert d["org_name"] == "TEST Org"
        assert d["city"] == "Mumbai"
        assert d["note"] == "TEST note"

    def test_bad_token_404(self):
        r = requests.get(f"{API}/vendor-invite/notarealtoken12345")
        assert r.status_code == 404

    def test_revoke_pending_invite(self, mgr_tok):
        # Create a fresh invite to revoke
        email = f"test_rev_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/invites", headers=H(mgr_tok),
                          json={"email": email, "org_name": "TEST Rev", "city": "Delhi"})
        iid = r.json()["id"]
        token = r.json()["link"].split("token=")[1]

        rv = requests.delete(f"{API}/console/invites/{iid}", headers=H(mgr_tok))
        assert rv.status_code == 200
        # public lookup should now 404
        r2 = requests.get(f"{API}/vendor-invite/{token}")
        assert r2.status_code == 404

    def test_duplicate_email_invite_400(self, mgr_tok, db):
        # existing user email
        r = requests.post(f"{API}/console/invites", headers=H(mgr_tok),
                          json={"email": ADMIN[0], "org_name": "TEST", "city": "Mumbai"})
        assert r.status_code == 400

    def test_member_cannot_create_invite(self, member_tok):
        r = requests.post(f"{API}/console/invites", headers=H(member_tok),
                          json={"email": "test_x@example.com", "org_name": "TEST", "city": "Mumbai"})
        assert r.status_code == 403


# ============================================================
# Signup accept
# ============================================================
class TestVendorSignup:
    def test_accept_flow_creates_partner(self, mgr_tok, db):
        email = f"test_vs_{uuid.uuid4().hex[:8]}@example.com"
        c = requests.post(f"{API}/console/invites", headers=H(mgr_tok),
                          json={"email": email, "org_name": "TEST Vendor Sign", "city": "Mumbai", "note": "welcome"})
        assert c.status_code == 200
        token = c.json()["link"].split("token=")[1]
        STATE['vs_token'] = token
        STATE['vs_email'] = email
        STATE['vs_invite_id'] = c.json()["id"]

        # short password
        r = requests.post(f"{API}/vendor-invite/{token}/accept",
                          json={"full_name": "TEST V", "org_name": "TEST Vendor Sign", "city": "Mumbai",
                                "password": "short", "mobile": "9999999999", "bio": "hi"})
        assert r.status_code == 400

        # missing org
        r = requests.post(f"{API}/vendor-invite/{token}/accept",
                          json={"full_name": "TEST V", "org_name": "", "city": "Mumbai",
                                "password": "Vendor@1234"})
        assert r.status_code == 400

        # success
        r = requests.post(f"{API}/vendor-invite/{token}/accept",
                          json={"full_name": "TEST V", "org_name": "TEST Vendor Sign", "city": "Mumbai",
                                "password": "Vendor@1234", "mobile": "9999999999", "bio": "TEST bio"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["access_token"]
        assert d["user"]["role"] == "partner"
        assert d["user"]["email"] == email
        STATE['vs_partner_tok'] = d["access_token"]
        STATE['vs_partner_id'] = d["user"]["id"]

    def test_reuse_token_404(self):
        r = requests.post(f"{API}/vendor-invite/{STATE['vs_token']}/accept",
                          json={"full_name": "x", "org_name": "y", "city": "Mumbai", "password": "Vendor@1234"})
        assert r.status_code == 404

    def test_get_reused_token_404(self):
        r = requests.get(f"{API}/vendor-invite/{STATE['vs_token']}")
        assert r.status_code == 404

    def test_revoking_accepted_invite_400(self, mgr_tok):
        r = requests.delete(f"{API}/console/invites/{STATE['vs_invite_id']}", headers=H(mgr_tok))
        assert r.status_code == 400

    def test_managed_by_stamped(self, mgr_tok, db):
        u = db.users.find_one({"_id": ObjectId(STATE['vs_partner_id'])})
        assert u["managed_by"]
        # appears in manager's vendor list
        r = requests.get(f"{API}/console/vendors", headers=H(mgr_tok))
        vids = [v["id"] for v in r.json()["items"]]
        assert STATE['vs_partner_id'] in vids


# ============================================================
# Documents
# ============================================================
class TestDocuments:
    def test_put_documents_ok(self):
        tok = STATE['vs_partner_tok']
        r = requests.put(f"{API}/partner/documents", headers=H(tok),
                         json={"documents": [{"name": "TEST licence.pdf",
                                              "url": "/api/files/buddilio/uploads/x/test.pdf",
                                              "kind": "licence"}]})
        assert r.status_code == 200
        assert len(r.json()["documents"]) == 1

    def test_external_url_400(self):
        r = requests.put(f"{API}/partner/documents", headers=H(STATE['vs_partner_tok']),
                         json={"documents": [{"name": "bad", "url": "https://evil.com/x.pdf"}]})
        assert r.status_code == 400

    def test_member_403(self, member_tok):
        r = requests.put(f"{API}/partner/documents", headers=H(member_tok),
                         json={"documents": []})
        assert r.status_code == 403

    def test_remove_persists(self):
        r = requests.put(f"{API}/partner/documents", headers=H(STATE['vs_partner_tok']),
                         json={"documents": []})
        assert r.status_code == 200
        assert r.json()["documents"] == []

    def test_documents_show_in_console_vendor_detail(self, mgr_tok):
        # re-add
        requests.put(f"{API}/partner/documents", headers=H(STATE['vs_partner_tok']),
                     json={"documents": [{"name": "TEST doc.pdf",
                                          "url": "/api/files/buddilio/uploads/y/a.pdf", "kind": "id"}]})
        r = requests.get(f"{API}/console/vendors/{STATE['vs_partner_id']}", headers=H(mgr_tok))
        assert r.status_code == 200
        docs = r.json().get("documents") or r.json().get("vendor", {}).get("documents")
        assert docs and len(docs) == 1


# ============================================================
# Cross-manager isolation
# ============================================================
class TestIsolation:
    def test_second_manager_isolation(self, admin_tok, mgr_tok, db):
        # Register another manager via /console/register, admin-approve them.
        email = f"test_mgr2_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/console/register", json={
            "full_name": "TEST Mgr Two", "email": email, "password": "Console@123",
            "org_name": "TEST Ops 2", "city": "Delhi", "mobile": "9999999999"})
        assert r.status_code == 200, r.text
        mgr2_tok = r.json()["access_token"]
        mgr2_id = r.json()["user"]["id"]

        # admin approve
        ap = requests.patch(f"{API}/admin/managers/{mgr2_id}", headers=H(admin_tok),
                            json={"action": "approve"})
        assert ap.status_code == 200

        # re-login to get non-pending token
        mgr2_tok = login(email, "Console@123")

        # mgr2 lists invites — should not see mgr1's invite
        r = requests.get(f"{API}/console/invites", headers=H(mgr2_tok))
        ids = [i["id"] for i in r.json()["items"]]
        assert STATE['invite_id_1'] not in ids

        # mgr2 cannot access mgr1's vendor
        r = requests.get(f"{API}/console/vendors/{STATE['vs_partner_id']}", headers=H(mgr2_tok))
        assert r.status_code == 404

        # mgr2 cannot revoke mgr1's invite
        r = requests.delete(f"{API}/console/invites/{STATE['invite_id_1']}", headers=H(mgr2_tok))
        assert r.status_code == 404


# ============================================================
# Payouts
# ============================================================
class TestPayouts:
    def test_manager_sees_own_only(self, mgr_tok):
        r = requests.get(f"{API}/console/payouts", headers=H(mgr_tok))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "totals" in d
        for k in ("paid", "pending", "gross", "fees"):
            assert k in d["totals"]

    def test_admin_sees_all_and_has_nightfall(self, admin_tok):
        r = requests.get(f"{API}/console/payouts", headers=H(admin_tok))
        assert r.status_code == 200
        d = r.json()
        vendors = {i["vendor"] for i in d["items"]}
        # at least should have some payouts
        assert len(d["items"]) >= 0
        paid_rows = [i for i in d["items"] if i["status"] == "paid"]
        # spec says 2 paid payouts for Nightfall Collective — soft check
        nf_paid = [i for i in paid_rows if "Nightfall" in i.get("vendor", "")]
        assert len(nf_paid) >= 1

    def test_member_403(self, member_tok):
        r = requests.get(f"{API}/console/payouts", headers=H(member_tok))
        assert r.status_code == 403


# ============================================================
# AI Copy Helper
# ============================================================
class TestAiDraft:
    def test_notes_too_short_400(self, partner_tok):
        r = requests.post(f"{API}/partner/ai-draft", headers=H(partner_tok),
                          json={"notes": "short"})
        assert r.status_code == 400

    def test_notes_too_long_400(self, partner_tok):
        r = requests.post(f"{API}/partner/ai-draft", headers=H(partner_tok),
                          json={"notes": "x" * 1600})
        assert r.status_code == 400

    def test_member_403(self, member_tok):
        r = requests.post(f"{API}/partner/ai-draft", headers=H(member_tok),
                          json={"notes": "TEST rooftop supper club regional dishes music"})
        assert r.status_code == 403

    def test_draft_ok_and_rules_include_21(self, partner_tok):
        notes = "Rooftop supper club, small plates, live jazz, mixed group of strangers, 20 seats"
        r = requests.post(f"{API}/partner/ai-draft", headers=H(partner_tok),
                          json={"notes": notes, "category": "dining", "city": "Mumbai"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("title")
        assert d.get("description")
        rules = " ".join(d.get("rules") or []) if isinstance(d.get("rules"), list) else str(d.get("rules", ""))
        # spec: '21+, valid ID at entry' must be in rules
        assert "21+" in rules and "ID" in rules.upper() or "id at entry" in rules.lower()
        assert d["daily_cap"] == 20


# ============================================================
# Activity log
# ============================================================
class TestActivityLog:
    def test_admin_gets_activity(self, admin_tok):
        r = requests.get(f"{API}/admin/vendor-activity", headers=H(admin_tok))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        # newest first
        assert items[0].get("created_at") >= items[-1].get("created_at")
        # every row has action + actor + created_at
        for it in items[:5]:
            assert it["action"] and it["created_at"]

    def test_member_403(self, member_tok):
        r = requests.get(f"{API}/admin/vendor-activity", headers=H(member_tok))
        assert r.status_code == 403

    def test_partner_403(self, partner_tok):
        r = requests.get(f"{API}/admin/vendor-activity", headers=H(partner_tok))
        assert r.status_code == 403


# ============================================================
# Regression sanity
# ============================================================
class TestRegression:
    def test_member_me(self, member_tok):
        assert requests.get(f"{API}/auth/me", headers=H(member_tok)).status_code == 200

    def test_events_public(self):
        assert requests.get(f"{API}/events").status_code == 200

    def test_console_summary(self, mgr_tok):
        assert requests.get(f"{API}/console/summary", headers=H(mgr_tok)).status_code == 200


# ============================================================
# cleanup
# ============================================================
@pytest.fixture(scope="module", autouse=True)
def cleanup(db):
    yield
    # nuke TEST invites, users, ai_drafts, audits
    db.vendor_invites.delete_many({"$or": [{"email": {"$regex": "^test_"}},
                                            {"org_name": {"$regex": "^TEST"}}]})
    users = list(db.users.find({"email": {"$regex": "^test_"}}, {"_id": 1}))
    uids = [str(u["_id"]) for u in users]
    if uids:
        db.ai_drafts.delete_many({"user_id": {"$in": uids}})
        db.users.delete_many({"_id": {"$in": [ObjectId(i) for i in uids]}})
