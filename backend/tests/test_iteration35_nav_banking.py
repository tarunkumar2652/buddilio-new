"""Iteration 35 — admin nav favourites API, vendor banking details, bank-proof doc gating, agreement PDF annexure."""
import os
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
PARTNER = ("partner@buddilio.com", "Partner@123")


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


# ---------------- admin nav favourites ----------------
class TestAdminNav:
    def test_get_default(self, admin):
        r = admin.get(f"{BASE}/me/admin-nav", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "favourites" in body and isinstance(body["favourites"], list)

    def test_put_and_persist(self, admin):
        original = admin.get(f"{BASE}/me/admin-nav", timeout=30).json()["favourites"]
        r = admin.put(f"{BASE}/me/admin-nav", json={"favourites": ["ledger", "payouts"]}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["favourites"] == ["ledger", "payouts"]

        g = admin.get(f"{BASE}/me/admin-nav", timeout=30)
        assert g.status_code == 200
        assert g.json()["favourites"] == ["ledger", "payouts"]

        # unpin one
        r2 = admin.put(f"{BASE}/me/admin-nav", json={"favourites": ["payouts"]}, timeout=30)
        assert r2.json()["favourites"] == ["payouts"]
        assert admin.get(f"{BASE}/me/admin-nav", timeout=30).json()["favourites"] == ["payouts"]

        admin.put(f"{BASE}/me/admin-nav", json={"favourites": original}, timeout=30)

    def test_cap_and_sanitise(self, admin):
        original = admin.get(f"{BASE}/me/admin-nav", timeout=30).json()["favourites"]
        r = admin.put(f"{BASE}/me/admin-nav", json={"favourites": [f"k{i}" for i in range(20)]}, timeout=30)
        assert r.status_code == 200
        assert len(r.json()["favourites"]) == 12
        r2 = admin.put(f"{BASE}/me/admin-nav", json={}, timeout=30)
        assert r2.status_code == 200 and r2.json()["favourites"] == []
        admin.put(f"{BASE}/me/admin-nav", json={"favourites": original}, timeout=30)

    def test_requires_auth(self):
        r = requests.get(f"{BASE}/me/admin-nav", timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_per_account_isolation(self, admin, partner):
        admin.put(f"{BASE}/me/admin-nav", json={"favourites": ["ledger"]}, timeout=30)
        p = partner.get(f"{BASE}/me/admin-nav", timeout=30)
        assert p.status_code == 200
        assert p.json()["favourites"] != ["ledger"] or p.json()["favourites"] == []
        admin.put(f"{BASE}/me/admin-nav", json={"favourites": []}, timeout=30)


# ---------------- vendor meta + banking ----------------
class TestVendorBanking:
    def test_meta_bank_fields(self, admin):
        r = admin.get(f"{BASE}/vendor-agreements/meta", timeout=30)
        assert r.status_code == 200, r.text[:300]
        m = r.json()
        assert m["bank_account_types"] == ["current", "savings", "cc", "od"]
        assert set(m["bank_proof_options"]) == {"cancelled_cheque", "bank_statement", "bank_proof"}
        keys = [d["key"] for d in m["doc_types"]]
        assert "cancelled_cheque" in keys and "bank_statement" in keys

    def test_profile_saves_all_bank_fields(self, partner):
        cur = partner.get(f"{BASE}/vendor/profile", timeout=30)
        assert cur.status_code == 200, cur.text[:300]
        v = cur.json()["vendor"]
        assert v, "partner has no vendor profile — seed expected SMOKE Vendor LLP"
        payload = {k: v.get(k) or "" for k in
                   ("legal_name", "trade_name", "contact_person", "email", "phone",
                    "pan", "gstin", "registered_address", "service_category", "website")}
        payload["email"] = v.get("email") or "partner@buddilio.com"
        payload["vendor_kind"] = v.get("vendor_kind") or "organiser"
        bank = {"bank_account_name": "TEST Holder Name", "bank_account_number": "123456789012",
                "bank_ifsc": "HDFC0001234", "bank_name": "HDFC Bank", "bank_branch": "Cyber Hub",
                "bank_account_type": "savings", "bank_swift": "HDFCINBB", "upi_id": "buddilio@hdfcbank"}
        payload.update(bank)
        r = partner.post(f"{BASE}/vendor/profile", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:400]
        saved = r.json()["vendor"]
        for k, val in bank.items():
            assert saved.get(k) == val, f"{k} -> {saved.get(k)}"

        # persistence via GET
        g = partner.get(f"{BASE}/vendor/profile", timeout=30)
        assert g.status_code == 200
        body = g.json()
        for k, val in bank.items():
            assert body["vendor"].get(k) == val, f"GET {k} -> {body['vendor'].get(k)}"
        assert "banking_rows" in body
        rows = {r0[0]: r0[1] for r0 in body["banking_rows"]}
        assert rows["Account holder name"] == "TEST Holder Name"
        assert rows["Account number"] == "123456789012"
        assert rows["Account type"] == "Savings"
        assert rows["UPI ID"] == "buddilio@hdfcbank"
        assert "_id" not in body["vendor"]

    def test_invalid_account_type_rejected(self, partner):
        v = partner.get(f"{BASE}/vendor/profile", timeout=30).json()["vendor"]
        payload = {"legal_name": v.get("legal_name") or "TEST Vendor",
                   "email": v.get("email") or "partner@buddilio.com",
                   "vendor_kind": v.get("vendor_kind") or "organiser",
                   "bank_account_type": "crypto"}
        r = partner.post(f"{BASE}/vendor/profile", json=payload, timeout=30)
        assert r.status_code == 422, f"expected validation error, got {r.status_code}"


# ---------------- docs_complete gating ----------------
class TestBankProofGating:
    @pytest.fixture(scope="class")
    def vendor(self):
        db = mongo()
        v = db.vendor_profiles.insert_one({
            "user_id": "TEST_i35", "legal_name": "TEST Bank Proof LLP", "trade_name": "TEST BP",
            "vendor_kind": "organiser", "contact_person": "QA", "pan": "AAAAA1111A",
            "registered_address": "Gurugram", "service_category": "events", "status": "submitted",
            "bank_account_name": "TEST BP", "bank_account_number": "999988887777",
            "bank_ifsc": "ICIC0000123", "bank_name": "ICICI", "bank_account_type": "current",
        })
        vid = str(v.inserted_id)
        yield vid
        db.vendor_documents.delete_many({"vendor_id": vid})
        db.vendor_profiles.delete_one({"_id": ObjectId(vid)})

    def test_approve_blocked_without_bank_proof(self, admin, vendor):
        db = mongo()
        db.vendor_documents.delete_many({"vendor_id": vendor})
        for dt in ("pan", "address_proof"):
            db.vendor_documents.insert_one({"vendor_id": vendor, "doc_type": dt, "path": "/api/files/x",
                                            "status": "approved", "note": ""})
        r = admin.get(f"{BASE}/admin/vendor-profiles/{vendor}/documents", timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["complete"] is False

        r2 = admin.patch(f"{BASE}/admin/vendor-profiles/{vendor}/status",
                         json={"status": "approved", "reason": "TEST"}, timeout=30)
        assert r2.status_code == 400, f"{r2.status_code} {r2.text[:300]}"
        detail = r2.json().get("detail", "")
        assert "bank" in detail.lower() and "cancelled cheque" in detail.lower(), detail

    def test_approve_unblocked_with_cancelled_cheque(self, admin, vendor):
        db = mongo()
        db.vendor_documents.insert_one({"vendor_id": vendor, "doc_type": "cancelled_cheque",
                                        "path": "/api/files/cheque", "status": "approved", "note": ""})
        r = admin.get(f"{BASE}/admin/vendor-profiles/{vendor}/documents", timeout=30)
        assert r.json()["complete"] is True
        r2 = admin.patch(f"{BASE}/admin/vendor-profiles/{vendor}/status",
                         json={"status": "approved", "reason": "TEST ok"}, timeout=30)
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:300]}"
        assert mongo().vendor_profiles.find_one({"_id": ObjectId(vendor)})["status"] == "approved"

    def test_bank_statement_also_satisfies(self, admin, vendor):
        db = mongo()
        db.vendor_documents.delete_many({"vendor_id": vendor, "doc_type": "cancelled_cheque"})
        db.vendor_documents.insert_one({"vendor_id": vendor, "doc_type": "bank_statement",
                                        "path": "/api/files/stmt", "status": "approved", "note": ""})
        r = admin.get(f"{BASE}/admin/vendor-profiles/{vendor}/documents", timeout=30)
        assert r.json()["complete"] is True


# ---------------- agreement banking annexure ----------------
class TestAgreementBanking:
    @pytest.fixture(scope="class")
    def agreement(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items") or []
        if not items:
            pytest.skip("no agreements seeded")
        return items[0]["id"]

    def test_detail_has_banking_rows(self, admin, agreement):
        r = admin.get(f"{BASE}/admin/vendor-agreements/{agreement}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "banking_rows" in body, list(body.keys())
        labels = [row[0] for row in body["banking_rows"]]
        for want in ["Account holder name", "Bank name", "Branch", "Account number",
                     "Account type", "IFSC", "SWIFT / BIC", "UPI ID"]:
            assert want in labels, labels
        text = " ".join(s[0] for s in (body["agreement"].get("sections") or [])) if body["agreement"].get("sections") else ""
        blob = str(body["agreement"])
        assert "Banking and payment transfer details" in blob + text + str(body.get("sections")), "agreement text missing banking section"

    def test_pdf_download(self, admin, agreement):
        r = admin.get(f"{BASE}/vendor-agreements/{agreement}/pdf", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers.get("content-type")
        assert r.content[:4] == b"%PDF" and len(r.content) > 5000
