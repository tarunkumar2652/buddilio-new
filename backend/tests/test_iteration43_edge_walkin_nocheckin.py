"""Reproduces the real-world path to the pass-reminder crash: a walk-in sold with
check_in_now=false and no guest email leaves a *valid* pass whose user_id is "".
Cleans up after itself."""
import os

import requests
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
DB = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]


def test_walkin_without_checkin_leaves_valid_pass_with_empty_user_id():
    tok = requests.post(f"{BASE}/auth/login",
                        json={"email": "partner@buddilio.com", "password": "Partner@123"},
                        timeout=30).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    partner = DB.users.find_one({"email": "partner@buddilio.com"})
    ev = DB.events.find_one({"partner_id": str(partner["_id"]), "status": "published"})
    eid = str(ev["_id"])
    r = requests.post(f"{BASE}/partner/events/{eid}/walk-in", headers=h, timeout=60,
                      json={"guest_name": "TEST_I43 Later", "amount": 15, "method": "cash",
                            "check_in_now": False})
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    order = DB.orders.find_one({"order_no": d["order_no"]})
    oid = str(order["_id"])
    try:
        p = DB.passes.find_one({"order_id": oid})
        assert p is not None
        print("pass status:", p["status"], "user_id:", repr(p["user_id"]))
        assert p["status"] == "valid"
        assert p["user_id"] != "", (
            "walk-in guest pass is 'valid' with an empty user_id — send_pass_reminders() will "
            "raise bson InvalidId on it and abort the whole reminder batch")
    finally:
        DB.passes.delete_many({"order_id": oid})
        DB.payments.delete_many({"order_id": oid})
        DB.vendor_settlements.delete_many({"booking_id": oid})
        DB.booking_commercial_snapshots.delete_many({"booking_id": oid})
        DB.orders.delete_one({"_id": order["_id"]})
        DB.events.update_one({"_id": ObjectId(eid)}, {"$inc": {"participant_count": -1}})
