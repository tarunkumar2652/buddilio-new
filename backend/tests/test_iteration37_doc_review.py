"""Iteration 37 — admin vendor-document review endpoints (backing the new DocsModal),
expiring-documents panel data and bank-proof freshness rule."""
import os
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

ADMIN = ("admin@buddilio.com", "Admin@123")
MEMBER = ("aarav.mehta@example.com", "User@123")
BANK_PROOF_DOCS = ["cancelled_cheque", "bank_statement", "bank_proof"]


def mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def client(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return client(*ADMIN)


@pytest.fixture(scope="module")
def member():
    return client(*MEMBER)


# ---------------- admin document review (DocsModal backend) ----------------
class TestAdminDocReview:
    @pytest.fixture(scope="class", autouse=True)
    def seeded(self, request):
        db = mongo()
        vid = db.vendor_profiles.insert_one({
            "legal_name": "TEST_iter37 Docs Vendor", "trade_name": "TEST_iter37",
            "email": "TEST_iter37@buddilio.com", "contact_person": "TEST QA",
            "status": "submitted", "vendor_kind": "organiser", "user_id": "",
            "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        did = db.vendor_documents.insert_one({
            "vendor_id": str(vid), "doc_type": "pan", "path": "/uploads/TEST_iter37/pan.pdf",
            "status": "pending", "note": "", "expires_on": "",
            "uploaded_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        request.cls.state = {"vid": str(vid), "did": str(did)}
        yield
        db.vendor_documents.delete_many({"vendor_id": str(vid)})
        db.vendor_profiles.delete_one({"_id": vid})

    def test_list_documents_shape(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/documents", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["complete"] is False
        assert "pan" in data["required"]
        row = next(x for x in data["items"] if x["doc_type"] == "pan")
        assert "_id" not in row and isinstance(row["id"], str)
        assert row["status"] == "pending"

    def test_meta_exposes_doc_types_for_modal(self, admin):
        r = admin.get(f"{BASE}/vendor-agreements/meta", timeout=30)
        assert r.status_code == 200
        keys = [d["key"] for d in r.json()["doc_types"]]
        assert "pan" in keys and "cancelled_cheque" in keys
        assert all({"key", "label", "required"} <= set(d) for d in r.json()["doc_types"])

    def test_approve_then_reject_persists(self, admin):
        for status in ["approved", "rejected", "approved"]:
            r = admin.patch(f"{BASE}/admin/vendor-documents/{self.state['did']}",
                            json={"status": status, "note": f"TEST_iter37 {status}"}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            got = admin.get(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/documents", timeout=30).json()
            row = next(x for x in got["items"] if x["doc_type"] == "pan")
            assert row["status"] == status, row
            assert row["note"] == f"TEST_iter37 {status}"
            assert row.get("reviewed_at")

    def test_approving_pan_marks_complete_only_with_bank_proof(self, admin):
        db = mongo()
        got = admin.get(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/documents", timeout=30).json()
        assert got["complete"] is False, "complete without an approved bank proof"
        addr = db.vendor_documents.insert_one({
            "vendor_id": self.state["vid"], "doc_type": "address_proof",
            "path": "/uploads/TEST_iter37/addr.pdf", "status": "pending", "note": "",
            "uploaded_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        assert admin.patch(f"{BASE}/admin/vendor-documents/{addr}",
                           json={"status": "approved"}, timeout=30).status_code == 200
        cheque = db.vendor_documents.insert_one({
            "vendor_id": self.state["vid"], "doc_type": "cancelled_cheque",
            "path": "/uploads/TEST_iter37/cheque.pdf", "status": "pending", "note": "",
            "uploaded_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        r = admin.patch(f"{BASE}/admin/vendor-documents/{cheque}", json={"status": "approved"}, timeout=30)
        assert r.status_code == 200
        got = admin.get(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/documents", timeout=30).json()
        assert got["complete"] is True, got

    def test_invalid_status_rejected(self, admin):
        r = admin.patch(f"{BASE}/admin/vendor-documents/{self.state['did']}",
                        json={"status": "whatever"}, timeout=30)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_unknown_document_404(self, admin):
        r = admin.patch(f"{BASE}/admin/vendor-documents/{ObjectId()}",
                        json={"status": "approved"}, timeout=30)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_malformed_id_400(self, admin):
        r = admin.patch(f"{BASE}/admin/vendor-documents/not-an-id", json={"status": "approved"}, timeout=30)
        assert r.status_code in (400, 404, 422), f"{r.status_code} {r.text[:200]}"

    def test_review_requires_permission(self, member):
        r = member.patch(f"{BASE}/admin/vendor-documents/{self.state['did']}",
                         json={"status": "approved"}, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        r = member.get(f"{BASE}/admin/vendor-profiles/{self.state['vid']}/documents", timeout=30)
        assert r.status_code == 403

    def test_anonymous_blocked(self):
        r = requests.patch(f"{BASE}/admin/vendor-documents/{self.state['did']}",
                           json={"status": "approved"}, timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- expiring documents panel ----------------
class TestExpiringPanel:
    @pytest.fixture(scope="class", autouse=True)
    def seeded(self, request):
        db = mongo()
        vid = db.vendor_profiles.insert_one({
            "legal_name": "TEST_iter37 Expiring Vendor", "email": "TEST_iter37exp@buddilio.com",
            "status": "approved", "vendor_kind": "organiser", "user_id": "",
            "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
        soon = (datetime.now(timezone.utc) + timedelta(days=11)).date().isoformat()
        far = (datetime.now(timezone.utc) + timedelta(days=200)).date().isoformat()
        db.vendor_documents.insert_one({"vendor_id": str(vid), "doc_type": "pan",
                                        "path": "/uploads/TEST_iter37/p.pdf", "status": "approved",
                                        "expires_on": soon, "note": ""})
        db.vendor_documents.insert_one({"vendor_id": str(vid), "doc_type": "cancelled_cheque",
                                        "path": "/uploads/TEST_iter37/c.pdf", "status": "approved",
                                        "expires_on": far, "note": ""})
        request.cls.state = {"vid": str(vid), "soon": soon, "far": far}
        yield
        db.vendor_documents.delete_many({"vendor_id": str(vid)})
        db.vendor_profiles.delete_one({"_id": vid})

    def test_expiring_within_30_days(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=30", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        mine = [i for i in items if i["vendor_id"] == self.state["vid"]]
        assert len(mine) == 1, mine
        row = mine[0]
        assert row["doc_type"] == "pan"
        assert row["expires_on"] == self.state["soon"]
        assert row["vendor"]["legal_name"] == "TEST_iter37 Expiring Vendor"
        assert "_id" not in row and "_id" not in row["vendor"]

    def test_days_window_respected(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=5", timeout=30)
        assert r.status_code == 200
        assert not [i for i in r.json()["items"] if i["vendor_id"] == self.state["vid"]]
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=365", timeout=30)
        assert len([i for i in r.json()["items"] if i["vendor_id"] == self.state["vid"]]) == 2

    def test_sorted_ascending(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-documents/expiring?days=365", timeout=30)
        dates = [i["expires_on"] for i in r.json()["items"]]
        assert dates == sorted(dates)

    def test_requires_permission(self, member):
        r = member.get(f"{BASE}/admin/vendor-documents/expiring", timeout=30)
        assert r.status_code == 403, r.status_code
