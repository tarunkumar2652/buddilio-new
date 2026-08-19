"""Iteration 33 — Vendor agreement & dynamic commercial module + website policy/legal pages.

Modules covered:
  * agreements.py pricing engine via /api/admin/pricing/preview and /api/pricing/quote
  * vendor_routes.py vendor self-service, acceptance guards, executed PDF, admin dashboard, audit, RBAC
  * server.py policy pages (CMS), version history, material-change re-acceptance, register consents
"""
import os
import re

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")
AARAV = ("aarav.mehta@example.com", "User@123")
ARJUN = ("arjun.sethi@example.com", "User@123")

POLICY_SLUGS = ["about", "how-it-works", "faq", "guidelines", "safety", "report", "privacy", "terms",
                "refund", "cookies", "vendor-terms", "contact", "grievance", "cities", "insights", "trust"]


def token(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {email}: {r.status_code} {r.text[:300]}")
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if not tok:
        pytest.fail(f"no token in login response: {list(data.keys())}")
    return tok


def client(email, password):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token(email, password)}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return client(*ADMIN)


@pytest.fixture(scope="module")
def partner():
    return client(*PARTNER)


@pytest.fixture(scope="module")
def member():
    return client(*AARAV)


@pytest.fixture(scope="module")
def partner_vendor(partner):
    r = partner.get(f"{BASE}/vendor/profile", timeout=30)
    assert r.status_code == 200, r.text[:300]
    v = r.json().get("vendor")
    assert v, "partner@buddilio.com has no vendor profile (expected SMOKE Vendor LLP)"
    return v


# ---------------- pricing engine ----------------
class TestPricingEngine:
    def base_schedule(self, **over):
        s = {"currency": "INR", "vendor_net_rate": 1000, "pricing_floor": 900,
             "commission_type": "percentage", "commission_value": 20, "commission_fixed": 0,
             "platform_fee_percent": 10, "platform_fee_fixed": 0, "tax_percent": 18,
             "dynamic_pricing_enabled": False, "discount_funding": "buddilio",
             "settlement_cycle": "T+7"}
        s.update(over)
        return s

    def preview(self, cl, schedule, **kw):
        r = cl.post(f"{BASE}/admin/pricing/preview",
                    json={"schedule": schedule, **kw}, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        return r.json()["preview"]

    def test_percentage_commission(self, admin):
        p = self.preview(admin, self.base_schedule())
        assert p["commission"] == 200.0
        base = 1000 + 200
        fee = round(base * 0.10, 2)
        tax = round((base + fee) * 0.18, 2)
        assert p["platform_fee"] == fee
        assert p["tax"] == tax
        assert p["customer_price"] == round(base + fee + tax, 2)
        assert p["vendor_settlement"] == 1000.0
        assert p["buddilio_earning"] == round(200 + fee, 2)

    def test_fixed_commission(self, admin):
        p = self.preview(admin, self.base_schedule(commission_type="fixed", commission_value=150),
                         quantity=3)
        assert p["vendor_net_rate"] == 3000.0
        assert p["commission"] == 450.0, "fixed commission must scale per unit"
        assert p["vendor_settlement"] == 3000.0

    def test_hybrid_commission(self, admin):
        p = self.preview(admin, self.base_schedule(commission_type="hybrid", commission_value=10,
                                                   commission_fixed=50), quantity=2)
        # 10% of 2000 + 50*2
        assert p["commission"] == 300.0
        assert p["vendor_net_rate"] == 2000.0

    def test_settlement_never_below_floor(self, admin):
        p = self.preview(admin, self.base_schedule(discount_funding="vendor", pricing_floor=950),
                         discount=500)
        assert p["discount"] == 500.0
        assert p["vendor_settlement"] == 950.0, "settlement must be floored at the pricing floor"

    def test_dynamic_adjustment_ignored_when_disabled(self, admin):
        off = self.preview(admin, self.base_schedule(dynamic_pricing_enabled=False),
                           dynamic_adjustment=300)
        on = self.preview(admin, self.base_schedule(dynamic_pricing_enabled=True),
                          dynamic_adjustment=300)
        assert off["dynamic_adjustment"] == 0.0
        assert on["dynamic_adjustment"] == 300.0
        assert on["customer_price"] > off["customer_price"]

    def test_quote_for_active_vendor(self, partner_vendor):
        r = requests.get(f"{BASE}/pricing/quote", params={"vendor_id": partner_vendor["id"]}, timeout=30)
        if r.status_code == 404:
            pytest.skip("partner vendor has no active schedule yet")
        assert r.status_code == 200, r.text[:300]
        q = r.json()["quote"]
        for key in ["vendor_net_rate", "commission", "platform_fee", "dynamic_adjustment", "discount",
                    "tax", "customer_price", "vendor_settlement", "commercial_schedule_id",
                    "commercial_schedule_version"]:
            assert key in q, f"missing {key} in quote"
        assert q["vendor_settlement"] >= q["pricing_floor"]
        assert isinstance(q["commercial_schedule_id"], str) and q["commercial_schedule_id"]

    def test_quote_unknown_vendor_404(self, admin):
        r = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": "000000000000000000000000"}, timeout=30)
        assert r.status_code == 404, r.text[:200]

    def test_quote_requires_auth(self):
        """Vendor net rates / floors are commercially sensitive: the quote endpoint should be auth-gated."""
        r = requests.get(f"{BASE}/pricing/quote", params={"vendor_id": "000000000000000000000000"}, timeout=30)
        assert r.status_code in (401, 403), f"unauthenticated quote returned {r.status_code}"


# ---------------- vendor onboarding + validation ----------------
class TestVendorOnboarding:
    def test_meta(self, admin):
        r = admin.get(f"{BASE}/vendor-agreements/meta", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert set(d["commission_types"]) == {"percentage", "fixed", "hybrid"}
        assert d["entity"]["signatory"] == "Manish Kumar"
        assert d["entity"]["msme"] == "UDYAM-HR-05-0203611"
        assert d["default_platform_fee_percent"] == 10

    def test_profile_shape(self, partner_vendor):
        assert partner_vendor.get("legal_name")
        assert "_id" not in partner_vendor and "id" in partner_vendor

    def test_submit_requires_mandatory_fields(self, admin):
        """A vendor created without PAN/address cannot be submitted; message names the gaps."""
        r = admin.post(f"{BASE}/admin/vendor-profiles",
                       json={"legal_name": "TEST_ Incomplete Vendor", "vendor_kind": "organiser",
                             "email": "test_incomplete@example.com"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        vid = r.json()["vendor"]["id"]
        # approving without documents must be refused
        st = admin.patch(f"{BASE}/admin/vendor-profiles/{vid}/status",
                         json={"status": "approved", "reason": "TEST"}, timeout=30)
        assert st.status_code == 400, f"approve without docs returned {st.status_code}"
        assert "document" in st.json()["detail"].lower()
        # schedule cannot be created for a non-approved vendor
        sc = admin.post(f"{BASE}/admin/vendor-profiles/{vid}/commercial-schedule",
                        json={"vendor_net_rate": 100, "pricing_floor": 50, "commission_type": "percentage",
                              "commission_value": 10}, timeout=30)
        assert sc.status_code == 400, sc.text[:200]
        # cleanup
        requests.delete(f"{BASE}/admin/vendor-profiles/{vid}", timeout=10)

    def test_pricing_floor_above_net_rejected(self, admin, partner_vendor):
        r = admin.post(f"{BASE}/admin/vendor-profiles/{partner_vendor['id']}/commercial-schedule",
                       json={"vendor_net_rate": 1000, "pricing_floor": 1500,
                             "commission_type": "percentage", "commission_value": 20}, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"
        assert "floor" in r.json()["detail"].lower()


# ---------------- agreement + acceptance guards ----------------
class TestAgreementAcceptance:
    def test_vendor_agreement_payload(self, partner):
        r = partner.get(f"{BASE}/vendor/agreement", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["agreement"], "no agreement for the smoke vendor"
        assert re.match(r"^BUD-VND-\d{6}$", d["agreement"]["agreement_number"]), \
            d["agreement"]["agreement_number"]
        assert len(d["sections"]) >= 30, f"only {len(d['sections'])} legal sections"
        assert len(d["commercial_rows"]) >= 8
        assert d["entity"]["signatory"] == "Manish Kumar"

    def test_accept_missing_confirmations_400(self, partner):
        r = partner.post(f"{BASE}/vendor/agreement/accept",
                         json={"read_agreement": True, "authorised": True, "accept_commercials": False,
                               "consent_electronic": True, "otp": "123456",
                               "accepted_by": "Test Signatory"}, timeout=30)
        assert r.status_code == 400, r.text[:200]
        assert "four confirmations" in r.json()["detail"].lower()

    def test_history_and_acceptance_record(self, partner):
        r = partner.get(f"{BASE}/vendor/agreement/history", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["agreements"]) >= 1
        assert len(d["schedules"]) >= 1
        assert len(d["acceptances"]) >= 1, "no immutable acceptance record stored"
        acc = d["acceptances"][0]
        for key in ["ip_address", "user_agent", "otp_reference", "document_hash", "acceptance_method",
                    "accepted_by", "accepted_at", "confirmations"]:
            assert key in acc and acc[key] not in (None, ""), f"acceptance missing {key}"
        assert acc["acceptance_method"] == "otp_email"
        assert acc["locked"] is True

    def test_schedule_versions_preserved(self, partner):
        d = partner.get(f"{BASE}/vendor/agreement/history", timeout=30).json()
        versions = sorted(s["version"] for s in d["schedules"])
        assert versions == sorted(set(versions)), "duplicate schedule versions"
        assert versions[0] == 1, "v1 must be preserved"


# ---------------- executed PDF ----------------
class TestExecutedPdf:
    @pytest.fixture(scope="class")
    def agreement_id(self, partner):
        d = partner.get(f"{BASE}/vendor/agreement", timeout=30).json()
        return d["agreement"]["id"], d["agreement"]["agreement_number"], d["agreement"]["version"]

    def test_vendor_can_download(self, partner, agreement_id):
        aid, number, version = agreement_id
        r = partner.get(f"{BASE}/vendor-agreements/{aid}/pdf", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("application/pdf")
        assert f"{number}-v{version}.pdf" in r.headers.get("content-disposition", "")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 5000

    def test_admin_can_download(self, admin, agreement_id):
        aid, _, _ = agreement_id
        r = admin.get(f"{BASE}/vendor-agreements/{aid}/pdf", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"

    def test_other_member_403(self, member, agreement_id):
        aid, _, _ = agreement_id
        r = member.get(f"{BASE}/vendor-agreements/{aid}/pdf", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"

    def test_anonymous_401(self, agreement_id):
        aid, _, _ = agreement_id
        r = requests.get(f"{BASE}/vendor-agreements/{aid}/pdf", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- admin dashboard + audit ----------------
class TestAdminDashboardAudit:
    def test_agreements_list(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        assert items, "no agreements listed"
        row = items[0]
        for key in ["agreement_number", "version", "status", "vendor", "schedule", "commission_label"]:
            assert key in row, f"missing {key}"
        assert "agreement_text" not in row, "full legal text should not bloat the list payload"
        assert "_id" not in row

    def test_agreement_detail_and_audit(self, admin, partner):
        # pick an already-accepted (active) agreement so the acceptance record must be present
        hist = partner.get(f"{BASE}/vendor/agreement/history", timeout=30).json()["agreements"]
        active = [a for a in hist if a["status"] in ("active", "superseded") and a.get("accepted_at")]
        assert active, f"no accepted agreement in history: {[a['status'] for a in hist]}"
        aid = active[0]["id"]
        r = admin.get(f"{BASE}/admin/vendor-agreements/{aid}", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["commercial_rows"] and d["sections"]
        assert d["acceptance"], "detail modal has no acceptance record"
        assert d["schedules"], "detail modal has no schedule versions"

        a = admin.get(f"{BASE}/admin/vendor-agreements/{aid}/audit", timeout=30)
        assert a.status_code == 200, a.text[:300]
        actions = {row["action"] for row in a.json()["items"]}
        for expected in ["VENDOR_APPROVED", "COMMERCIAL_SCHEDULE_CREATED", "AGREEMENT_GENERATED",
                         "AGREEMENT_ACCEPTED"]:
            assert expected in actions, f"audit trail missing {expected}: {sorted(actions)}"

    def test_detail_404(self, admin):
        r = admin.get(f"{BASE}/admin/vendor-agreements/000000000000000000000000", timeout=30)
        assert r.status_code == 404, r.status_code


# ---------------- RBAC ----------------
class TestRbac:
    @pytest.mark.parametrize("path", ["/admin/vendor-agreements", "/admin/vendor-profiles"])
    def test_partner_blocked_on_admin(self, partner, path):
        r = partner.get(f"{BASE}{path}", timeout=30)
        assert r.status_code == 403, f"{path} -> {r.status_code}"

    def test_member_blocked_on_admin(self, member):
        r = member.get(f"{BASE}/admin/vendor-agreements", timeout=30)
        assert r.status_code == 403, r.status_code

    def test_partner_cannot_amend(self, partner, admin):
        aid = admin.get(f"{BASE}/admin/vendor-agreements", timeout=30).json()["items"][0]["id"]
        r = partner.post(f"{BASE}/admin/vendor-agreements/{aid}/amend",
                         json={"vendor_net_rate": 1, "pricing_floor": 0,
                               "commission_type": "percentage", "commission_value": 5}, timeout=30)
        assert r.status_code == 403, r.status_code

    def test_member_vendor_endpoints(self, member):
        for path in ["/vendor/profile", "/vendor/agreement", "/vendor/commercial-terms",
                     "/vendor/settlements"]:
            r = member.get(f"{BASE}{path}", timeout=30)
            if path == "/vendor/profile":
                assert r.status_code == 200 and r.json()["vendor"] is None, r.text[:200]
            else:
                assert r.status_code in (403, 404), f"{path} -> {r.status_code} {r.text[:150]}"

    def test_member_cannot_read_other_vendor_settlements(self, member):
        r = member.get(f"{BASE}/vendor/settlements", timeout=30)
        assert r.status_code in (403, 404)


# ---------------- policy pages ----------------
class TestPolicyPages:
    @pytest.mark.parametrize("slug", POLICY_SLUGS)
    def test_page_published_with_seo(self, slug):
        r = requests.get(f"{BASE}/cms/{slug}", timeout=30)
        assert r.status_code == 200, f"/cms/{slug} -> {r.status_code}"
        d = r.json()
        assert d["title"].strip()
        assert d.get("seo_title", "").strip(), f"{slug} has no SEO title"
        assert d.get("seo_description", "").strip(), f"{slug} has no meta description"
        assert d.get("blocks"), f"{slug} has no content blocks"
        assert int(d.get("policy_version") or 0) >= 1, f"{slug} has no policy version"
        assert d.get("last_updated"), f"{slug} has no last-updated date"

    def test_faq_has_expandable_items(self):
        d = requests.get(f"{BASE}/cms/faq", timeout=30).json()
        assert any(b.get("type") == "faq" for b in d["blocks"]), "FAQ page has no faq blocks"

    def test_no_escaped_html_in_text_blocks(self):
        offenders = []
        for slug in POLICY_SLUGS:
            d = requests.get(f"{BASE}/cms/{slug}", timeout=30).json()
            for b in d["blocks"]:
                if b.get("type") in ("heading", "text", "quote") and re.search(r"&lt;|&gt;", str(b)):
                    offenders.append(slug)
        assert not offenders, f"escaped HTML entities leaking in: {set(offenders)}"

    def test_cross_links_present(self):
        expect = {"terms": ["/p/privacy", "/p/refund", "/p/guidelines"],
                  "privacy": ["/p/cookies"],
                  "vendor-terms": ["/vendor/agreement"]}
        for slug, links in expect.items():
            body = requests.get(f"{BASE}/cms/{slug}", timeout=30).text
            missing = [l for l in links if l not in body]
            assert not missing, f"{slug} missing cross-links {missing}"


# ---------------- registration consent ----------------
class TestRegisterConsent:
    def payload(self, email, **over):
        body = {"full_name": "TEST_ Consent User", "email": email, "mobile": "9876500011",
                "password": "User@123", "dob": "1990-05-05", "gender": "male", "city": "Gurugram",
                "is_adult": True, "accept_terms": True, "accept_privacy": True,
                "accept_guidelines": True}
        body.update(over)
        return body

    @pytest.mark.parametrize("flag", ["is_adult", "accept_terms", "accept_privacy", "accept_guidelines"])
    def test_missing_consent_rejected(self, flag):
        r = requests.post(f"{BASE}/auth/register",
                          json=self.payload(f"test_consent_{flag}@example.com", **{flag: False}),
                          timeout=30)
        assert r.status_code == 400, f"{flag} unticked -> {r.status_code}"
        assert "accept" in r.json()["detail"].lower() or "21" in r.json()["detail"]

    def test_full_consent_registers(self):
        email = "test_consent_ok@example.com"
        r = requests.post(f"{BASE}/auth/register", json=self.payload(email), timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        data = r.json()
        assert (data.get("user") or {}).get("email") == email or data.get("access_token")


# ---------------- policy version history + re-acceptance ----------------
class TestPolicyReacceptance:
    def test_material_change_flow(self, admin):
        pages = admin.get(f"{BASE}/admin/pages", timeout=30).json()
        items = pages["items"] if isinstance(pages, dict) else pages
        terms = next(p for p in items if p["slug"] == "terms")
        before_version = int(terms.get("policy_version") or 1)

        body = {k: terms.get(k) for k in ["slug", "title", "content", "blocks", "seo_title",
                                          "seo_description", "status", "nav_header",
                                          "nav_footer_group", "nav_label", "order"]}
        body["material_change"] = True
        r = admin.put(f"{BASE}/admin/pages/{terms['id']}", json=body, timeout=30)
        assert r.status_code == 200, r.text[:300]
        new_version = int(r.json()["policy_version"])
        assert new_version == before_version + 1

        ver = admin.get(f"{BASE}/admin/pages/terms/versions", timeout=30)
        assert ver.status_code == 200, ver.text[:300]
        archived = [v["version"] for v in ver.json()["items"]]
        assert before_version in archived, f"previous version {before_version} not archived: {archived}"

        arjun = client(*ARJUN)
        pend = arjun.get(f"{BASE}/policies/pending", timeout=30)
        assert pend.status_code == 200, pend.text[:300]
        slugs = [p["slug"] for p in pend.json()["items"]]
        assert "terms" in slugs, f"member not asked to re-accept terms: {pend.json()}"

        acc = arjun.post(f"{BASE}/policies/accept", json={"slugs": ["terms"]}, timeout=30)
        assert acc.status_code == 200, acc.text[:300]
        again = arjun.get(f"{BASE}/policies/pending", timeout=30).json()["items"]
        assert "terms" not in [p["slug"] for p in again], "member re-prompted after accepting"

    def test_accept_empty_rejected(self, member):
        r = member.post(f"{BASE}/policies/accept", json={"slugs": []}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_pending_requires_auth(self):
        r = requests.get(f"{BASE}/policies/pending", timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- quick regression ----------------
class TestRegression:
    def test_ledger(self, member, admin):
        r = member.get(f"{BASE}/me/ledger", timeout=30)
        assert r.status_code == 200, r.text[:200]
        a = admin.get(f"{BASE}/admin/ledger", timeout=30)
        assert a.status_code == 200, a.text[:200]

    def test_plans_dynamic(self):
        r = requests.get(f"{BASE}/plans", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"] if isinstance(r.json(), dict) else r.json()
        assert items and any(p.get("benefits") for p in items)
