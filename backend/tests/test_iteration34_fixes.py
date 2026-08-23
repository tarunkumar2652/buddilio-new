"""Iteration 34 — verification of the fixes reported in iteration 33.

FIX 1 pricing quote auth/scoping, FIX 3 admin page update by slug + versions,
FIX 4 sign-up consent recording, FIX 5 pricing-floor API guard, plus light regression.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
MEMBER = ("aarav.mehta@example.com", "User@12345")


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
def vendor_id():
    db = mongo()
    u = db.users.find_one({"email": PARTNER[0]}, {"_id": 1})
    v = db.vendor_profiles.find_one({"user_id": str(u["_id"])}, {"_id": 1, "legal_name": 1})
    assert v, "SMOKE vendor profile missing for partner@buddilio.com"
    return str(v["_id"])


# ---------------- FIX 1: pricing quote is authenticated and scoped ----------------
class TestPricingQuoteScoping:
    def test_anonymous_gets_401(self, vendor_id):
        r = requests.get(f"{BASE}/pricing/quote", params={"vendor_id": vendor_id}, timeout=30)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:300]}"
        assert "vendor_net_rate" not in r.text and "commission" not in r.text

    def test_unrelated_member_gets_403(self, vendor_id):
        r = client(*MEMBER).get(f"{BASE}/pricing/quote", params={"vendor_id": vendor_id}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"
        assert "commission" not in r.text.lower()

    def test_owning_vendor_gets_quote(self, vendor_id):
        r = client(*PARTNER).get(f"{BASE}/pricing/quote", params={"vendor_id": vendor_id}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        q = r.json()["quote"]
        for k in ("vendor_net_rate", "commission", "platform_fee", "tax", "customer_price",
                  "vendor_settlement", "buddilio_earning"):
            assert k in q, f"{k} missing from quote"
        assert q["customer_price"] > q["vendor_net_rate"] > 0
        assert r.json()["settlement_cycle"]

    def test_admin_gets_quote(self, vendor_id):
        admin = client(*ADMIN)
        r = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vendor_id, "quantity": 2}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        q1 = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vendor_id}, timeout=30).json()["quote"]
        assert r.json()["quote"]["customer_price"] == pytest.approx(q1["customer_price"] * 2, rel=0.02)

    def test_bad_vendor_id_404(self):
        r = client(*ADMIN).get(f"{BASE}/pricing/quote", params={"vendor_id": "6500aaaaaaaaaaaaaaaaaaaa"},
                               timeout=30)
        assert r.status_code == 404, r.text[:200]


# ---------------- FIX 3: admin page update accepts a slug ----------------
class TestAdminPageBySlug:
    SLUG = "safety"

    def test_update_by_slug_archives_version(self):
        admin = client(*ADMIN)
        cur = requests.get(f"{BASE}/cms/{self.SLUG}", timeout=30)
        assert cur.status_code == 200, cur.text[:200]
        page = cur.json()
        before_version = int(page.get("policy_version") or 1)
        payload = {"slug": self.SLUG, "title": page["title"], "content": page.get("content", ""),
                   "blocks": page.get("blocks", []), "seo_title": page.get("seo_title", ""),
                   "seo_description": page.get("seo_description", ""),
                   "status": page.get("status", "published"),
                   "nav_footer_group": page.get("nav_footer_group", ""),
                   "nav_label": page.get("nav_label", ""), "order": page.get("order", 0)}
        r = admin.put(f"{BASE}/admin/pages/{self.SLUG}", json=payload, timeout=30)
        assert r.status_code == 200, f"update by slug failed: {r.status_code} {r.text[:400]}"
        assert int(r.json()["policy_version"]) == before_version + 1

        vres = admin.get(f"{BASE}/admin/pages/{self.SLUG}/versions", timeout=30)
        assert vres.status_code == 200, vres.text[:300]
        body = vres.json()
        assert body["current"]["policy_version"] == before_version + 1
        assert any(int(i["version"]) == before_version for i in body["items"]), \
            f"previous version {before_version} not archived: {[i['version'] for i in body['items']]}"
        after = requests.get(f"{BASE}/cms/{self.SLUG}", timeout=30).json()
        assert after["blocks"] and len(after["blocks"]) >= 5, "blocks lost after update"
        assert after.get("last_updated")

    def test_versions_endpoint_requires_staff(self):
        r = client(*MEMBER).get(f"{BASE}/admin/pages/{self.SLUG}/versions", timeout=30)
        assert r.status_code in (401, 403), f"member reached admin versions: {r.status_code}"


# ---------------- FIX 4: sign-up records policy acceptances ----------------
class TestSignupConsents:
    def _payload(self, **over):
        e = f"TEST_i34_{uuid.uuid4().hex[:8]}@example.com"
        body = {"full_name": "TEST Consent User", "email": e, "password": "User@12345",
                "mobile": "+919812345678", "dob": "1993-04-11", "gender": "male", "city": "Delhi",
                "is_adult": True, "accept_terms": True, "accept_privacy": True,
                "accept_guidelines": True}
        body.update(over)
        return body

    def test_all_four_consents_recorded(self):
        body = self._payload()
        r = requests.post(f"{BASE}/auth/register", json=body, timeout=45)
        assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:400]}"
        uid = r.json()["user"]["id"]
        db = mongo()
        rows = list(db.policy_acceptances.find({"user_id": uid}))
        assert rows, "no policy_acceptances rows written at registration"
        slugs = {row.get("slug") for row in rows}
        for expect in ("terms", "privacy", "guidelines"):
            assert expect in slugs, f"missing {expect} acceptance; got {slugs}"
        assert all(row.get("source") == "registration" for row in rows), \
            f"unexpected source values: {[row.get('source') for row in rows]}"
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        pend = s.get(f"{BASE}/policies/pending", timeout=30)
        assert pend.status_code == 200, pend.text[:200]
        assert not pend.json()["items"], f"new member re-prompted for policies: {pend.json()}"

    @pytest.mark.parametrize("flag", ["is_adult", "accept_terms", "accept_privacy", "accept_guidelines"])
    def test_missing_consent_rejected(self, flag):
        r = requests.post(f"{BASE}/auth/register", json=self._payload(**{flag: False}), timeout=30)
        assert r.status_code == 400, f"{flag}=False accepted: {r.status_code}"
        detail = r.json()["detail"].lower()
        assert "accept" in detail or "21" in detail


# ---------------- FIX 5: pricing floor guard on the API ----------------
class TestFloorGuard:
    def test_floor_above_net_rate_rejected(self, vendor_id):
        admin = client(*ADMIN)
        ags = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30)
        assert ags.status_code == 200, ags.text[:200]
        rows = [a for a in ags.json()["items"] if a["vendor_id"] == vendor_id]
        assert rows, "no agreement for the smoke vendor"
        aid = rows[0]["id"]
        bad = {"vendor_net_rate": 1000, "pricing_floor": 1500, "commission_type": "percentage",
               "commission_value": 20, "platform_fee_percent": 10, "tax_percent": 18,
               "settlement_cycle": "T+15", "change_reason": "TEST_i34 floor guard"}
        r = admin.post(f"{BASE}/admin/vendor-agreements/{aid}/amend", json=bad, timeout=30)
        if r.status_code == 200:
            # BUG: the API accepted it. Roll the vendor back so the rest of the suite is unaffected.
            from bson import ObjectId
            db = mongo()
            body = r.json()
            db.commercial_schedules.delete_one({"_id": ObjectId(body["schedule"]["id"])})
            db.vendor_agreements.delete_one({"_id": ObjectId(body["agreement"]["id"])})
            db.vendor_agreements.update_one({"_id": ObjectId(aid)}, {"$set": {"status": "active"}})
        assert r.status_code == 400, f"floor>net accepted: {r.status_code} {r.text[:300]}"
        assert "floor" in r.json()["detail"].lower()

    def test_member_cannot_amend(self):
        r = client(*MEMBER).post(f"{BASE}/admin/vendor-agreements/000000000000000000000000/amend",
                                 json={"vendor_net_rate": 1}, timeout=30)
        assert r.status_code == 403, r.status_code


# ---------------- light regression ----------------
class TestLightRegression:
    def test_ledger_and_invoice_pdf(self):
        m = client(*MEMBER)
        led = m.get(f"{BASE}/me/ledger", timeout=30)
        assert led.status_code == 200, led.text[:300]
        payments = led.json()["payments"]
        assert isinstance(payments, list) and payments, "ledger has no payments for the seeded member"
        paid = [p for p in payments if p["status"] == "paid"]
        assert paid, "no paid rows in ledger"
        pdf = m.get(f"{BASE}/orders/{paid[0]['id']}/invoice.pdf", timeout=60)
        assert pdf.status_code == 200, f"invoice pdf {pdf.status_code} {pdf.text[:200]}"
        assert pdf.content[:4] == b"%PDF", pdf.content[:20]

    def test_membership_plans_dynamic_features(self):
        r = requests.get(f"{BASE}/plans", timeout=30)
        assert r.status_code == 200, r.text[:200]
        plans = r.json().get("items", r.json())
        assert plans
        assert any(p.get("benefits") for p in plans), "no plan exposes benefits/features"
        assert all("price" in p and "duration_days" in p for p in plans)

    def test_rich_text_page_html(self):
        r = requests.get(f"{BASE}/cms/terms", timeout=30)
        assert r.status_code == 200
        page = r.json()
        blob = str(page.get("content", "")) + str(page.get("blocks", ""))
        assert "<" in blob, "terms page has no HTML markup"
        assert "&lt;p&gt;" not in blob, "page HTML looks escaped"
