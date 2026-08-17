"""Iteration 13: Guest AI + Widget - backend regression + validation tests."""
import json
import os
import re
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lifestyle-connect-17.preview.emergentagent.com").rstrip("/")
MONGO = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------- guest config ----------
def test_guest_config_no_auth():
    r = requests.get(f"{BASE}/api/ai/guest/config", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    assert isinstance(data["suggestions"], list)
    assert len(data["suggestions"]) == 3


# ---------- guest post validation ----------
def test_guest_post_empty_message_400():
    r = requests.post(f"{BASE}/api/ai/guest", json={"message": "   "}, timeout=15)
    assert r.status_code == 400


def test_guest_post_too_long_400():
    r = requests.post(f"{BASE}/api/ai/guest", json={"message": "x" * 501}, timeout=15)
    assert r.status_code == 400


# ---------- guest streaming ----------
@pytest.fixture(scope="module")
def guest_stream_result():
    """One shared guest call to conserve LLM budget."""
    q = "Do I need a membership to use Buddilio? one line only."
    with requests.post(f"{BASE}/api/ai/guest", json={"message": q}, stream=True, timeout=60) as r:
        assert r.status_code == 200, r.text
        deltas = []
        done_seen = False
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            evt = json.loads(raw[6:])
            if "delta" in evt:
                deltas.append(evt["delta"])
            if evt.get("done"):
                done_seen = True
        return {"reply": "".join(deltas).strip(), "done": done_seen, "question": q}


def test_guest_stream_sse_format_and_done(guest_stream_result):
    assert guest_stream_result["done"] is True
    assert len(guest_stream_result["reply"]) > 10


def test_guest_reply_persisted(guest_stream_result):
    # give mongo a moment
    time.sleep(1)
    row = MONGO.ai_guest_asks.find_one({"question": guest_stream_result["question"]}, sort=[("created_at", -1)])
    assert row is not None, "guest ask row missing"
    assert "ip" in row and row["ip"]
    assert row.get("reply", "").strip() != ""
    # cleanup
    MONGO.ai_guest_asks.delete_many({"question": guest_stream_result["question"]})


def test_guest_reply_supports_refund_policy():
    q = "If I cancel 3 days before, do I get money back? one short line only."
    with requests.post(f"{BASE}/api/ai/guest", json={"message": q}, stream=True, timeout=60) as r:
        assert r.status_code == 200
        text = ""
        for raw in r.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data: "):
                evt = json.loads(raw[6:])
                if "delta" in evt:
                    text += evt["delta"]
    low = text.lower()
    # Refund policy: 48h full refund. 3 days > 48h, so should mention full refund / 48
    assert ("48" in low or "full" in low or "refund" in low), f"refund answer weak: {text}"
    # Should NOT dump to human support
    assert "contact us" not in low and "contact support" not in low, f"unexpected contact-support answer: {text}"
    MONGO.ai_guest_asks.delete_many({"question": q})


def test_guest_reply_event_links_resolve():
    q = "What is on in Dubai this weekend? one line only."
    with requests.post(f"{BASE}/api/ai/guest", json={"message": q}, stream=True, timeout=60) as r:
        assert r.status_code == 200
        text = ""
        for raw in r.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data: "):
                evt = json.loads(raw[6:])
                if "delta" in evt:
                    text += evt["delta"]
    # Any /events/<id> link must resolve
    ids = re.findall(r"/events/([a-f0-9]{24})", text)
    for eid in ids:
        er = requests.get(f"{BASE}/api/events/{eid}", timeout=10)
        assert er.status_code == 200, f"linked event {eid} not published"
    MONGO.ai_guest_asks.delete_many({"question": q})


# ---------- concierge requires auth ----------
def test_concierge_requires_auth():
    r = requests.post(f"{BASE}/api/ai/concierge", json={"session_id": "s1", "message": "hi"}, timeout=15)
    assert r.status_code in (401, 403)


def test_ai_config_requires_auth():
    r = requests.get(f"{BASE}/api/ai/config", timeout=15)
    assert r.status_code in (401, 403)


# ---------- member smoke test: concierge streams ----------
@pytest.fixture(scope="module")
def member_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "diya.sharma@example.com", "password": "User@123"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_member_concierge_stream_smoke(member_token):
    sid = f"TEST_iter13_{int(time.time())}"
    with requests.post(f"{BASE}/api/ai/concierge",
                       headers={"Authorization": f"Bearer {member_token}"},
                       json={"session_id": sid, "message": "Say hi in 5 words."},
                       stream=True, timeout=60) as r:
        assert r.status_code == 200, r.text
        deltas = []
        for raw in r.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data: "):
                evt = json.loads(raw[6:])
                if "delta" in evt:
                    deltas.append(evt["delta"])
        assert len("".join(deltas).strip()) > 0
    # verify persisted
    hist = requests.get(f"{BASE}/api/ai/history",
                        headers={"Authorization": f"Bearer {member_token}"},
                        params={"session_id": sid}, timeout=15).json()
    assert len(hist["messages"]) >= 2
    # cleanup
    MONGO.ai_messages.delete_many({"session_id": sid})
