"""Iteration 41 — built-in captcha, Buddilio Pass (QR voucher), cancellation/refund rules,
simulated-payment block. Seeds paid orders directly in Mongo (no real gateway charge)."""
import os
import re
import time
import uuid

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

MEMBER = {"email": "arjun.sethi@example.com", "password": "User@12345"}
ADMIN = {"email": "admin@buddilio.com", "password": "Admin@123"}

WORDS_RE = re.compile(r"[“\"']([A-Za-z]+)[”\"']")


def solve(question: str) -> str:
    """Solves the three built-in challenge styles."""
    m = re.search(r"What is (\d+) \+ (\d+)", question)
    if m:
        return str(int(m.group(1)) + int(m.group(2)))
    w = WORDS_RE.search(question)
    if "How many letters" in question and w:
        return str(len(w.group(1)))
    if "last four letters" in question and w:
        return w.group(1)[-4:]
    raise AssertionError(f"Unknown captcha style: {question}")


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def captcha(s):
    r = s.get(f"{API}/captcha", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    return d["captcha_id"], solve(d["question"])


def token(s, creds):
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        # progressive captcha may be armed from earlier attempts
        cid, ans = captcha(s)
        r = s.post(f"{API}/auth/login", json={**creds, "captcha_id": cid, "captcha_answer": ans},
                   timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:300]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def member_h(s):
    return {"Authorization": f"Bearer {token(requests.Session(), MEMBER)}"}


@pytest.fixture(scope="session")
def admin_h(s):
    return {"Authorization": f"Bearer {token(requests.Session(), ADMIN)}"}


# ---------------- captcha endpoint ----------------
class TestCaptcha:
    def test_captcha_endpoint(self, s):
        r = s.get(f"{API}/captcha", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("captcha_id"), str) and len(d["captcha_id"]) > 10
        assert isinstance(d.get("question"), str) and d["question"]
        assert "answer" not in str(d).lower().replace("captcha_answer", "")
        assert solve(d["question"])

    def test_captcha_ids_unique(self, s):
        a = s.get(f"{API}/captcha", timeout=30).json()["captcha_id"]
        b = s.get(f"{API}/captcha", timeout=30).json()["captcha_id"]
        assert a != b


def reg_payload(**kw):
    body = {
        "full_name": "TEST Captcha User", "email": f"test_cap_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@12345", "mobile": "9876500011", "dob": "1990-05-05", "gender": "male",
        "city": "Mumbai", "is_adult": True, "accept_terms": True, "accept_privacy": True,
        "accept_guidelines": True, "interests": [], "event_categories": [], "lifestyle": [],
    }
    body.update(kw)
    return body


# ---------------- register guard ----------------
class TestRegisterGuard:
    created = []

    def test_wrong_captcha_rejected(self, s):
        cid, _ = captcha(s)
        r = s.post(f"{API}/auth/register",
                   json=reg_payload(captcha_id=cid, captcha_answer="99999"), timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "verification" in r.json()["detail"].lower()

    def test_empty_captcha_rejected(self, s):
        r = s.post(f"{API}/auth/register", json=reg_payload(), timeout=30)
        assert r.status_code == 400
        assert "verification" in r.json()["detail"].lower()

    def test_honeypot_rejected(self, s):
        cid, ans = captcha(s)
        r = s.post(f"{API}/auth/register",
                   json=reg_payload(captcha_id=cid, captcha_answer=ans, website="http://spam.io"),
                   timeout=30)
        assert r.status_code == 400
        assert "automated" in r.json()["detail"].lower()

    def test_register_success_and_captcha_single_use(self, s, mongo):
        cid, ans = captcha(s)
        body = reg_payload(captcha_id=cid, captcha_answer=ans)
        r = s.post(f"{API}/auth/register", json=body, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["access_token"] and d["user"]["email"] == body["email"]
        assert "password_hash" not in d["user"] and "_id" not in d["user"]
        TestRegisterGuard.created.append(body["email"])
        assert mongo.users.find_one({"email": body["email"]}) is not None
        # replaying the same captcha id must fail (single-use)
        again = s.post(f"{API}/auth/register",
                       json=reg_payload(captcha_id=cid, captcha_answer=ans), timeout=30)
        assert again.status_code in (400, 429), "used captcha must not be replayable"
        if again.status_code == 400:
            assert "expired" in again.json()["detail"].lower() or \
                   "verification" in again.json()["detail"].lower()

    @classmethod
    def teardown_class(cls):
        c = MongoClient(MONGO_URL)
        for email in cls.created:
            c[DB_NAME].users.delete_many({"email": email})
        c.close()


# ---------------- login guard ----------------
class TestLoginGuard:
    def test_clean_login_needs_no_captcha(self):
        sess = requests.Session()
        r = sess.post(f"{API}/auth/login", json=MEMBER, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["access_token"]
        assert any(c.name == "access_token" for c in sess.cookies), "httpOnly cookie not set"

    def test_progressive_captcha_after_failures(self, mongo):
        sess = requests.Session()
        email = MEMBER["email"]
        mongo.login_attempts.delete_many({"identifier": f"email:{email}"})
        for _ in range(2):
            bad = sess.post(f"{API}/auth/login", json={"email": email, "password": "Nope@123"},
                            timeout=30)
            assert bad.status_code in (400, 401), bad.text[:200]
        # third attempt now requires the challenge
        r = sess.post(f"{API}/auth/login", json=MEMBER, timeout=30)
        assert r.status_code == 400, f"expected captcha demand, got {r.status_code}"
        assert "verification" in r.json()["detail"].lower()
        cid, ans = captcha(sess)
        ok = sess.post(f"{API}/auth/login", json={**MEMBER, "captcha_id": cid, "captcha_answer": ans},
                       timeout=30)
        assert ok.status_code == 200, ok.text[:300]
        assert mongo.login_attempts.find_one({"identifier": f"email:{email}"}) is None

    def test_wrong_password_still_401_with_valid_captcha(self, mongo):
        sess = requests.Session()
        email = MEMBER["email"]
        mongo.login_attempts.delete_many({"identifier": f"email:{email}"})
        for _ in range(2):
            sess.post(f"{API}/auth/login", json={"email": email, "password": "Nope@123"}, timeout=30)
        cid, ans = captcha(sess)
        r = sess.post(f"{API}/auth/login",
                      json={"email": email, "password": "StillWrong@1", "captcha_id": cid,
                            "captcha_answer": ans}, timeout=30)
        assert r.status_code == 401, r.text[:200]
        mongo.login_attempts.delete_many({"identifier": f"email:{email}"})


# ---------------- payment safety ----------------
class TestPaymentSafety:
    def test_simulated_verify_blocked(self, member_h):
        r = requests.post(f"{API}/payments/verify", headers=member_h,
                          json={"order_id": "68000000000000000000abcd", "simulate": "success"},
                          timeout=30)
        assert r.status_code == 400, r.text[:300]
        assert "Simulated payments are disabled" in r.json()["detail"]

    def test_config_reports_simulation_off(self):
        r = requests.get(f"{API}/payments/config", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["simulation_enabled"] is False
        assert d["paypal_enabled"] is True

    def test_no_public_route_marks_paid(self, member_h, mongo):
        """Sanity: a pending order cannot be flipped to paid through user-facing routes."""
        member = mongo.users.find_one({"email": MEMBER["email"]})
        oid = mongo.orders.insert_one({
            "order_no": "TESTPAY" + uuid.uuid4().hex[:5].upper(), "user_id": str(member["_id"]),
            "user_email": MEMBER["email"], "kind": "product", "ref_id": "", "item_name": "TEST_probe",
            "quantity": 1, "subtotal": 100.0, "discount": 0.0, "tax": 0.0, "total": 100.0,
            "currency": "USD", "charge_total": 100.0, "payment_status": "pending",
            "order_status": "created", "refund_status": "none", "gateway": "paypal",
            "transaction_id": "", "created_at": "2026-07-01T00:00:00+00:00"}).inserted_id
        try:
            for path, body in [("/payments/verify", {"order_id": str(oid), "simulate": "success"}),
                               (f"/orders/{oid}/mark-paid", {}),
                               (f"/payments/mock/{oid}", {})]:
                r = requests.post(f"{API}{path}", headers=member_h, json=body, timeout=30)
                assert r.status_code >= 400, f"{path} unexpectedly succeeded: {r.text[:200]}"
            assert mongo.orders.find_one({"_id": oid})["payment_status"] == "pending"
        finally:
            mongo.orders.delete_one({"_id": oid})


# ---------------- pass issuance / verification / redemption ----------------
def seed_paid_order(mongo, kind="product", total=200.0, item="TEST_pass_item"):
    member = mongo.users.find_one({"email": MEMBER["email"]})
    oid = mongo.orders.insert_one({
        "order_no": "TESTP" + uuid.uuid4().hex[:6].upper(), "user_id": str(member["_id"]),
        "user_email": MEMBER["email"], "kind": kind, "ref_id": "", "item_name": item,
        "quantity": 2, "subtotal": total, "discount": 0.0, "tax": 0.0, "total": total,
        "currency": "USD", "charge_total": total, "base_currency": "INR",
        "payment_status": "paid", "order_status": "completed", "refund_status": "none",
        "gateway": "paypal", "transaction_id": "TESTTXN" + uuid.uuid4().hex[:6],
        "created_at": "2026-07-01T00:00:00+00:00", "paid_at": "2026-07-01T00:00:00+00:00"}).inserted_id
    return str(oid)


class TestPasses:
    order_ids = []

    def _pass_for(self, mongo, admin_h, oid):
        r = requests.post(f"{API}/admin/passes/backfill", headers=admin_h, timeout=120)
        assert r.status_code == 200, r.text[:300]
        doc = mongo.passes.find_one({"order_id": oid})
        assert doc, "no pass issued for paid order"
        return doc

    def test_pass_issued_for_paid_order(self, mongo, admin_h, member_h):
        oid = seed_paid_order(mongo)
        TestPasses.order_ids.append(oid)
        doc = self._pass_for(mongo, admin_h, oid)
        assert re.fullmatch(r"BUD-[A-Z2-9]{4}-\d{2}", doc["code"]), doc["code"]
        assert doc["status"] == "valid"
        mine = requests.get(f"{API}/me/passes", headers=member_h, timeout=30)
        assert mine.status_code == 200
        codes = [p["code"] for p in mine.json()["items"]]
        assert doc["code"] in codes
        item = next(p for p in mine.json()["items"] if p["code"] == doc["code"])
        assert "_id" not in item and item["item_name"] == "TEST_pass_item"

    def test_qr_and_pdf(self, mongo, admin_h, member_h):
        oid = seed_paid_order(mongo)
        TestPasses.order_ids.append(oid)
        code = self._pass_for(mongo, admin_h, oid)["code"]
        qr = requests.get(f"{API}/passes/{code}/qr.png", timeout=30)
        assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
        assert qr.content[:4] == b"\x89PNG"
        pdf = requests.get(f"{API}/passes/{code}/pdf", headers=member_h, timeout=60)
        assert pdf.status_code == 200, pdf.text[:200]
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF" and len(pdf.content) > 2000
        # other member's pass must not download
        anon = requests.get(f"{API}/passes/{code}/pdf", timeout=30)
        assert anon.status_code in (401, 403)

    def test_check_and_single_redeem(self, mongo, admin_h):
        oid = seed_paid_order(mongo)
        TestPasses.order_ids.append(oid)
        code = self._pass_for(mongo, admin_h, oid)["code"]
        chk = requests.get(f"{API}/passes/{code}/check", timeout=30)
        assert chk.status_code == 200
        d = chk.json()
        assert d["found"] is True and d["status"] == "valid"
        assert d["item_name"] == "TEST_pass_item" and d["quantity"] == 2
        r1 = requests.post(f"{API}/passes/{code}/redeem", headers=admin_h, timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json()["pass"]["status"] == "redeemed"
        assert r1.json()["pass"]["redeemed_by_name"]
        r2 = requests.post(f"{API}/passes/{code}/redeem", headers=admin_h, timeout=30)
        assert r2.status_code == 400, r2.text[:200]
        assert "already used" in r2.json()["detail"].lower()
        after = requests.get(f"{API}/passes/{code}/check", timeout=30).json()
        assert after["status"] == "redeemed" and after["redeemed_at"]

    def test_unknown_code(self, admin_h):
        chk = requests.get(f"{API}/passes/BUD-ZZZZ-00/check", timeout=30)
        assert chk.status_code == 200 and chk.json() == {"found": False}
        red = requests.post(f"{API}/passes/GARBAGE123/redeem", headers=admin_h, timeout=30)
        assert red.status_code == 404

    def test_cancelled_pass_is_void(self, mongo, admin_h, member_h):
        oid = seed_paid_order(mongo)
        TestPasses.order_ids.append(oid)
        code = self._pass_for(mongo, admin_h, oid)["code"]
        cancel = requests.post(f"{API}/me/orders/{oid}/cancel", headers=member_h,
                               json={"reason": "TEST"}, timeout=30)
        assert cancel.status_code == 200, cancel.text[:300]
        chk = requests.get(f"{API}/passes/{code}/check", timeout=30).json()
        assert chk["status"] == "void", chk
        red = requests.post(f"{API}/passes/{code}/redeem", headers=admin_h, timeout=30)
        assert red.status_code == 400
        assert "void" in red.json()["detail"].lower() or "cancel" in red.json()["detail"].lower()

    @classmethod
    def teardown_class(cls):
        c = MongoClient(MONGO_URL)
        db = c[DB_NAME]
        from bson import ObjectId
        for oid in cls.order_ids:
            db.passes.delete_many({"order_id": oid})
            db.orders.delete_one({"_id": ObjectId(oid)})
        c.close()


# ---------------- cancellation & refund rules ----------------
class TestCancellationRefund:
    order_ids = []

    def test_quote_minimum_deduction(self, mongo, member_h):
        oid = seed_paid_order(mongo, total=500.0)
        TestCancellationRefund.order_ids.append(oid)
        r = requests.get(f"{API}/me/orders/{oid}/cancellation-quote", headers=member_h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["deduction_percent"] >= 30, d
        assert d["refundable"] <= 500.0 * 0.7 + 0.01
        assert d["cancellable"] is True
        assert d["credit_option"] >= d["refundable"]

    def test_membership_non_refundable(self, mongo, member_h):
        oid = seed_paid_order(mongo, kind="membership", total=99.0)
        TestCancellationRefund.order_ids.append(oid)
        q = requests.get(f"{API}/me/orders/{oid}/cancellation-quote", headers=member_h,
                         timeout=30).json()
        assert q["deduction_percent"] == 100 and q["refundable"] == 0.0
        assert "non-refundable" in q["reason"].lower()

    def test_member_cannot_trigger_admin_refund(self, mongo, member_h):
        oid = seed_paid_order(mongo, total=120.0)
        TestCancellationRefund.order_ids.append(oid)
        r = requests.post(f"{API}/admin/orders/{oid}/refund", headers=member_h,
                          json={"amount": 120.0, "reason": "TEST"}, timeout=30)
        assert r.status_code == 403, f"member got {r.status_code}: {r.text[:200]}"
        s = requests.post(f"{API}/admin/orders/{oid}/settle-cancellation", headers=member_h,
                          json={"amount": 50.0}, timeout=30)
        assert s.status_code == 403
        assert mongo.orders.find_one({"_id": __import__("bson").ObjectId(oid)})[
            "refund_status"] == "none"

    def test_cancel_then_admin_sees_it_and_credit_settlement(self, mongo, member_h, admin_h):
        oid = seed_paid_order(mongo, total=400.0)
        TestCancellationRefund.order_ids.append(oid)
        c = requests.post(f"{API}/me/orders/{oid}/cancel", headers=member_h,
                          json={"reason": "TEST plans changed", "prefer": "credit"}, timeout=30)
        assert c.status_code == 200, c.text[:300]
        cn = c.json()["cancellation"]
        assert cn["status"] == "requested" and cn["deduction_percent"] >= 30
        dup = requests.post(f"{API}/me/orders/{oid}/cancel", headers=member_h, json={}, timeout=30)
        assert dup.status_code == 400 and "already cancelled" in dup.json()["detail"].lower()
        lst = requests.get(f"{API}/admin/cancellations", headers=admin_h, timeout=30)
        assert lst.status_code == 200
        assert oid in [i["id"] for i in lst.json()["items"]], "cancellation missing from admin queue"
        over = requests.post(f"{API}/admin/orders/{oid}/settle-cancellation", headers=admin_h,
                             json={"amount": 9999.0}, timeout=30)
        assert over.status_code == 400
        settle = requests.post(f"{API}/admin/orders/{oid}/settle-cancellation", headers=admin_h,
                               json={"amount": cn["refundable"], "as_credit": True,
                                     "note": "TEST credit"}, timeout=60)
        assert settle.status_code == 200, settle.text[:300]
        st = settle.json()["cancellation"]
        assert st["status"] == "settled" and st["method"] == "credit"
        assert abs(st["settled_amount"] - cn["refundable"]) < 0.01
        time.sleep(0.5)
        fresh = mongo.orders.find_one({"_id": __import__("bson").ObjectId(oid)})
        assert fresh["refund_status"] == "credited"

    @classmethod
    def teardown_class(cls):
        c = MongoClient(MONGO_URL)
        db = c[DB_NAME]
        from bson import ObjectId
        for oid in cls.order_ids:
            db.passes.delete_many({"order_id": oid})
            db.orders.delete_one({"_id": ObjectId(oid)})
        db.credits.delete_many({"note": {"$regex": "TESTP"}}) if "credits" in db.list_collection_names() else None
        c.close()
