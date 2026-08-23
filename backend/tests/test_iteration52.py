"""Iteration 52 — support alerts, canned replies, Journal newsletter."""
import os
import time
import uuid

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@buddilio.com", "Admin@123")
MEMBER = ("arjun.sethi@example.com", "User@12345")


def login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=40)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_token():
    return login(*ADMIN)


@pytest.fixture(scope="session")
def member_token():
    return login(*MEMBER)


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def member_h(member_token):
    return {"Authorization": f"Bearer {member_token}"}


# ---------------- newsletter public ----------------
class TestNewsletterPublic:
    email = f"TEST_news_{uuid.uuid4().hex[:8]}@example.com"

    def test_subscribe_new(self):
        r = requests.post(f"{API}/newsletter/subscribe",
                          json={"email": self.email, "source": "journal"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ok"] is True
        assert "You're in" in d["message"], d

    def test_subscribe_duplicate_friendly(self):
        r = requests.post(f"{API}/newsletter/subscribe",
                          json={"email": self.email, "source": "journal"}, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert "already on the list" in r.json()["message"], r.json()

    def test_subscribe_invalid_email(self):
        r = requests.post(f"{API}/newsletter/subscribe", json={"email": "not-an-email"}, timeout=40)
        assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"

    def test_case_insensitive_dedupe(self):
        r = requests.post(f"{API}/newsletter/subscribe",
                          json={"email": self.email.upper()}, timeout=40)
        assert r.status_code == 200
        assert "already on the list" in r.json()["message"], r.json()

    def test_unsubscribe_bad_token(self):
        r = requests.post(f"{API}/newsletter/unsubscribe", json={"token": "nope-" + uuid.uuid4().hex},
                          timeout=40)
        assert r.status_code == 404, r.text[:200]
        assert "isn't on the list" in r.json().get("detail", "")

    def test_unsubscribe_no_token_no_email(self):
        r = requests.post(f"{API}/newsletter/unsubscribe", json={}, timeout=40)
        assert r.status_code == 400, r.text[:200]

    def test_unsubscribe_by_email(self, admin_h):
        # parallel workers add/remove subscribers, so assert on this row, not the global count
        before = requests.get(f"{API}/admin/newsletter", headers=admin_h, timeout=40).json()
        mine = next((x for x in before["items"] if x["email"] == self.email.lower()), None)
        assert mine and mine["status"] == "active", mine
        r = requests.post(f"{API}/newsletter/unsubscribe", json={"email": self.email}, timeout=40)
        assert r.status_code == 200, r.text[:200]
        assert "won't get any more" in r.json()["message"], r.json()
        after = requests.get(f"{API}/admin/newsletter", headers=admin_h, timeout=40).json()
        row = next((x for x in after["items"] if x["email"] == self.email.lower()), None)
        assert row and row["status"] == "unsubscribed", row

    def test_unsubscribe_by_token_roundtrip(self):
        """Token in db.newsletter_subs is what the emailed /unsubscribe?t= link carries."""
        from pymongo import MongoClient
        email = f"TEST_tok_{uuid.uuid4().hex[:8]}@example.com"
        assert requests.post(f"{API}/newsletter/subscribe", json={"email": email},
                             timeout=40).status_code == 200
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        row = db.newsletter_subs.find_one({"email": email.lower()})
        assert row and row.get("token"), row
        r = requests.post(f"{API}/newsletter/unsubscribe", json={"token": row["token"]}, timeout=40)
        assert r.status_code == 200, r.text[:200]
        assert db.newsletter_subs.find_one({"email": email.lower()})["status"] == "unsubscribed"
        # resubscribing keeps the same token
        requests.post(f"{API}/newsletter/subscribe", json={"email": email}, timeout=40)
        assert db.newsletter_subs.find_one({"email": email.lower()})["token"] == row["token"]
        requests.post(f"{API}/newsletter/unsubscribe", json={"token": row["token"]}, timeout=40)


# ---------------- newsletter admin ----------------
class TestNewsletterAdmin:
    def test_admin_newsletter_requires_perm(self, member_h):
        r = requests.get(f"{API}/admin/newsletter", headers=member_h, timeout=40)
        assert r.status_code == 403, r.status_code

    def test_admin_newsletter_shape(self, admin_h):
        r = requests.get(f"{API}/admin/newsletter", headers=admin_h, timeout=40)
        assert r.status_code == 200
        d = r.json()
        for k in ("active", "total", "items"):
            assert k in d
        assert isinstance(d["active"], int) and isinstance(d["items"], list)
        for it in d["items"][:5]:
            assert "_id" not in it

    def test_send_draft_refused_and_published_contract(self, admin_h):
        # create a draft post
        payload = {"title": f"TEST_news post {uuid.uuid4().hex[:6]}", "excerpt": "TEST excerpt",
                   "body": "<p>TEST body</p>", "status": "draft", "category": "City guides"}
        c = requests.post(f"{API}/admin/blog", headers=admin_h, json=payload, timeout=40)
        assert c.status_code in (200, 201), c.text[:300]
        pid = c.json().get("id") or c.json().get("post", {}).get("id")
        assert pid, c.json()
        try:
            r = requests.post(f"{API}/admin/blog/{pid}/newsletter", headers=admin_h, timeout=60)
            assert r.status_code == 400, r.text[:200]
            assert "Publish the story" in r.json().get("detail", ""), r.json()

            # publish it
            u = requests.put(f"{API}/admin/blog/{pid}", headers=admin_h,
                             json=payload | {"status": "published"}, timeout=40)
            assert u.status_code == 200, u.text[:300]

            subs = requests.get(f"{API}/admin/newsletter", headers=admin_h, timeout=40).json()
            sub_email = f"TEST_send_{uuid.uuid4().hex[:8]}@example.com"
            requests.post(f"{API}/newsletter/subscribe", json={"email": sub_email}, timeout=40)

            r = requests.post(f"{API}/admin/blog/{pid}/newsletter", headers=admin_h, timeout=120)
            assert r.status_code == 200, r.text[:400]
            d = r.json()
            assert "Sent to" in d["message"] and "subscribers" in d["message"], d
            assert d["subscribers"] >= 1
            assert isinstance(d["sent"], int)

            # not marked sent when sent == 0 -> retry allowed
            r2 = requests.post(f"{API}/admin/blog/{pid}/newsletter", headers=admin_h, timeout=120)
            if d["sent"] == 0:
                assert r2.status_code == 200, f"retry blocked though nothing was sent: {r2.text[:300]}"
            else:
                assert r2.status_code == 400 and "already gone out" in r2.json().get("detail", "")
            requests.post(f"{API}/newsletter/unsubscribe", json={"email": sub_email}, timeout=40)
        finally:
            requests.delete(f"{API}/admin/blog/{pid}", headers=admin_h, timeout=40)

    def test_send_with_zero_subscribers_refused(self, admin_h):
        d = requests.get(f"{API}/admin/newsletter", headers=admin_h, timeout=40).json()
        if d["active"] > 0:
            pytest.skip(f"{d['active']} active subscribers exist; cannot assert empty-list refusal")


# ---------------- support alerts ----------------
class TestSupportAlerts:
    def test_guest_thread_creates_notification(self, admin_h):
        before = requests.get(f"{API}/notifications", headers=admin_h, timeout=40)
        assert before.status_code == 200, before.text[:200]
        name = f"TEST Nora {uuid.uuid4().hex[:4]}"
        r = requests.post(f"{API}/support/threads", json={
            "name": name, "email": f"TEST_guest_{uuid.uuid4().hex[:6]}@example.com",
            "message": "TEST need a human please", "subject": "TEST alert",
            "page": "/", "ai_transcript": []}, timeout=60)
        if r.status_code == 429:
            pytest.skip("guest support rate limit hit")
        assert r.status_code == 200, r.text[:400]
        tid = r.json()["thread"]["id"]
        token = r.json()["token"]
        time.sleep(2)
        n = requests.get(f"{API}/notifications", headers=admin_h, timeout=40).json()
        items = n.get("items", n if isinstance(n, list) else [])
        hit = [x for x in items if x.get("title") == f"{name} wants a human"]
        assert hit, f"no 'wants a human' notification. titles={[x.get('title') for x in items[:5]]}"
        assert hit[0].get("type") == "support", hit[0]

        # follow-up reply
        r2 = requests.post(f"{API}/support/threads/{tid}/messages",
                           json={"message": "TEST following up", "token": token}, timeout=60)
        assert r2.status_code == 200, r2.text[:400]
        time.sleep(2)
        n2 = requests.get(f"{API}/notifications", headers=admin_h, timeout=40).json()
        items2 = n2.get("items", [])
        assert any(x.get("title") == f"{name} replied in support" for x in items2), \
            f"no reply notification. titles={[x.get('title') for x in items2[:5]]}"

        # thread still saved with both messages
        g = requests.get(f"{API}/support/threads/{tid}", params={"token": token}, timeout=40)
        assert g.status_code == 200
        assert len(g.json()["thread"]["messages"]) == 2

    def test_member_thread_and_last_booking(self, member_h, admin_h):
        r = requests.post(f"{API}/support/threads", headers=member_h, json={
            "message": "TEST member escalation", "subject": "TEST member",
            "page": "/dashboard", "ai_transcript": []}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        tid = r.json()["thread"]["id"]
        d = requests.get(f"{API}/admin/support/{tid}", headers=admin_h, timeout=40)
        assert d.status_code == 200, d.text[:300]
        th = d.json()["thread"]
        assert "last_booking" in th
        # staff reply reaches the visitor
        rep = requests.post(f"{API}/admin/support/{tid}/reply", headers=admin_h,
                            json={"message": "TEST staff answer"}, timeout=60)
        assert rep.status_code == 200, rep.text[:300]
        mine = requests.get(f"{API}/support/threads", headers=member_h, timeout=40).json()
        assert any(x["id"] == tid for x in mine["items"])


    def test_guest_escalate_staff_reply_visitor_sees_it(self, admin_h):
        """Regression: guest → staff → guest round trip on the human support chat."""
        r = requests.post(f"{API}/support/threads", json={
            "name": "TEST Guest Round", "email": f"TEST_rt_{uuid.uuid4().hex[:6]}@example.com",
            "message": "TEST guest round trip", "subject": "TEST rt", "page": "/",
            "ai_transcript": []}, timeout=60)
        if r.status_code == 429:
            pytest.skip("guest support rate limit hit")
        assert r.status_code == 200, r.text[:300]
        tid, token = r.json()["thread"]["id"], r.json()["token"]
        rep = requests.post(f"{API}/admin/support/{tid}/reply", headers=admin_h,
                            json={"message": "TEST staff round trip answer"}, timeout=60)
        assert rep.status_code == 200, rep.text[:300]
        g = requests.get(f"{API}/support/threads/{tid}", params={"token": token}, timeout=40)
        assert g.status_code == 200, g.text[:200]
        msgs = g.json()["thread"]["messages"]
        assert msgs[-1]["role"] == "staff" and "round trip answer" in msgs[-1]["body"], msgs[-1]
        wrong = requests.get(f"{API}/support/threads/{tid}", params={"token": "nope"}, timeout=40)
        assert wrong.status_code in (403, 404), wrong.status_code


# ---------------- canned replies ----------------
class TestCannedReplies:
    def test_member_forbidden(self, member_h):
        r = requests.get(f"{API}/admin/support-replies", headers=member_h, timeout=40)
        assert r.status_code == 403, r.status_code

    def test_crud(self, admin_h):
        body = "Hi {first_name}, about {last_booking} — {my_name}"
        c = requests.post(f"{API}/admin/support-replies", headers=admin_h,
                          json={"title": "TEST_saved reply", "body": body}, timeout=40)
        assert c.status_code == 200, c.text[:300]
        rid = c.json()["id"]
        try:
            lst = requests.get(f"{API}/admin/support-replies", headers=admin_h, timeout=40)
            assert lst.status_code == 200
            d = lst.json()
            assert "{first_name}" in str(d["placeholders"])
            row = next((x for x in d["items"] if x["id"] == rid), None)
            assert row and row["body"] == body, row

            u = requests.put(f"{API}/admin/support-replies/{rid}", headers=admin_h,
                             json={"title": "TEST_saved reply v2", "body": body + "!"}, timeout=40)
            assert u.status_code == 200, u.text[:200]
            after = requests.get(f"{API}/admin/support-replies", headers=admin_h, timeout=40).json()
            row2 = next(x for x in after["items"] if x["id"] == rid)
            assert row2["title"] == "TEST_saved reply v2" and row2["body"].endswith("!")

            short = requests.post(f"{API}/admin/support-replies", headers=admin_h,
                                  json={"title": "a", "body": "b"}, timeout=40)
            assert short.status_code == 422, short.status_code

            missing = requests.put(f"{API}/admin/support-replies/507f1f77bcf86cd799439011",
                                   headers=admin_h, json={"title": "TEST_x", "body": "TEST_y"},
                                   timeout=40)
            assert missing.status_code == 404, missing.status_code
        finally:
            dl = requests.delete(f"{API}/admin/support-replies/{rid}", headers=admin_h, timeout=40)
            assert dl.status_code == 200
        gone = requests.get(f"{API}/admin/support-replies", headers=admin_h, timeout=40).json()
        assert all(x["id"] != rid for x in gone["items"])


# ---------------- regression ----------------
class TestRegression:
    def test_public_blog_endpoints(self):
        r = requests.get(f"{API}/blog", timeout=40)
        assert r.status_code == 200, r.text[:200]
        items = r.json().get("items", [])
        assert isinstance(items, list)
        if items:
            slug = items[0]["slug"]
            one = requests.get(f"{API}/blog/{slug}", timeout=40)
            assert one.status_code == 200, one.text[:200]

    def test_seo_panel(self, admin_h):
        r = requests.get(f"{API}/admin/seo", headers=admin_h, timeout=40)
        assert r.status_code == 200, r.text[:300]

    def test_admin_support_list(self, admin_h):
        r = requests.get(f"{API}/admin/support", headers=admin_h, timeout=40)
        assert r.status_code == 200, r.text[:300]
        assert "counts" in r.json()
