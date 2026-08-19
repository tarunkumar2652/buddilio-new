"""Iteration 32 — dynamic membership plans (price/messages/feature flags), /api/me/limits,
message quota enforcement, hangouts plan flag, currency overrides, and event price_input round-trip."""
import os
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
AARAV = ("aarav.mehta@example.com", "User@123")
DIYA = ("diya.sharma@example.com", "User@123")
ARJUN = ("arjun.sethi@example.com", "User@123")

PLAN_FIELDS = ["name", "price", "duration_days", "description", "benefits", "discount_percent",
               "price_overrides", "messages_per_week", "hangouts_access", "premium_filters",
               "priority_access", "concierge_support", "active"]


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
def plans_snapshot(admin):
    r = admin.get(f"{BASE}/admin/plans", timeout=30)
    assert r.status_code == 200, r.text[:300]
    return {p["id"]: {k: p.get(k) for k in PLAN_FIELDS} for p in r.json()["items"]}


def payload(plan, **over):
    body = {k: plan.get(k) for k in PLAN_FIELDS}
    body.update(over)
    return body


def restore(admin, plans_snapshot, pid):
    r = admin.put(f"{BASE}/admin/plans/{pid}", json=payload(plans_snapshot[pid]), timeout=30)
    assert r.status_code == 200, r.text[:300]


def public_plan(pid):
    r = requests.get(f"{BASE}/plans", timeout=30)
    assert r.status_code == 200
    return next((p for p in r.json()["items"] if p["id"] == pid), None)


# ---------------- plan schema / seed sanity ----------------
class TestDynamicPlans:
    """All plan-mutating + plan-reading tests live in ONE class so pytest-xdist
    (--dist loadscope) keeps them on a single worker and they cannot race."""
    def test_public_plans_expose_new_fields(self):
        r = requests.get(f"{BASE}/plans", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 3
        for p in items:
            assert "_id" not in p
            for k in ("messages_per_week", "hangouts_access", "premium_filters",
                      "priority_access", "concierge_support", "price", "price_overrides"):
                assert k in p, f"{p['name']} missing {k}"

    def test_seeded_values(self, plans_snapshot):
        by_name = {v["name"]: v for v in plans_snapshot.values()}
        assert by_name["Basic"]["price"] == 999
        assert by_name["Basic"]["messages_per_week"] == 5
        assert by_name["Basic"]["hangouts_access"] is False
        assert by_name["Premium Monthly"]["price"] == 1999
        assert by_name["Premium Monthly"]["messages_per_week"] == 0
        assert by_name["Premium Monthly"]["hangouts_access"] is True
        assert by_name["Premium Annual"]["price"] == 19999
        assert by_name["Premium Annual"]["concierge_support"] is True


# ---------------- admin edit -> public reflection ----------------
# --- section: TestPlanEditPropagates ---
    def test_price_messages_and_flags_update_public_api(self, admin, plans_snapshot):
        pid = next(k for k, v in plans_snapshot.items() if v["name"] == "Basic")
        try:
            body = payload(plans_snapshot[pid], price=1234, messages_per_week=3,
                           premium_filters=True, priority_access=True,
                           benefits=(plans_snapshot[pid].get("benefits") or []) + ["TEST_extra benefit line"])
            r = admin.put(f"{BASE}/admin/plans/{pid}", json=body, timeout=30)
            assert r.status_code == 200, r.text[:300]
            out = r.json()
            assert out["price"] == 1234
            assert out["messages_per_week"] == 3
            assert out["premium_filters"] is True

            pub = public_plan(pid)
            assert pub is not None
            assert pub["price"] == 1234
            assert pub["messages_per_week"] == 3
            assert pub["premium_filters"] is True
            assert pub["priority_access"] is True
            assert "TEST_extra benefit line" in pub["benefits"]
        finally:
            restore(admin, plans_snapshot, pid)
        assert public_plan(pid)["price"] == 999

    def test_currency_override_then_clear(self, admin, plans_snapshot):
        pid = next(k for k, v in plans_snapshot.items() if v["name"] == "Premium Monthly")
        try:
            r = admin.put(f"{BASE}/admin/plans/{pid}",
                          json=payload(plans_snapshot[pid], price_overrides={"USD": 29}), timeout=30)
            assert r.status_code == 200, r.text[:300]
            assert public_plan(pid)["price_overrides"] == {"USD": 29}

            # clearing overrides must fall back to the base price
            r = admin.put(f"{BASE}/admin/plans/{pid}",
                          json=payload(plans_snapshot[pid], price_overrides={}, price=2499), timeout=30)
            assert r.status_code == 200
            pub = public_plan(pid)
            assert pub["price_overrides"] in ({}, None)
            assert pub["price"] == 2499
        finally:
            restore(admin, plans_snapshot, pid)
        assert public_plan(pid)["price"] == 1999

    def test_inactive_plan_hidden_from_public(self, admin, plans_snapshot):
        pid = next(k for k, v in plans_snapshot.items() if v["name"] == "Basic")
        try:
            r = admin.put(f"{BASE}/admin/plans/{pid}", json=payload(plans_snapshot[pid], active=False), timeout=30)
            assert r.status_code == 200
            assert public_plan(pid) is None
        finally:
            restore(admin, plans_snapshot, pid)
        assert public_plan(pid) is not None

    def test_plan_write_requires_admin(self, plans_snapshot):
        pid = next(iter(plans_snapshot))
        member = client(*AARAV)
        r = member.put(f"{BASE}/admin/plans/{pid}", json=payload(plans_snapshot[pid]), timeout=30)
        assert r.status_code in (401, 403), r.status_code


# ---------------- /api/me/limits ----------------
# --- section: TestLimits ---
    def test_limits_requires_auth(self):
        assert requests.get(f"{BASE}/me/limits", timeout=30).status_code in (401, 403)

    @pytest.mark.parametrize("creds", [AARAV, DIYA, ARJUN])
    def test_limits_shape(self, creds):
        c = client(*creds)
        r = c.get(f"{BASE}/me/limits", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("plan_name", "messages_per_week", "messages_left", "messages_unlimited",
                  "hangouts_access", "premium_filters", "priority_access", "concierge_support"):
            assert k in d, f"{creds[0]} limits missing {k}"
        assert isinstance(d["messages_unlimited"], bool)
        print(creds[0], d)

    def test_free_member_gets_five_weekly_messages(self):
        d = client(*ARJUN).get(f"{BASE}/me/limits", timeout=30).json()
        assert d["plan_name"] == "Free"
        assert d["messages_per_week"] == 5
        assert d["messages_unlimited"] is False
        assert d["hangouts_access"] is False

    def test_premium_annual_member_unlimited(self):
        d = client(*DIYA).get(f"{BASE}/me/limits", timeout=30).json()
        assert d["messages_unlimited"] is True
        assert d["messages_left"] is None
        assert d["hangouts_access"] is True
        assert d["concierge_support"] is True

    def test_limits_follow_plan_edit(self, admin, plans_snapshot):
        """A member's live limits must change the moment admin edits their plan."""
        member = client(*DIYA)
        pname = member.get(f"{BASE}/me/limits", timeout=30).json()["plan_name"]
        pid = next((k for k, v in plans_snapshot.items() if v["name"] == pname), None)
        if not pid:
            pytest.skip(f"member plan {pname} not in plan list")
        try:
            admin.put(f"{BASE}/admin/plans/{pid}",
                      json=payload(plans_snapshot[pid], messages_per_week=7, concierge_support=False), timeout=30)
            d = member.get(f"{BASE}/me/limits", timeout=30).json()
            assert d["messages_per_week"] == 7
            assert d["messages_unlimited"] is False
            assert isinstance(d["messages_left"], int)
            assert d["concierge_support"] is False
        finally:
            restore(admin, plans_snapshot, pid)
        d = member.get(f"{BASE}/me/limits", timeout=30).json()
        assert d["messages_unlimited"] is True
        assert d["concierge_support"] is True


# ---------------- message quota enforcement ----------------
# --- section: TestMessageQuota ---
    def test_cap_blocks_send_with_403(self, admin, plans_snapshot):
        member = client(*DIYA)
        convs = member.get(f"{BASE}/conversations", timeout=30)
        assert convs.status_code == 200, convs.text[:300]
        items = convs.json().get("items", [])
        if not items:
            pytest.skip("member has no conversation to test the quota with")
        cid = items[0]["id"]
        pname = member.get(f"{BASE}/me/limits", timeout=30).json()["plan_name"]
        pid = next((k for k, v in plans_snapshot.items() if v["name"] == pname), None)
        if not pid:
            pytest.skip("plan not found")
        try:
            # cap = 1 with messages already sent this week means the very next send is refused
            admin.put(f"{BASE}/admin/plans/{pid}", json=payload(plans_snapshot[pid], messages_per_week=1), timeout=30)
            left = member.get(f"{BASE}/me/limits", timeout=30).json()["messages_left"]
            sent = 0
            r = None
            while sent <= 2:
                r = member.post(f"{BASE}/conversations/{cid}/messages",
                                json={"body": "TEST_quota probe"}, timeout=30)
                if r.status_code == 403:
                    break
                assert r.status_code in (200, 201), f"send failed: {r.status_code} {r.text[:300]}"
                sent += 1
            assert r.status_code == 403, f"quota never enforced (left={left}, sent={sent})"
            assert "messages a week" in r.json().get("detail", "").lower() or \
                   "upgrade" in r.json().get("detail", "").lower(), r.text[:300]
            assert member.get(f"{BASE}/me/limits", timeout=30).json()["messages_left"] == 0
        finally:
            restore(admin, plans_snapshot, pid)
        assert member.get(f"{BASE}/me/limits", timeout=30).json()["messages_unlimited"] is True


# ---------------- hangouts driven by plan flag ----------------
# --- section: TestHangoutsFlag ---
    def test_no_membership_blocked(self):
        r = client(*ARJUN).get(f"{BASE}/companions", timeout=30)
        assert r.status_code == 403, r.status_code

    def test_flag_off_blocks_flag_on_allows(self, admin, plans_snapshot):
        member = client(*DIYA)
        assert member.get(f"{BASE}/companions", timeout=30).status_code == 200
        pname = member.get(f"{BASE}/me/limits", timeout=30).json()["plan_name"]
        pid = next((k for k, v in plans_snapshot.items() if v["name"] == pname), None)
        if not pid:
            pytest.skip("plan not found")
        try:
            admin.put(f"{BASE}/admin/plans/{pid}", json=payload(plans_snapshot[pid], hangouts_access=False), timeout=30)
            r = member.get(f"{BASE}/companions", timeout=30)
            assert r.status_code == 403, f"expected 403 with hangouts off, got {r.status_code}"
            assert "hangout" in r.json().get("detail", "").lower()
        finally:
            restore(admin, plans_snapshot, pid)
        assert member.get(f"{BASE}/companions", timeout=30).status_code == 200


# ---------------- event price_input stability (non-INR double save) ----------------
class TestEventPriceRoundTrip:
    def test_non_inr_event_price_input_stable(self, admin):
        r = admin.get(f"{BASE}/admin/events?q=Marina", timeout=30)
        if r.status_code != 200:
            r = admin.get(f"{BASE}/admin/events", timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", [])
        ev = next((e for e in items if "Marina Yacht" in e.get("title", "")), None) or \
            next((e for e in items if (e.get("price_currency") or "INR") not in ("", "INR")
                  and float(e.get("price_input") or 0) > 0), None)
        if not ev:
            pytest.skip("no non-INR priced event available")
        detail = admin.get(f"{BASE}/events/{ev['id']}", timeout=30)
        assert detail.status_code == 200, detail.text[:300]
        e = detail.json().get("event", detail.json())
        cur = e.get("price_currency") or "INR"
        original_input = float(e.get("price_input") or 0)
        base = {k: v for k, v in e.items() if k in (
            "title", "description", "city", "country", "venue", "address", "category", "starts_at",
            "ends_at", "capacity", "cover_image", "images", "tags", "gender_ratio_note", "dress_code",
            "age_min", "age_max", "cancellation_policy", "status", "featured")}
        base.setdefault("status", e.get("status", "published"))
        body = {**base, "price": original_input, "price_currency": cur, "partner_id": e.get("partner_id", "")}
        first = admin.put(f"{BASE}/admin/events/{ev['id']}", json=body, timeout=30)
        assert first.status_code == 200, first.text[:400]
        assert float(first.json()["price_input"]) == pytest.approx(original_input, rel=0.01)
        second = admin.put(f"{BASE}/admin/events/{ev['id']}", json=body, timeout=30)
        assert second.status_code == 200, second.text[:400]
        assert float(second.json()["price_input"]) == pytest.approx(original_input, rel=0.01), \
            "price_input drifted on the second save"
        assert second.json()["price_currency"] == cur


# ---------------- settings guard ----------------
def test_free_messages_setting_is_five(admin):
    r = admin.get(f"{BASE}/admin/settings", timeout=30)
    if r.status_code != 200:
        pytest.skip(f"settings endpoint {r.status_code}")
    data = r.json()
    s = data.get("settings", data)
    assert int(s.get("free_messages_per_week", 5)) == 5
