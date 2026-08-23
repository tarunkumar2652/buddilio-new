"""Iteration 52 — Buddilio logo on generated PDFs (invoice/receipt, pass, vendor agreement, commission)."""
import os

import pymupdf
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
OUT = "/app/test_reports/pytest"

ADMIN = ("admin@buddilio.com", "Admin@123")
PARTNER = ("partner@buddilio.com", "Partner@123")


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=40)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {login(*ADMIN)}"}


@pytest.fixture(scope="module")
def partner_h():
    return {"Authorization": f"Bearer {login(*PARTNER)}"}


def _assert_logo(content: bytes, name: str):
    """Page 1 must carry a raster image anchored top-left, and still hold its text."""
    doc = pymupdf.open(stream=content, filetype="pdf")
    page = doc[0]
    imgs = page.get_image_info()
    assert imgs, f"{name}: no image on page 1 — logo missing"
    top_left = [i for i in imgs if i["bbox"][0] < page.rect.width * 0.35
                and i["bbox"][1] < page.rect.height * 0.2]
    assert top_left, f"{name}: images exist but none top-left: {[i['bbox'] for i in imgs]}"
    logo = top_left[0]["bbox"]
    text = page.get_text()
    assert len(text) > 100, f"{name}: page text looks empty ({len(text)} chars)"
    page.get_pixmap(dpi=110).save(f"{OUT}/i52_{name}.png")
    return logo, text, page


def _no_overlap_with_right_text(logo_bbox, page, name):
    """Nothing from the logo may sit on top of the right-hand receipt/invoice number block."""
    for w in page.get_text("words"):
        x0, y0, x1, y1 = w[:4]
        if x0 > page.rect.width * 0.5 and y1 < page.rect.height * 0.2:
            overlap_x = min(logo_bbox[2], x1) - max(logo_bbox[0], x0)
            overlap_y = min(logo_bbox[3], y1) - max(logo_bbox[1], y0)
            assert not (overlap_x > 1 and overlap_y > 1), \
                f"{name}: logo {logo_bbox} overlaps header text '{w[4]}' at {(x0, y0, x1, y1)}"


class TestOrderInvoicePdf:
    def test_order_invoice_pdf_has_logo(self, admin_h, mongo):
        order = mongo.orders.find_one({"payment_status": {"$in": ["paid", "completed"]}})
        if not order:
            order = mongo.orders.find_one({})
        if not order:
            pytest.skip("no orders in db")
        oid = str(order["_id"])
        r = requests.get(f"{API}/orders/{oid}/invoice.pdf", headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        assert r.headers["content-type"].startswith("application/pdf")
        logo, text, page = _assert_logo(r.content, "order_invoice")
        _no_overlap_with_right_text(logo, page, "order_invoice")
        assert "Buddilio" in text or "BUDDILIO" in text


class TestPassPdf:
    def test_pass_pdf_has_logo(self, admin_h, mongo):
        row = mongo.passes.find_one({"code": {"$exists": True}}) if "passes" in \
            mongo.list_collection_names() else None
        if not row:
            pytest.skip("no passes in db")
        r = requests.get(f"{API}/passes/{row['code']}/pdf", headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        logo, text, page = _assert_logo(r.content, "pass")
        _no_overlap_with_right_text(logo, page, "pass")


class TestAgreementPdf:
    def test_agreement_pdf_endpoint_serves(self, admin_h, mongo):
        """Existing agreements are served from db.agreement_documents (immutable stored copy)."""
        ag = mongo.vendor_agreements.find_one({"status": "active"}) or \
            mongo.vendor_agreements.find_one({})
        if not ag:
            pytest.skip("no vendor agreements in db")
        r = requests.get(f"{API}/vendor-agreements/{str(ag['_id'])}/pdf", headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        doc = pymupdf.open(stream=r.content, filetype="pdf")
        stored = mongo.agreement_documents.count_documents(
            {"agreement_id": str(ag["_id"]), "version": ag.get("version")})
        has_logo = bool(doc[0].get_image_info())
        doc[0].get_pixmap(dpi=110).save(f"{OUT}/i52_agreement_endpoint.png")
        if stored:
            print(f"agreement served from stored copy (pre-logo build); logo present={has_logo}")
        else:
            assert has_logo, "freshly rendered agreement PDF has no logo"

    def test_agreement_pdf_generator_draws_logo(self, mongo):
        """Newly generated agreement PDFs must carry the brand mark."""
        import sys
        sys.path.insert(0, "/app/backend")
        import agreements as agr
        ag = mongo.vendor_agreements.find_one({}) or {}
        if not ag:
            pytest.skip("no vendor agreements in db")
        v = mongo.vendor_profiles.find_one({"_id": ag["vendor_id"]}) if isinstance(
            ag.get("vendor_id"), object) else None
        from bson import ObjectId
        v = v or mongo.vendor_profiles.find_one({"_id": ObjectId(str(ag["vendor_id"]))}) or {}
        sched = mongo.commercial_schedules.find_one(
            {"_id": ObjectId(str(ag["commercial_schedule_id"]))}) or {}
        pdf = agr.agreement_pdf({**ag, "_id": str(ag["_id"])}, {**v, "_id": str(v.get("_id", ""))},
                                {**sched, "_id": str(sched.get("_id", ""))})
        logo, text, page = _assert_logo(bytes(pdf), "agreement_fresh")
        _no_overlap_with_right_text(logo, page, "agreement_fresh")
        assert "VENDOR AGREEMENT" in text


class TestCommissionInvoicePdf:
    def test_commission_invoice_pdf_has_logo(self, admin_h, mongo):
        names = mongo.list_collection_names()
        coll = "vendor_commission_invoices" if "vendor_commission_invoices" in names else None
        inv = mongo[coll].find_one({}) if coll else None
        if not inv:
            pytest.skip("no commission invoices in db")
        r = requests.get(f"{API}/vendor-commission-invoices/{str(inv['_id'])}/pdf",
                         headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        logo, text, page = _assert_logo(r.content, "commission")
        _no_overlap_with_right_text(logo, page, "commission")
