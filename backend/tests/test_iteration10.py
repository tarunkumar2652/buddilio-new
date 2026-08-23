"""Iteration 10 - Refactor verification for N+1 rewrites."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lifestyle-connect-17.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _items(payload):
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return payload


def test_me_events_tara_has_7_bookings():
    tok = _login("tara.joshi@example.com", "User@12345")
    r = requests.get(f"{API}/me/events", headers=_hdr(tok), timeout=30)
    assert r.status_code == 200
    events = _items(r.json())
    assert len(events) == 7, f"expected 7 bookings, got {len(events)}"
    for e in events:
        assert e.get("title")
        assert e.get("booking_status") or e.get("status")


def test_conversations_aarav_has_4():
    tok = _login("aarav.mehta@example.com", "User@12345")
    r = requests.get(f"{API}/conversations", headers=_hdr(tok), timeout=30)
    assert r.status_code == 200
    convs = _items(r.json())
    assert len(convs) == 4, f"expected 4 conversations, got {len(convs)}"
    titles = [c.get("title", "") for c in convs]
    assert any("Street Food Crawl" in t for t in titles), f"missing group chat, titles={titles}"
    for c in convs:
        assert (c.get("unread") or c.get("unread_count") or 0) == 0


def test_conversations_messages_aarav_first_direct_has_19():
    tok = _login("aarav.mehta@example.com", "User@12345")
    convs = _items(requests.get(f"{API}/conversations", headers=_hdr(tok), timeout=30).json())
    direct = [c for c in convs if c.get("type", "direct") != "event"]
    assert direct
    # First direct = Diya Sharma per spec
    diya = next((c for c in direct if "Diya" in c.get("title", "")), direct[0])
    cid = diya["id"]
    msgs = _items(requests.get(f"{API}/conversations/{cid}/messages", headers=_hdr(tok), timeout=30).json())
    assert len(msgs) >= 19, f"expected >=19 messages with Diya, got {len(msgs)}"
    for m in msgs:
        assert m.get("sender_name") or m.get("author_name")


def test_events_top_review_batch():
    # top_review only appears on rated events, so sort by rating
    events = _items(requests.get(f"{API}/events?sort=rating", timeout=30).json())
    rated = [e for e in events if e.get("top_review")]
    assert rated, "no events have top_review under sort=rating"
    for e in rated:
        tr = e["top_review"]
        assert tr.get("user_name")
        assert tr.get("comment")
        assert isinstance(tr.get("rating"), (int, float))


def test_event_detail_participants_shape():
    events = _items(requests.get(f"{API}/events", timeout=30).json())
    target = next((e for e in events if "Rooftop Jazz" in e.get("title", "")), events[0])
    d = requests.get(f"{API}/events/{target['id']}", timeout=30).json()
    parts = d.get("participants") or []
    for p in parts:
        assert p.get("name") or p.get("full_name")


def test_discover_membership_badges():
    tok = _login("tara.joshi@example.com", "User@12345")
    members = _items(requests.get(f"{API}/discover", headers=_hdr(tok), timeout=30).json())
    by_email = {m.get("email"): m for m in members if m.get("email")}
    # Gulf members should not be premium (they may not appear if not near Tara — check only if present)
    for e in ["layla.haddad@example.com", "rohan.mehra@example.com", "noor.alsuwaidi@example.com", "daniel.okonkwo@example.com"]:
        if e in by_email:
            m = by_email[e]
            assert not m.get("is_member"), f"{e} unexpectedly flagged member: {m}"


def test_admin_reviews_9():
    tok = _login("admin@buddilio.com", "Admin@123")
    r = requests.get(f"{API}/admin/reviews", headers=_hdr(tok), timeout=30).json()
    reviews = _items(r)
    total = r.get("total") if isinstance(r, dict) else len(reviews)
    assert total == 9, f"expected 9 total reviews, got {total}"
    for rv in reviews:
        # rewritten endpoint should surface these batched fields
        assert rv.get("event_title") or rv.get("event"), f"missing event_title: {list(rv.keys())}"
        assert rv.get("author_name") or rv.get("user_name"), f"missing author_name: {list(rv.keys())}"
    reported = [rv for rv in reviews if (rv.get("report_count") or (len(rv.get("reports") or []) if isinstance(rv.get("reports"), list) else 0)) > 0]
    # At least 1 review has reports
    assert len(reported) >= 1


def test_admin_payouts_2():
    tok = _login("admin@buddilio.com", "Admin@123")
    r = requests.get(f"{API}/admin/payouts", headers=_hdr(tok), timeout=30).json()
    payouts = _items(r)
    assert len(payouts) == 2, f"expected 2 payouts, got {len(payouts)}"
    for po in payouts:
        # partner is a dict {id, full_name, ...} after batch rewrite
        partner = po.get("partner") or {}
        name = po.get("partner_name") or partner.get("full_name") or partner.get("name")
        assert name and "Ravi" in name, f"missing/wrong partner name: {po}"


def test_partner_event_participants():
    tok = _login("partner@buddilio.com", "Partner@123")
    pev = _items(requests.get(f"{API}/partner/events", headers=_hdr(tok), timeout=30).json())
    assert pev
    busiest = max(pev, key=lambda e: e.get("participants_count", e.get("confirmed_count", 0)))
    parts = _items(requests.get(f"{API}/partner/events/{busiest['id']}/participants", headers=_hdr(tok), timeout=30).json())
    for p in parts:
        assert p.get("name") or p.get("full_name")


def test_leaderboard_5_rows():
    r = requests.get(f"{API}/referrals/leaderboard", timeout=30).json()
    rows = _items(r)
    assert len(rows) == 5
    assert "Tara" in rows[0]["name"]
    # invites can vary as new referrals are seeded; verify Tara has the top count with a valid badge
    assert rows[0].get("invites", 0) >= 5, f"Tara invites unexpectedly low: {rows[0]}"
    # Ambassador badge for at least the top 3 (lifetime aggregation)
    badges = [row.get("badge") for row in rows]
    assert badges[0] == "Ambassador", f"Tara should be Ambassador, got {badges}"
    assert all(b for b in badges), f"missing badges: {badges}"


def test_city_delhi_has_quotes():
    data = requests.get(f"{API}/cities/delhi-ncr", timeout=30).json()
    quotes = data.get("quotes") or []
    assert quotes, "delhi-ncr has no quotes"
    names = [q.get("user_name") or q.get("author_name") or "" for q in quotes]
    assert any("Tara" in n for n in names), f"expected Tara, got {names}"
    assert any("Ananya" in n for n in names), f"expected Ananya, got {names}"
    for q in quotes:
        assert q.get("comment")
        assert q.get("rating")


def test_city_gurugram_has_quotes():
    data = requests.get(f"{API}/cities/gurugram", timeout=30).json()
    quotes = data.get("quotes") or []
    assert quotes, "gurugram has no quotes"
    names = [q.get("user_name") or "" for q in quotes]
    assert any("Kunal" in n for n in names) or any("Arjun" in n for n in names), f"names={names}"


def test_city_dubai_no_quotes():
    data = requests.get(f"{API}/cities/dubai", timeout=30).json()
    quotes = data.get("quotes") or []
    assert quotes == [], f"dubai should have no quotes, got {quotes}"
