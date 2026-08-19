"""Iteration 33 (part 2) — amendment re-acceptance with a real OTP.

The OTP hash is read from Mongo and the 6-digit code recovered locally (preview email is blocked for
@example.com), so only ONE API attempt is spent. Verifies: fresh OTP accepted, agreement v1.1 goes
active, immutable acceptance record #2, executed PDF for v1.1, v1 schedule preserved.
"""
import hashlib
import os
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
PARTNER = ("partner@buddilio.com", "Partner@123")


def client(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json().get('access_token') or r.json()['token']}"})
    return s


def recover_code(agreement_id, version):
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    otp = db.agreement_otps.find_one({"agreement_id": agreement_id, "version": version})
    assert otp, "no OTP row stored for the pending agreement"
    for n in range(100000, 1000000):
        if hashlib.sha256(str(n).encode()).hexdigest() == otp["code_hash"]:
            return str(n)
    pytest.fail("could not recover the OTP code")


def test_amendment_acceptance_with_fresh_otp():
    partner = client(*PARTNER)
    ag = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()["agreement"]
    if ag["status"] == "active":
        pytest.skip(f"nothing pending: agreement already active at v{ag['version']}")
    assert ag["status"] == "amendment_pending", ag["status"]

    otp_res = partner.post(f"{BASE}/vendor/agreement/otp", json={"channel": "email"}, timeout=30)
    assert otp_res.status_code == 200, otp_res.text[:300]
    assert otp_res.json()["reference"].startswith("OTP-")
    assert otp_res.json()["sent_to"] == "partner@buddilio.com"

    code = recover_code(ag["id"], ag["version"])
    bad = partner.post(f"{BASE}/vendor/agreement/accept",
                       json={"read_agreement": True, "authorised": True, "accept_commercials": True,
                             "consent_electronic": True, "otp": "111111" if code != "111111" else "222222",
                             "accepted_by": "Test Signatory"}, timeout=30)
    assert bad.status_code == 400 and "not correct" in bad.json()["detail"].lower(), bad.text[:200]

    ok = partner.post(f"{BASE}/vendor/agreement/accept",
                      json={"read_agreement": True, "authorised": True, "accept_commercials": True,
                            "consent_electronic": True, "otp": code,
                            "accepted_by": "Manish Kumar (Vendor)"}, timeout=60)
    assert ok.status_code == 200, ok.text[:300]
    d = ok.json()
    assert d["version"] == ag["version"]
    assert d["method"] == "OTP (email)"
    assert d["document_hash"].startswith("sha256:") and len(d["document_hash"]) > 40

    after = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()
    assert after["agreement"]["status"] == "active"
    assert after["acceptance"]["document_hash"] == d["document_hash"]
    assert after["acceptance"]["ip_address"] and after["acceptance"]["user_agent"]


def test_post_amendment_state():
    partner = client(*PARTNER)
    after = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()
    ag = after["agreement"]
    assert ag["status"] == "active", ag["status"]
    assert ag["version"] >= 1.1, f"amended agreement version is {ag['version']}"
    assert after["acceptance"] and after["acceptance"]["ip_address"] and after["acceptance"]["user_agent"]
    assert after["acceptance"]["otp_reference"].startswith("OTP-")
    hist = partner.get(f"{BASE}/vendor/agreement/history", timeout=30).json()
    assert len(hist["agreements"]) >= 2, "amendment did not create a second agreement record"
    assert len(hist["schedules"]) >= 2, "v1 schedule was not preserved"
    assert len(hist["acceptances"]) >= 2, "second immutable acceptance not recorded"
    assert 1 in [s["version"] for s in hist["schedules"]]

    pdf = partner.get(f"{BASE}/vendor-agreements/{ag['id']}/pdf", timeout=60)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert f"-v{ag['version']}.pdf" in pdf.headers.get("content-disposition", "")

    quote = partner.get(f"{BASE}/pricing/quote",
                        params={"vendor_id": after["vendor"]["id"]}, timeout=30)
    assert quote.status_code == 200, quote.text[:200]
    q = quote.json()["quote"]
    assert q["commercial_schedule_version"] == after["schedule"]["version"], \
        "quote is not using the newly accepted schedule version"
