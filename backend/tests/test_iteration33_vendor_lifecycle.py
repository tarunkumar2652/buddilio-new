"""Iteration 33 (part 3) — isolated vendor lifecycle: approve → schedule v1 → agreement → suspend →
terminate, proving history is closed and never deleted. Uses a throwaway TEST_ vendor; documents are
seeded directly in Mongo because upload is a vendor-side action.
"""
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
SCHEDULE = {"vendor_net_rate": 1200, "pricing_floor": 1000, "commission_type": "hybrid",
            "commission_value": 15, "commission_fixed": 50, "platform_fee_percent": 10,
            "tax_percent": 18, "settlement_cycle": "T+7", "currency": "INR",
            "cancellation_policy": "TEST policy"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json().get('access_token') or r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def vendor(admin, db):
    r = admin.post(f"{BASE}/admin/vendor-profiles",
                   json={"legal_name": "TEST_ Lifecycle Vendor", "vendor_kind": "travel_provider",
                         "contact_person": "TEST Person", "email": "test_lifecycle@example.com",
                         "pan": "AAAPZ1234C", "registered_address": "Gurugram",
                         "service_category": "Travel"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    vid = r.json()["vendor"]["id"]
    for doc_type in ("pan", "bank_proof", "address_proof"):
        db.vendor_documents.insert_one({"vendor_id": vid, "doc_type": doc_type, "path": "test.pdf",
                                        "status": "approved", "note": "", "uploaded_at": "2026-01-01"})
    yield vid
    db.vendor_documents.delete_many({"vendor_id": vid})
    ags = list(db.vendor_agreements.find({"vendor_id": vid}, {"_id": 1}))
    aids = [str(a["_id"]) for a in ags]
    db.agreement_documents.delete_many({"agreement_id": {"$in": aids}})
    db.agreement_acceptances.delete_many({"vendor_id": vid})
    db.vendor_agreements.delete_many({"vendor_id": vid})
    db.commercial_schedules.delete_many({"vendor_id": vid})
    db.vendor_profiles.delete_one({"_id": ObjectId(vid)})


def test_approve_then_publish_schedule_and_agreement(admin, vendor):
    st = admin.patch(f"{BASE}/admin/vendor-profiles/{vendor}/status",
                     json={"status": "approved", "reason": "TEST docs verified"}, timeout=30)
    assert st.status_code == 200, st.text[:300]

    r = admin.post(f"{BASE}/admin/vendor-profiles/{vendor}/commercial-schedule", json=SCHEDULE, timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["schedule"]["version"] == 1 and d["schedule"]["status"] == "pending"
    ag = d["agreement"]
    assert ag["status"] == "pending_vendor_acceptance"
    assert ag["agreement_number"].startswith("BUD-VND-") and len(ag["agreement_number"]) == 14
    assert ag["version"] == 1.0
    assert ag["document_hash"].startswith("sha256:")

    detail = admin.get(f"{BASE}/admin/vendor-agreements/{ag['id']}", timeout=30)
    assert detail.status_code == 200
    dd = detail.json()
    assert dd["acceptance"] is None, "unaccepted agreement must not have an acceptance record"
    assert len(dd["sections"]) >= 30
    labels = [row[0] if isinstance(row, (list, tuple)) else row for row in dd["commercial_rows"]]
    assert any("commission" in str(l).lower() for l in labels)


def test_amend_creates_v2_with_change_list(admin, vendor):
    ags = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30).json()["items"]
    ag = next(a for a in ags if a["vendor"] and a["vendor"]["legal_name"] == "TEST_ Lifecycle Vendor")
    payload = dict(SCHEDULE, vendor_net_rate=1500, commission_value=20, settlement_cycle="T+15",
                   change_reason="TEST amendment")
    r = admin.post(f"{BASE}/admin/vendor-agreements/{ag['id']}/amend", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["schedule"]["version"] == 2
    assert d["agreement"]["version"] == 1.1
    assert d["agreement"]["status"] == "amendment_pending"
    assert d["material"] is True
    fields = {c["field"]: (c["from"], c["to"]) for c in d["changes"]}
    assert fields["vendor_net_rate"][1] in (1500, 1500.0)
    assert fields["commission_value"][1] in (20, 20.0)
    assert fields["settlement_cycle"] == ("T+7", "T+15")
    # v1 preserved
    scheds = admin.get(f"{BASE}/admin/vendor-agreements/{d['agreement']['id']}", timeout=30).json()["schedules"]
    assert sorted(s["version"] for s in scheds) == [1, 2]


def test_suspend_then_terminate_keeps_history(admin, vendor, db):
    ags = [a for a in admin.get(f"{BASE}/admin/vendor-agreements", timeout=30).json()["items"]
           if a["vendor"] and a["vendor"]["legal_name"] == "TEST_ Lifecycle Vendor"]
    assert len(ags) == 2, f"expected 2 agreement records, got {len(ags)}"
    latest = max(ags, key=lambda a: a["version"])

    s = admin.post(f"{BASE}/admin/vendor-agreements/{latest['id']}/suspend",
                   json={"reason": "compliance", "note": "TEST suspend"}, timeout=30)
    assert s.status_code == 200, s.text[:300]
    assert admin.get(f"{BASE}/admin/vendor-agreements/{latest['id']}",
                     timeout=30).json()["agreement"]["status"] == "suspended"

    t = admin.post(f"{BASE}/admin/vendor-agreements/{latest['id']}/terminate",
                   json={"reason": "vendor_request", "note": "TEST terminate"}, timeout=30)
    assert t.status_code == 200, t.text[:300]
    after = admin.get(f"{BASE}/admin/vendor-agreements/{latest['id']}", timeout=30).json()
    assert after["agreement"]["status"] == "terminated"
    assert after["agreement"]["termination_reason"] == "vendor_request"
    assert after["vendor"]["status"] == "terminated"
    assert len(after["schedules"]) == 2, "schedule history must survive termination"
    assert db.vendor_agreements.count_documents({"vendor_id": vendor}) == 2

    audit = admin.get(f"{BASE}/admin/vendor-agreements/{latest['id']}/audit", timeout=30).json()["items"]
    actions = {a["action"] for a in audit}
    for expected in ["VENDOR_CREATED", "VENDOR_APPROVED", "COMMERCIAL_SCHEDULE_CREATED",
                     "AGREEMENT_GENERATED", "COMMERCIAL_SCHEDULE_CHANGED", "AGREEMENT_SUSPENDED",
                     "AGREEMENT_TERMINATED"]:
        assert expected in actions, f"audit missing {expected}: {sorted(actions)}"

    # quote must stop resolving once the schedule is closed
    q = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vendor}, timeout=30)
    assert q.status_code == 404, f"terminated vendor still quotable: {q.status_code} {q.text[:200]}"


def test_terminate_unknown_agreement_404(admin):
    r = admin.post(f"{BASE}/admin/vendor-agreements/000000000000000000000000/terminate",
                   json={"reason": "other", "note": ""}, timeout=30)
    assert r.status_code == 404, r.status_code
