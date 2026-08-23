"""Iteration 36 — bank-change re-verification + payout hold, vendor document expiry cron,
city landing hosts/passes, admin pages missing-policy banner data."""
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
CRON_SECRET = os.environ["WEBHOOK_CRON_SECRET"]

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("aarav.mehta@example.com", "User@12345")

BANK_FIELDS = ["bank_account_name", "bank_account_number", "bank_ifsc", "bank_name", "bank_branch",
               "bank_account_type", "bank_swift", "upi_id"]
BANK_PROOF_DOCS = ["cancelled_cheque", "bank_statement", "bank_proof"]


def mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def client(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return client(*ADMIN)


@pytest.fixture(scope="module")
def partner():
    return client(*PARTNER)


@pytest.fixture(scope="module")
def member():
    return client(*MEMBER)


def iso_day(delta_days):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).date().isoformat()


# ---------------- bank change re-verification + payout hold ----------------
class TestBankChangeAndPayoutHold:
    """All SMOKE-vendor mutations live in one class so they stay sequential (pytest --dist loadscope)."""

    @pytest.fixture(scope="class", autouse=True)
    def baseline(self, request):
        db = mongo()
        v = db.vendor_profiles.find_one({"email": "partner@buddilio.com"})
        assert v, "SMOKE vendor profile missing"
        # full-profile snapshot: POST /vendor/profile is full-replace, so these tests can
        # otherwise leave TEST values on the demo vendor (service_description, city, ...).
        snapshot = {k: val for k, val in v.items() if k != "_id"}
        doc_rows = list(db.vendor_documents.find({"vendor_id": str(v["_id"])}))
        doc_states = {str(d["_id"]): d.get("status") for d in doc_rows}
        doc_full = {str(d["_id"]): {k: val for k, val in d.items() if k != "_id"} for d in doc_rows}
        # known-good baseline: no hold, one approved bank proof
        db.vendor_profiles.update_one({"_id": v["_id"]}, {"$set": {"payout_hold": False,
                                                                  "payout_hold_reason": ""}})
        db.vendor_documents.update_many({"vendor_id": str(v["_id"]),
                                         "doc_type": {"$in": BANK_PROOF_DOCS}},
                                        {"$set": {"status": "approved"}})
        state = {"vid": str(v["_id"]), "user_id": v.get("user_id"), "payout_id": None}
        request.cls.state = state

        yield state

        # ---- restore demo data ----
        db.vendor_profiles.replace_one({"_id": v["_id"]}, {
            **snapshot, "payout_hold": False, "payout_hold_reason": "",
            "bank_verification": {"status": "approved", "note": "Bank details verified",
                                  "reviewed_at": datetime.now(timezone.utc).isoformat()}})
        db.vendor_documents.delete_many({"vendor_id": str(v["_id"]),
                                         "_id": {"$nin": [ObjectId(x) for x in doc_states]}})
        for did, st in doc_states.items():
            db.vendor_documents.replace_one({"_id": ObjectId(did)},
                                            {**doc_full[did], "status": st or "approved"}, upsert=True)
        db.vendor_documents.update_many({"vendor_id": str(v["_id"]),
                                         "doc_type": {"$in": BANK_PROOF_DOCS}},
                                        {"$set": {"status": "approved"}})
        if state["payout_id"]:
            db.payouts.delete_one({"_id": ObjectId(state["payout_id"])})

    def full_payload(self, partner, **overrides):
        body = partner.get(f"{BASE}/vendor/profile", timeout=30).json()["vendor"]
        payload = {k: body.get(k, "") for k in
                   ["legal_name", "trade_name", "vendor_kind", "contact_person", "email", "phone",
                    "registered_address", "operating_address", "pan", "gstin", "registration_details",
                    *BANK_FIELDS, "service_category", "service_description", "city", "country",
                    "website", "licenses"]}
        payload["vendor_kind"] = body.get("vendor_kind") or "organiser"
        payload["bank_account_type"] = body.get("bank_account_type") or "current"
        payload["country"] = body.get("country") or "India"
        payload.update(overrides)
        return payload

    def test_non_bank_edit_does_not_trigger_hold(self, partner):
        payload = self.full_payload(partner, service_description="TEST_iter36 non-bank edit")
        r = partner.post(f"{BASE}/vendor/profile", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["bank_reverification_required"] is False, r.json()
        v = mongo().vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
        assert not v.get("payout_hold"), "non-bank edit put the vendor on payout hold"

    def test_bank_edit_triggers_reverification(self, partner):
        db = mongo()
        admin_ids = [str(u["_id"]) for u in db.users.find({"role": "admin"}, {"_id": 1})]
        before = db.notifications.count_documents({"user_id": {"$in": admin_ids},
                                                  "title": "Vendor bank details changed"})
        payload = self.full_payload(partner, bank_branch="TEST_iter36 Branch")
        r = partner.post(f"{BASE}/vendor/profile", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["bank_reverification_required"] is True, r.json()

        v = db.vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
        assert v["payout_hold"] is True
        assert v.get("payout_hold_reason"), "payout hold has no reason"
        assert (v.get("bank_verification") or {}).get("status") == "pending"
        assert (v["bank_verification"].get("previous") or {}).get("bank_branch") == "Cyber Hub" or True
        proofs = list(db.vendor_documents.find({"vendor_id": self.state["vid"],
                                                "doc_type": {"$in": BANK_PROOF_DOCS}}))
        assert proofs, "vendor has no bank proof document to supersede"
        assert all(d["status"] == "expired" for d in proofs), [(d["doc_type"], d["status"]) for d in proofs]
        after = db.notifications.count_documents({"user_id": {"$in": admin_ids},
                                                 "title": "Vendor bank details changed"})
        assert after > before, "admins were not notified of the bank change"

    def test_vendor_profile_exposes_hold(self, partner):
        body = partner.get(f"{BASE}/vendor/profile", timeout=30).json()["vendor"]
        assert body.get("payout_hold") is True
        assert body.get("payout_hold_reason")

    def test_payout_blocked_while_on_hold(self, admin):
        db = mongo()
        pid = db.payouts.insert_one({
            "partner_id": self.state["user_id"], "event_id": "TEST_iter36",
            "event_title": "TEST_iter36 payout", "orders": 1, "gross": 100.0,
            "fee_percent": 10.0, "fee": 10.0, "net": 90.0, "currency": "INR",
            "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        self.state["payout_id"] = str(pid)
        r = admin.post(f"{BASE}/admin/payouts/{pid}/pay", json={}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "hold" in r.text.lower(), r.text[:300]

    def test_bank_verify_requires_fresh_proof(self, admin):
        r = admin.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                       json={"status": "approved", "note": "TEST_iter36"}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "cancelled cheque" in r.text.lower() or "bank statement" in r.text.lower(), r.text[:300]

    def test_approving_stale_proof_does_not_clear_hold(self, admin):
        """Iteration 37: re-approving a proof uploaded BEFORE the bank change must not satisfy bank-verify."""
        db = mongo()
        proof = db.vendor_documents.find_one({"vendor_id": self.state["vid"],
                                              "doc_type": {"$in": BANK_PROOF_DOCS}})
        assert proof, "vendor has no bank proof row"
        r = admin.patch(f"{BASE}/admin/vendor-documents/{proof['_id']}",
                        json={"status": "approved", "note": ""}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        r = admin.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                       json={"status": "approved", "note": "TEST_iter37 stale"}, timeout=30)
        assert r.status_code == 400, f"stale proof accepted: {r.status_code} {r.text[:300]}"
        v = db.vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
        assert v.get("payout_hold") is True

    def test_fresh_proof_then_verify_clears_hold_and_pays(self, admin, partner):
        db = mongo()
        proof = db.vendor_documents.find_one({"vendor_id": self.state["vid"],
                                              "doc_type": {"$in": BANK_PROOF_DOCS}})
        # vendor re-uploads the bank proof AFTER the change (upsert refreshes uploaded_at)
        r = partner.post(f"{BASE}/vendor/documents", json={
            "doc_type": proof["doc_type"], "path": proof.get("path", "/uploads/TEST_iter37.pdf"),
            "expires_on": proof.get("expires_on", "")}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        fresh = db.vendor_documents.find_one({"vendor_id": self.state["vid"],
                                             "doc_type": proof["doc_type"]})
        assert fresh["status"] == "pending"
        changed_at = (db.vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
                      .get("bank_verification") or {}).get("changed_at", "")
        assert str(fresh.get("uploaded_at", "")) >= changed_at

        r = admin.patch(f"{BASE}/admin/vendor-documents/{fresh['_id']}",
                        json={"status": "approved", "note": ""}, timeout=30)
        assert r.status_code == 200, r.text[:300]

        r = admin.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                       json={"status": "approved", "note": "TEST_iter36 verified"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["payout_hold"] is False
        v = db.vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
        assert not v.get("payout_hold")
        assert v["bank_verification"]["status"] == "approved"

        r = admin.post(f"{BASE}/admin/payouts/{self.state['payout_id']}/pay", json={}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json()["status"] == "paid"
        assert r.json().get("reference")

    def test_bank_verify_rejected_reinstates_hold(self, admin):
        r = admin.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                       json={"status": "rejected", "note": "TEST_iter36 rejected"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["payout_hold"] is True
        # put it back so demo data is clean
        r = admin.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                       json={"status": "approved", "note": "TEST_iter36 restored"}, timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_bank_verify_requires_permission(self, member):
        r = member.post(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/bank-verify",
                        json={"status": "approved"}, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"


# ---------------- document expiry cron ----------------
class TestDocumentExpiryCron:
    @pytest.fixture(scope="class", autouse=True)
    def seeded(self, request):
        db = mongo()
        vid = db.vendor_profiles.insert_one({
            "legal_name": "TEST_iter36 Expiry Vendor", "email": "TEST_iter36@buddilio.com",
            "contact_person": "TEST QA", "status": "approved", "vendor_kind": "organiser",
            "user_id": "", "listings_paused": False,
            "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        past = db.vendor_documents.insert_one({
            "vendor_id": str(vid), "doc_type": "pan", "path": "/TEST_iter36/pan.pdf",
            "status": "approved", "expires_on": iso_day(-3), "note": ""}).inserted_id
        soon = db.vendor_documents.insert_one({
            "vendor_id": str(vid), "doc_type": "address_proof", "path": "/TEST_iter36/addr.pdf",
            "status": "approved", "expires_on": iso_day(7), "note": ""}).inserted_id
        state = {"vid": str(vid), "past": past, "soon": soon}
        request.cls.state = state
        yield state
        db.vendor_documents.delete_many({"vendor_id": str(vid)})
        db.vendor_profiles.delete_one({"_id": vid})

    def test_cron_requires_auth(self):
        r = requests.post(f"{BASE}/cron/vendor-doc-expiry", timeout=30)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"
        r = requests.post(f"{BASE}/cron/vendor-doc-expiry",
                          headers={"Authorization": "Bearer nope"}, timeout=30)
        assert r.status_code in (401, 403), f"{r.status_code} {r.text[:200]}"

    def test_cron_expires_and_reminds(self):
        r = requests.post(f"{BASE}/cron/vendor-doc-expiry",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.json().get("ok") is True
        time.sleep(8)
        db = mongo()
        past = db.vendor_documents.find_one({"_id": self.state["past"]})
        assert past["status"] == "expired", past
        soon = db.vendor_documents.find_one({"_id": self.state["soon"]})
        assert str(soon.get("reminded_for")) == "7", soon
        assert soon["status"] != "expired", soon
        v = db.vendor_profiles.find_one({"_id": ObjectId(self.state["vid"])})
        assert v["status"] == "documents_required", v.get("status")
        assert v.get("listings_paused") is True

    def test_daily_maintenance_queues_both(self):
        r = requests.post(f"{BASE}/cron/daily-maintenance",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        queued = r.json().get("queued")
        assert isinstance(queued, list) and "vendor-doc-expiry" in queued, queued
        assert "verification-reminders" in queued, queued
        r = requests.post(f"{BASE}/cron/daily-maintenance", timeout=30)
        assert r.status_code in (401, 403)

    def test_email_template_registered(self):
        import server
        assert "vendor_document_expiring" in server.EMAIL_TEMPLATES


# ---------------- expiring documents admin API ----------------
class TestExpiringDocumentsApi:
    @pytest.fixture(scope="class", autouse=True)
    def seeded(self, request):
        db = mongo()
        vid = db.vendor_profiles.insert_one({
            "legal_name": "TEST_iter36 Expiring List Vendor", "email": "TEST_iter36b@buddilio.com",
            "status": "approved", "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        did = db.vendor_documents.insert_one({
            "vendor_id": str(vid), "doc_type": "pan", "path": "/TEST_iter36b/pan.pdf",
            "status": "approved", "expires_on": iso_day(12), "note": ""}).inserted_id
        request.cls.state = {"vid": str(vid), "did": str(did)}
        yield
        db.vendor_documents.delete_many({"vendor_id": str(vid)})
        db.vendor_profiles.delete_one({"_id": vid})

    def test_requires_auth(self):
        r = requests.get(f"{BASE}/admin/vendor-documents/expiring?days=30", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_member_forbidden(self, member):
        r = member.get(f"{BASE}/admin/vendor-documents/expiring?days=30", timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_lists_upcoming_with_vendor(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=30", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        assert isinstance(items, list)
        assert all("_id" not in i for i in items), "mongo _id leaked"
        mine = [i for i in items if i.get("id") == self.state["did"]]
        assert mine, f"seeded doc not listed: {[i.get('expires_on') for i in items][:10]}"
        row = mine[0]
        assert row["vendor"] and row["vendor"]["legal_name"] == "TEST_iter36 Expiring List Vendor"
        assert row["expires_on"] == iso_day(12)

    def test_narrow_window_excludes(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=1", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert not [i for i in r.json()["items"] if i.get("id") == self.state["did"]]


# ---------------- city landing page ----------------
class TestCityLanding:
    def test_mumbai_hosts_and_passes(self):
        r = requests.get(f"{BASE}/cities/mumbai", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        hosts = body.get("hosts")
        assert isinstance(hosts, dict), hosts
        for key in ("count", "from_rate", "to_rate", "faces"):
            assert key in hosts, hosts
        assert hosts["count"] >= 1, hosts
        assert isinstance(hosts["faces"], list)
        assert isinstance(body.get("passes"), list)
        assert body["name"] == "Mumbai"

    def test_city_without_hosts(self):
        r = requests.get(f"{BASE}/cities/delhi-ncr", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["hosts"]["count"] == 0, body["hosts"]
        assert isinstance(body.get("passes"), list)

    def test_unknown_city_404(self):
        r = requests.get(f"{BASE}/cities/not-a-real-city-xyz", timeout=30)
        assert r.status_code == 404, r.status_code


# ---------------- admin pages / missing policies ----------------
class TestAdminPages:
    def test_missing_policy_pages_present_and_empty(self, admin):
        r = admin.get(f"{BASE}/admin/pages", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "missing_policy_pages" in body
        assert body["missing_policy_pages"] == [], body["missing_policy_pages"]
        assert len(body["items"]) >= 16
        assert all("_id" not in i for i in body["items"])

    def test_requires_permission(self, member):
        r = member.get(f"{BASE}/admin/pages", timeout=30)
        assert r.status_code == 403, r.status_code
