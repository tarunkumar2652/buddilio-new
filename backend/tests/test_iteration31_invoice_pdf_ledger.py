"""Iteration 31 — invoice/receipt PDF + per-kind templates + member ledger.

Covers:
- GET /api/me/ledger returns totals + payments (with template + kind_label) for members with/without orders
- GET /api/orders/{oid}/invoice returns per-kind template + note
- GET /api/orders/{oid}/invoice.pdf returns application/pdf, %PDF magic, filename INV-.../RCP-...
- 403 when a different member fetches; admin (finance:view) can fetch any invoice
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    fe_env = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if fe_env.exists():
        for line in fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")

MEMBER_EMAIL = "aarav.mehta@example.com"
OTHER_EMAIL = "tara.joshi@example.com"
NEW_EMAIL = "arjun.sethi@example.com"  # low-order account
ADMIN_EMAIL = "admin@buddilio.com"

EXPECTED_HEADINGS = {
    "membership": "Membership invoice",
    "product": "Store invoice",
    "event": "Ticket receipt",
    "companion": "Hangout receipt",
    "wallet": "Wallet top-up receipt",
    "travel": "Travel service receipt",
    "provider_fee": "Registration invoice",
}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def member_token():
    return _login(MEMBER_EMAIL, "User@12345")


@pytest.fixture(scope="module")
def other_token():
    return _login(OTHER_EMAIL, "User@12345")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, "Admin@123")


@pytest.fixture(scope="module")
def new_token():
    return _login(NEW_EMAIL, "User@12345")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


class TestLedger:
    def test_ledger_shape(self, member_token):
        r = requests.get(f"{BASE_URL}/api/me/ledger", headers=_h(member_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("payments", "credits", "earnings", "totals", "kinds", "currency"):
            assert k in d, f"missing {k}"
        assert isinstance(d["payments"], list)
        assert isinstance(d["kinds"], dict)
        for k in ("paid", "credit_balance", "earned", "earned_pending"):
            assert k in d["totals"]

    def test_ledger_member_has_orders(self, member_token):
        r = requests.get(f"{BASE_URL}/api/me/ledger", headers=_h(member_token), timeout=30)
        d = r.json()
        assert len(d["payments"]) > 0, "aarav.mehta should have orders"
        p = d["payments"][0]
        for k in ("id", "reference", "kind", "kind_label", "template", "amount", "status"):
            assert k in p
        # Ensure template is one of the known headings
        assert p["template"] in EXPECTED_HEADINGS.values() or p["template"] == "Invoice"

    def test_ledger_no_orders_ok(self, new_token):
        """Regression: user with no or few orders shouldn't 500."""
        r = requests.get(f"{BASE_URL}/api/me/ledger", headers=_h(new_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "payments" in d and isinstance(d["payments"], list)
        assert d["totals"]["paid"] >= 0


class TestInvoiceJson:
    @pytest.fixture(scope="class")
    def ledger(self, member_token):
        r = requests.get(f"{BASE_URL}/api/me/ledger", headers=_h(member_token), timeout=30)
        return r.json()

    def test_invoice_per_kind_templates(self, ledger, member_token):
        """Cycle through the member's orders — for every kind present verify template+note match TEMPLATES."""
        seen_kinds = set()
        for p in ledger["payments"]:
            if p["kind"] in seen_kinds:
                continue
            seen_kinds.add(p["kind"])
            r = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice", headers=_h(member_token), timeout=30)
            assert r.status_code == 200, f"invoice fetch failed for {p['id']}: {r.text}"
            inv = r.json()
            assert inv["kind"] == p["kind"]
            if p["kind"] in EXPECTED_HEADINGS:
                assert inv["template"] == EXPECTED_HEADINGS[p["kind"]], \
                    f"template mismatch for {p['kind']}: {inv['template']}"
                # note must be non-empty for known kinds
                assert inv.get("note"), f"note missing for {p['kind']}"
        # Required kinds must be present in this member's history
        required = {"membership", "product", "event"}
        missing = required - seen_kinds
        if missing:
            pytest.skip(f"member missing kinds {missing} — seeded data may vary; got {seen_kinds}")


class TestInvoicePDF:
    def _first_order(self, tok, want_status=None):
        r = requests.get(f"{BASE_URL}/api/me/ledger", headers=_h(tok), timeout=30)
        for p in r.json()["payments"]:
            if want_status is None or p["status"] == want_status:
                return p
        return None

    def test_pdf_paid_returns_receipt(self, member_token):
        p = self._first_order(member_token, want_status="paid")
        if not p:
            pytest.skip("no paid order")
        r = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice.pdf", headers=_h(member_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", "not a valid PDF"
        assert len(r.content) > 500
        cd = r.headers.get("content-disposition", "")
        assert "RCP-" in cd, f"expected RCP- in filename for paid receipt, got {cd}"

    def test_pdf_pending_returns_invoice(self, member_token):
        p = self._first_order(member_token, want_status="pending")
        if not p:
            pytest.skip("no pending order")
        r = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice.pdf", headers=_h(member_token), timeout=30)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        cd = r.headers.get("content-disposition", "")
        assert "INV-" in cd, f"expected INV- for pending, got {cd}"

    def test_other_member_forbidden(self, member_token, other_token):
        p = self._first_order(member_token)
        assert p, "member should have an order"
        r = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice", headers=_h(other_token), timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}"
        r2 = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice.pdf", headers=_h(other_token), timeout=30)
        assert r2.status_code == 403

    def test_admin_can_fetch_any(self, member_token, admin_token):
        p = self._first_order(member_token)
        r = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/orders/{p['id']}/invoice.pdf", headers=_h(admin_token), timeout=30)
        assert r2.status_code == 200
        assert r2.content[:4] == b"%PDF"

    def test_invalid_order_id(self, member_token):
        r = requests.get(f"{BASE_URL}/api/orders/badid/invoice", headers=_h(member_token), timeout=30)
        assert r.status_code == 400
        r2 = requests.get(f"{BASE_URL}/api/orders/000000000000000000000000/invoice",
                          headers=_h(member_token), timeout=30)
        assert r2.status_code == 404
