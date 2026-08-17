"""Iteration 16 — File & media storage integration.

Focus (per E1 hand-off, other paths already self-verified):
  * WebSocket delivery of attachments to the OTHER member
  * Cross-user attachment / upload-session abuse
  * Admin can delete another member's file
  * Size limits (5MB image cap, 10MB non-image cap, 25MB chunked cap)
  * Partner event gallery end-to-end (upload -> save -> public event.gallery)
  * Regressions: legacy /api/uploads image endpoint + /api/files serving
"""
import asyncio
import io
import json
import os
import struct
import time
import uuid
import zlib
from pathlib import Path

import pytest
import requests
import websockets
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    for line in Path(__file__).resolve().parents[2].joinpath("frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

CONV_DIYA_AARAV = "6a7b6792aaea7f778441926c"

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------- helpers ----------
def login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


def make_png(w=8, h_=8, colour=(200, 40, 80)):
    """Return bytes of a tiny valid PNG so upload validation passes."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h_, 8, 2, 0, 0, 0)
    raw = b""
    for _ in range(h_):
        raw += b"\x00" + bytes(list(colour) * w)
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def register_ephemeral_partner():
    """Create a throwaway partner for the gallery flow. NOTE: We avoid the ``test_`` /
    ``TEST_`` prefixes on the email so the session-scoped conftest purge (which can fire
    on a sibling xdist worker mid-test) doesn't delete the user while we're still using
    it. We clean up manually at the end of the test."""
    email = f"partnergallery_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "Test@1234", "full_name": "Partner Gallery Bot",
        "role": "partner", "org_name": "Gallery Co.",
        "mobile": "9876500000", "dob": "1990-01-01", "gender": "male", "city": "Delhi NCR",
        "country": "India", "is_adult": True, "accept_terms": True,
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    return r.json()["access_token"], email


@pytest.fixture(scope="session")
def diya():
    return login("diya.sharma@example.com", "User@123")


@pytest.fixture(scope="session")
def tara():
    return login("tara.joshi@example.com", "User@123")


@pytest.fixture(scope="session")
def admin():
    return login("admin@buddilio.com", "Admin@123")


@pytest.fixture(scope="session")
def uploaded_png(diya):
    png = make_png()
    r = requests.post(f"{BASE_URL}/api/uploads/file",
                      files={"file": ("hello.png", png, "image/png")}, headers=h(diya), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- size limits ----------
class TestSizeLimits:
    def test_image_over_5mb_rejected(self, diya):
        # Size cap is enforced by extension; the endpoint checks len(bytes) before storage.
        big = b"\x89PNG\r\n\x1a\n" + os.urandom(5 * 1024 * 1024 + 4096)
        r = requests.post(f"{BASE_URL}/api/uploads/file",
                          files={"file": ("big.png", big, "image/png")}, headers=h(diya), timeout=60)
        assert r.status_code == 400, r.text
        assert "too large" in r.text.lower()

    def test_pdf_over_10mb_rejected(self, diya):
        payload = b"%PDF-1.4\n" + os.urandom(10 * 1024 * 1024 + 1024)
        # direct endpoint enforces 10MB
        r = requests.post(f"{BASE_URL}/api/uploads/file",
                          files={"file": ("big.pdf", payload, "application/pdf")}, headers=h(diya), timeout=60)
        assert r.status_code == 400
        assert "too large" in r.text.lower()

    def test_chunk_init_over_25mb_rejected(self, diya):
        r = requests.post(f"{BASE_URL}/api/uploads/chunk/init",
                          json={"filename": "huge.mp4", "size": 26 * 1024 * 1024, "content_type": "video/mp4"},
                          headers=h(diya), timeout=20)
        assert r.status_code == 400
        assert "25mb" in r.text.lower()

    def test_chunk_init_requires_supported_ext(self, diya):
        r = requests.post(f"{BASE_URL}/api/uploads/chunk/init",
                          json={"filename": "trojan.exe", "size": 1024},
                          headers=h(diya), timeout=20)
        assert r.status_code == 400


# ---------- cross-user upload-session abuse ----------
class TestCrossUserUploadSession:
    def test_other_user_cannot_post_parts(self, diya, tara):
        init = requests.post(f"{BASE_URL}/api/uploads/chunk/init",
                             json={"filename": "clip.mp4", "size": 200_000, "content_type": "video/mp4"},
                             headers=h(diya), timeout=20).json()
        uid = init["upload_id"]

        # Tara tries to hijack diya's upload_id
        r = requests.post(f"{BASE_URL}/api/uploads/chunk/part",
                          data={"upload_id": uid, "index": "0"},
                          files={"chunk": ("c0.bin", b"x" * 1024, "application/octet-stream")},
                          headers=h(tara), timeout=20)
        assert r.status_code == 404, r.text

        r = requests.post(f"{BASE_URL}/api/uploads/chunk/complete",
                          data={"upload_id": uid}, headers=h(tara), timeout=20)
        assert r.status_code == 404, r.text

        # bogus upload_id
        r = requests.post(f"{BASE_URL}/api/uploads/chunk/complete",
                          data={"upload_id": "bogus" + uuid.uuid4().hex}, headers=h(diya), timeout=20)
        assert r.status_code == 404

        # cleanup
        db.upload_sessions.delete_one({"upload_id": uid})


# ---------- attachment abuse in chat ----------
class TestAttachmentAbuse:
    def test_attachment_belonging_to_other_user_rejected(self, diya, tara, uploaded_png):
        # tara tries to reference diya's file
        # First tara needs to be a member of a conversation. Pick or create direct with someone
        # Simpler: post into diya's own conversation but as tara — 403 conversation membership
        # So instead: use diya's conversation and diya sends someone else's file? No — she owns it.
        # Correct test: create/find a conv where tara is a member, then have tara reference diya's file.
        # Use send-message endpoint; find or create tara<->admin direct via /conversations
        cid = self._get_tara_conv(tara)
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/messages",
                          json={"body": "", "attachment_path": uploaded_png["path"]},
                          headers=h(tara), timeout=20)
        assert r.status_code == 400, r.text
        assert "no longer available" in r.text.lower() or "attachment" in r.text.lower()

    def test_message_empty_body_and_no_attachment_rejected(self, diya):
        r = requests.post(f"{BASE_URL}/api/conversations/{CONV_DIYA_AARAV}/messages",
                          json={"body": "  ", "attachment_path": ""},
                          headers=h(diya), timeout=20)
        assert r.status_code == 400

    def test_bogus_attachment_path_rejected(self, diya):
        r = requests.post(f"{BASE_URL}/api/conversations/{CONV_DIYA_AARAV}/messages",
                          json={"body": "", "attachment_path": "buddilio/uploads/deadbeef/nope.png"},
                          headers=h(diya), timeout=20)
        assert r.status_code == 400

    def _get_tara_conv(self, tara):
        # Reach out to any other user (Aarav) to open a direct thread that tara owns.
        # Find a user id
        aarav = db.users.find_one({"email": "aarav.mehta@example.com"}, {"_id": 1})
        assert aarav
        r = requests.post(f"{BASE_URL}/api/conversations", json={"user_id": str(aarav["_id"])},
                          headers=h(tara), timeout=20)
        assert r.status_code == 200, r.text
        return r.json()["id"]


# ---------- WebSocket delivery ----------
class TestWebSocketAttachmentDelivery:
    @pytest.mark.asyncio
    async def test_recipient_receives_attachment_over_ws(self, diya, uploaded_png):
        """Open a WS as Aarav, have Diya send an attachment-only message, expect a
        'message' frame delivered to Aarav with the attachment payload."""
        aarav = login("aarav.mehta@example.com", "User@123")
        ws_url = BASE_URL.replace("http", "ws") + f"/api/ws?token={aarav}"
        received = []
        async with websockets.connect(ws_url, open_timeout=15) as ws:
            # skip 'ready'
            ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert ready["type"] == "ready"

            # Diya sends attachment-only message from a background thread
            def send():
                return requests.post(
                    f"{BASE_URL}/api/conversations/{CONV_DIYA_AARAV}/messages",
                    json={"body": "", "attachment_path": uploaded_png["path"]},
                    headers=h(diya), timeout=20,
                )
            fut = asyncio.get_event_loop().run_in_executor(None, send)

            deadline = time.time() + 15
            got_message = None
            while time.time() < deadline:
                try:
                    frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                except asyncio.TimeoutError:
                    continue
                received.append(frame)
                if frame.get("type") == "message" and frame.get("conversation_id") == CONV_DIYA_AARAV:
                    got_message = frame
                    break

            resp = await fut
            assert resp.status_code == 200, resp.text
            msg_id = resp.json()["id"]

        assert got_message, f"No message frame received. Got: {[f.get('type') for f in received]}"
        att = got_message["message"].get("attachment")
        assert att, "attachment missing on WS message payload"
        assert att["content_type"].startswith("image/")
        assert att["path"] == uploaded_png["path"]

        # Notification was created for Aarav
        aarav_id = str(db.users.find_one({"email": "aarav.mehta@example.com"}, {"_id": 1})["_id"])
        notes = list(db.notifications.find({"user_id": aarav_id, "type": "message"})
                     .sort([("created_at", -1)]).limit(3))
        assert notes, "expected message notification"

        # Conversation preview says 'Sent a photo'
        conv = db.conversations.find_one({"_id": ObjectId(CONV_DIYA_AARAV)})
        assert conv["last_message"] == "Sent a photo", conv["last_message"]

        # Cleanup this attachment-only message so we don't leave chat noise
        db.messages.delete_one({"_id": ObjectId(msg_id)})


# ---------- Admin can delete another member's file ----------
class TestAdminDelete:
    def test_admin_can_soft_delete_another_users_file(self, diya, tara, admin):
        # diya uploads a fresh file to delete
        r = requests.post(f"{BASE_URL}/api/uploads/file",
                          files={"file": ("bye.png", make_png(), "image/png")}, headers=h(diya), timeout=30)
        assert r.status_code == 200
        path = r.json()["path"]

        # tara (non-owner, non-admin) is blocked
        r2 = requests.delete(f"{BASE_URL}/api/uploads", params={"path": path}, headers=h(tara), timeout=20)
        assert r2.status_code == 403

        # admin can delete
        r3 = requests.delete(f"{BASE_URL}/api/uploads", params={"path": path}, headers=h(admin), timeout=20)
        assert r3.status_code == 200, r3.text

        # Serve now 404
        r4 = requests.get(f"{BASE_URL}/api/files/{path}", timeout=20)
        assert r4.status_code == 404

        # DB row soft-deleted, not removed
        rec = db.files.find_one({"storage_path": path})
        assert rec is not None
        assert rec.get("is_deleted") is True


# ---------- Legacy /api/uploads image endpoint (regression) ----------
class TestLegacyImageUpload:
    def test_legacy_uploads_still_works_and_serves(self, diya):
        r = requests.post(f"{BASE_URL}/api/uploads",
                          files={"file": ("legacy.png", make_png(), "image/png")},
                          headers=h(diya), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["url"].startswith("/api/files/")

        # Fetch back the bytes
        r2 = requests.get(f"{BASE_URL}{j['url']}", timeout=20)
        assert r2.status_code == 200
        assert r2.headers.get("Content-Type", "").startswith("image/")
        assert len(r2.content) == j["size"]

        # Cleanup
        requests.delete(f"{BASE_URL}/api/uploads", params={"path": j["path"]}, headers=h(diya), timeout=20)


# ---------- Partner gallery end-to-end ----------
class TestPartnerGallery:
    def test_partner_can_save_event_gallery_and_public_page_shows_it(self):
        tok, email = register_ephemeral_partner()

        # Upload two images
        urls = []
        paths = []
        for name in ("g1.png", "g2.png"):
            r = requests.post(f"{BASE_URL}/api/uploads/file",
                              files={"file": (name, make_png(), "image/png")},
                              headers=h(tok), timeout=30)
            assert r.status_code == 200, r.text
            urls.append(r.json()["url"])
            paths.append(r.json()["path"])

        # Create an event as this partner with a gallery of 2 photos
        future = "2027-06-15T18:00"
        event_payload = {
            "title": "TEST Gallery Event",
            "description": "TEST gallery event", "category": "Parties",
            "city": "Delhi NCR", "country": "India", "venue": "TEST Venue",
            "starts_at": future, "ends_at": future,
            "cover_image": urls[0], "gallery": urls,
            "price": 0, "price_currency": "INR", "capacity": 20,
            "rules": "", "cancellation_policy": "", "approval_mode": "instant",
        }
        r = requests.post(f"{BASE_URL}/api/partner/events", json=event_payload,
                          headers=h(tok), timeout=30)
        assert r.status_code in (200, 201), r.text
        ev_id = r.json()["id"]

        # Remove one (simulating the UI Remove button then Save) — PUT expects full payload
        r2 = requests.put(f"{BASE_URL}/api/partner/events/{ev_id}",
                         json={**event_payload, "gallery": [urls[0]]}, headers=h(tok), timeout=20)
        assert r2.status_code == 200, r2.text

        # Approve as admin so public page can serve it
        admin_tok = login("admin@buddilio.com", "Admin@123")
        requests.post(f"{BASE_URL}/api/partner/events/{ev_id}/submit",
                      headers=h(tok), timeout=20)
        r3 = requests.post(f"{BASE_URL}/api/admin/events/{ev_id}/moderate",
                           json={"action": "approve"}, headers=h(admin_tok), timeout=20)
        assert r3.status_code == 200, r3.text

        # Public event detail
        pub = requests.get(f"{BASE_URL}/api/events/{ev_id}", timeout=20)
        assert pub.status_code == 200, pub.text
        assert pub.json().get("gallery") == [urls[0]]

        # Cleanup
        db.events.delete_one({"_id": ObjectId(ev_id)})
        for p in paths:
            requests.delete(f"{BASE_URL}/api/uploads", params={"path": p}, headers=h(admin_tok), timeout=10)
        db.users.delete_one({"email": email})
