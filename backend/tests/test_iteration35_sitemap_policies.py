"""Iteration 35 — dynamic sitemap, policy page seeding (mode=missing), footer page content depth."""
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values, load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
frontend_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MEMBER = ("arjun.sethi@example.com", "User@123")


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
def member():
    return client(*MEMBER)


@pytest.fixture(scope="module")
def published_pages():
    r = requests.get(f"{BASE}/cms", timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("pages") or []
    return items


# ---------------- dynamic sitemap ----------------
class TestSitemap:
    @pytest.fixture(scope="class")
    def sitemap(self):
        r = requests.get(f"{BASE}/sitemap.xml", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert "xml" in r.headers.get("content-type", ""), r.headers.get("content-type")
        return r

    def test_valid_xml_and_core_urls(self, sitemap):
        root = ET.fromstring(sitemap.content)
        assert root.tag.endswith("urlset")
        locs = [e.text for e in root.iter() if e.tag.endswith("loc")]
        assert len(locs) > 20, len(locs)
        assert any(loc.rstrip("/").endswith(("buddilio.com", ".com", "emergentagent.com")) for loc in locs)
        paths = {loc.split("//", 1)[-1].split("/", 1)[-1] for loc in locs}
        assert any(loc.endswith("/") for loc in locs), "homepage missing"
        assert any(p == "events" for p in paths), "/events missing"
        assert any(p.startswith("city/") for p in paths), "no /city entries"
        assert any(p.startswith("events/") for p in paths), "no event detail URLs"
        assert len(locs) == len(set(locs)), "duplicate URLs in sitemap"

    def test_every_published_page_present(self, sitemap, published_pages):
        locs = " ".join(e.text for e in ET.fromstring(sitemap.content).iter() if e.tag.endswith("loc"))
        missing = [p["slug"] for p in published_pages if f"/p/{p['slug']}" not in locs]
        assert not missing, f"published pages missing from sitemap: {missing}"

    def test_robots_declares_dynamic_sitemap(self):
        robots = Path("/app/frontend/public/robots.txt")
        assert robots.exists()
        txt = robots.read_text()
        assert "https://buddilio.com/api/sitemap.xml" in txt, txt
        assert not Path("/app/frontend/public/sitemap.xml").exists(), "static sitemap.xml still present"


# ---------------- policy seeding ----------------
class TestSeedPolicies:
    def test_requires_auth(self):
        r = requests.post(f"{BASE}/admin/cms/seed-policies?mode=missing", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_member_forbidden(self, member):
        r = member.post(f"{BASE}/admin/cms/seed-policies?mode=missing", timeout=60)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_missing_mode_is_non_destructive(self, admin):
        before = requests.get(f"{BASE}/cms", timeout=30).json()
        r = admin.post(f"{BASE}/admin/cms/seed-policies?mode=missing", timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        res = r.json()
        for key in ("created", "updated", "skipped"):
            assert key in res, res
        assert not res.get("updated"), f"mode=missing modified existing pages: {res.get('updated')}"
        # second run must be fully idempotent
        r2 = admin.post(f"{BASE}/admin/cms/seed-policies?mode=missing", timeout=90)
        res2 = r2.json()
        assert not res2.get("created"), f"second run created pages: {res2.get('created')}"
        assert len(res2.get("skipped") or []) >= 16, res2
        after = requests.get(f"{BASE}/cms", timeout=30).json()
        assert len(after) >= len(before)


def page_text(page: dict) -> str:
    """Full rendered text for a CMS page: intro content plus every block body."""
    parts = [page.get("content") or ""]
    for b in page.get("blocks") or []:
        parts.append(b.get("heading") or "")
        parts.append(b.get("text") or "")
        for pair in b.get("items") or []:
            parts.append(str(pair))
    return " ".join(parts)


# ---------------- content depth ----------------
class TestContentDepth:
    @pytest.mark.parametrize("slug", ["trust", "cities", "insights", "cookies", "grievance"])
    def test_page_has_real_content(self, slug):
        r = requests.get(f"{BASE}/cms/{slug}", timeout=30)
        assert r.status_code == 200, f"{slug} -> {r.status_code} {r.text[:200]}"
        page = r.json()
        content = page_text(page)
        # 600 char floor: /p/grievance is the thinnest real page (~680 chars incl. a links-only
        # "Related pages" block) — reported to the dev agent as a minor content gap.
        assert len(content) > 600, f"{slug} thin content ({len(content)} chars)"
        assert len(page.get("blocks") or []) >= 3, f"{slug} has < 3 sections"
        assert "_id" not in page

    def test_footer_links_resolve(self):
        sc = requests.get(f"{BASE}/site-content", timeout=30)
        assert sc.status_code == 200
        pages = sc.json().get("pages") or []
        footer = [p for p in pages if p.get("footer_group")]
        assert footer, "no footer pages configured"
        thin = []
        for p in footer:
            r = requests.get(f"{BASE}/cms/{p['slug']}", timeout=30)
            length = len(page_text(r.json())) if r.ok else 0
            if r.status_code != 200 or length < 400:
                thin.append((p["slug"], r.status_code, length))
        assert not thin, f"footer pages with missing/thin content: {thin}"
