"""Iteration 4 tests: PWA endpoints + review moderation + organiser reply API."""
import os, requests, pytest, uuid
BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lifestyle-connect-17.preview.emergentagent.com").rstrip("/")

def login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

def H(tok): return {"Authorization": f"Bearer {tok}"}

# ---------- PWA static assets ----------
@pytest.mark.parametrize("path", [
    "/manifest.json","/sw.js","/offline.html",
    "/icons/icon-192.png","/icons/icon-512.png",
    "/icons/maskable-192.png","/icons/maskable-512.png",
])
def test_pwa_assets_200(path):
    r = requests.get(f"{BASE}{path}", timeout=10)
    assert r.status_code == 200, f"{path} -> {r.status_code}"

def test_manifest_valid_json():
    m = requests.get(f"{BASE}/manifest.json", timeout=10).json()
    assert m["name"].startswith("Buddilio")
    assert m["display"] == "standalone"
    sizes = {i["sizes"] for i in m["icons"]}
    assert "192x192" in sizes and "512x512" in sizes
    assert any(i.get("purpose") == "maskable" for i in m["icons"])

# ---------- helpers to locate finished event and a foreign review ----------
ROOFTOP_ID = "6a7b73e34a13de566dbd110f"
SUPPER_ID  = "6a7b73e34a13de566dbd112c"

def find_rooftop_event(tok):
    return ROOFTOP_ID

# ---------- Report review ----------
def test_report_review_flow():
    tok = login("tara.joshi@example.com", "User@123")
    ev_id = find_rooftop_event(tok)
    assert ev_id
    r = requests.get(f"{BASE}/api/events/{ev_id}/reviews", headers=H(tok), timeout=15)
    body = r.json()
    revs = body.get("items", body if isinstance(body,list) else [])
    assert isinstance(revs, list) and len(revs) > 0
    foreign = [r for r in revs if not r.get("mine")]
    if not foreign:
        pytest.skip("No foreign reviews to report")
    rid = foreign[0]["id"]
    r1 = requests.post(f"{BASE}/api/reviews/{rid}/report",
        headers=H(tok), json={"reason":"spam"}, timeout=15)
    assert r1.status_code in (200,201,400), r1.text
    # duplicate report should return friendly 400
    r2 = requests.post(f"{BASE}/api/reviews/{rid}/report",
        headers=H(tok), json={"reason":"spam"}, timeout=15)
    assert r2.status_code == 400
    assert "already" in r2.text.lower()

# ---------- Admin moderation ----------
def test_admin_review_moderation_and_stats():
    atok = login("admin@buddilio.com","Admin@123")
    stats = requests.get(f"{BASE}/api/admin/stats", headers=H(atok), timeout=15)
    assert stats.status_code == 200
    assert "flagged_reviews" in stats.json()

    flagged = requests.get(f"{BASE}/api/admin/reviews?status=flagged", headers=H(atok), timeout=15)
    assert flagged.status_code == 200
    for status in ("published","hidden","all"):
        r = requests.get(f"{BASE}/api/admin/reviews?status={status}", headers=H(atok), timeout=15)
        assert r.status_code == 200, f"{status}: {r.text}"

    body = flagged.json()
    flagged_list = body.get("items", body if isinstance(body,list) else [])
    if not flagged_list:
        pytest.skip("no flagged reviews to moderate")
    rid = flagged_list[0]["id"]
    # hide → restore
    r = requests.post(f"{BASE}/api/admin/reviews/{rid}/moderate",
        headers=H(atok), json={"action":"hide"}, timeout=15)
    assert r.status_code == 200, r.text
    hidden_body = requests.get(f"{BASE}/api/admin/reviews?status=hidden", headers=H(atok), timeout=15).json()
    hidden_list = hidden_body.get("items", hidden_body if isinstance(hidden_body, list) else [])
    assert any(x["id"] == rid for x in hidden_list)
    r = requests.post(f"{BASE}/api/admin/reviews/{rid}/moderate",
        headers=H(atok), json={"action":"publish"}, timeout=15)
    assert r.status_code == 200

# ---------- Partner reply ----------
def test_partner_reply_and_cross_partner_403():
    p1 = login("partner@buddilio.com","Partner@123")
    p2 = login("partner2@buddilio.com","Partner@123")
    pr = requests.get(f"{BASE}/api/partner/reviews", headers=H(p1), timeout=15)
    assert pr.status_code == 200, pr.text
    body = pr.json()
    reviews = body.get("items", body.get("reviews", body if isinstance(body,list) else []))
    if not reviews:
        pytest.skip("partner has no reviews")
    # Pick a review with no reply
    target = next((x for x in reviews if not x.get("reply")), reviews[0])
    rid = target["id"]
    txt = "Thank you for coming — we're delighted the tapas landed well and hope to host you again."
    r = requests.post(f"{BASE}/api/reviews/{rid}/reply",
        headers=H(p1), json={"body":txt}, timeout=15)
    assert r.status_code == 200, r.text
    # partner2 cannot reply to partner1's review
    r2 = requests.post(f"{BASE}/api/reviews/{rid}/reply",
        headers=H(p2), json={"body":"You cannot reply here"}, timeout=15)
    assert r2.status_code == 403, r2.text
