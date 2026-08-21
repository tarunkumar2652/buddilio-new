"""Edge case: a walk-in guest pass has user_id == "" — does send_pass_reminders survive it?

Seeds (a) a guest pass with empty user_id and (b) a normal member pass, both inside the
reminder window, runs the cron, and asserts the member pass still gets reminded.
Cleans up everything it creates.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
DB = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
CRON = be["WEBHOOK_CRON_SECRET"]
MEMBER = "arjun.sethi@example.com"


def seed(event_id, user_id, minutes, tag):
    starts = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    code = f"BUD-E43{uuid.uuid4().hex[:2].upper()}-{uuid.uuid4().hex[:2].upper()}"
    DB.passes.insert_one({"code": code, "order_id": "", "order_no": tag, "user_id": user_id,
                          "user_name": "TEST_I43 Guest", "kind": "event", "ref_id": event_id,
                          "item_name": tag, "quantity": 1, "city": "", "starts_at": starts,
                          "vendor_name": "Buddilio", "amount_label": "$10.00", "status": "valid",
                          "redeemed_at": "", "redeemed_by": "", "redeemed_by_name": "",
                          "created_at": starts})
    return code


def test_guest_pass_does_not_break_pass_reminders():
    partner = DB.users.find_one({"email": "partner@buddilio.com"})
    ev = DB.events.find_one({"partner_id": str(partner["_id"]), "status": "published"})
    member = DB.users.find_one({"email": MEMBER})
    hours = int((DB.settings.find_one({}, {"pass_reminder_hours": 1}) or {}).get("pass_reminder_hours") or 12)
    window_minutes = max(int(hours * 60) - 30, 30)
    guest_code = seed(str(ev["_id"]), "", min(window_minutes, 90), "TEST_I43_GUESTPASS")
    member_code = seed(str(ev["_id"]), str(member["_id"]), min(window_minutes, 100), "TEST_I43_MEMBERPASS")
    try:
        r = requests.post(f"{BASE}/cron/city-openings", headers={"Authorization": f"Bearer {CRON}"},
                          timeout=60)
        assert r.status_code == 200
        time.sleep(10)
        member_pass = DB.passes.find_one({"code": member_code})
        assert member_pass.get("reminded") is True, (
            "member pass was NOT reminded — the guest pass with an empty user_id most likely "
            "raised bson InvalidId and aborted send_pass_reminders()")
    finally:
        DB.passes.delete_many({"code": {"$in": [guest_code, member_code]}})
        DB.notifications.delete_many({"body": {"$regex": f"{guest_code}|{member_code}"}})
