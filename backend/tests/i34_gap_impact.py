"""Iteration 34 — impact check for the future-dated-terms gap (run standalone, restores state)."""
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def client(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


pu = db.users.find_one({"email": "partner@buddilio.com"}, {"_id": 1})
v = db.vendor_profiles.find_one({"user_id": str(pu["_id"])}, {"_id": 1})
vid = str(v["_id"])
admin, member = client("admin@buddilio.com", "Admin@123"), client("aarav.mehta@example.com", "User@123")

q = admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30)
print("quote after effective_from passed:", q.status_code, q.json().get("quote", {}).get("vendor_net_rate"))

sched = db.commercial_schedules.find_one({"vendor_id": vid, "status": "active"})
orig = sched["effective_from"]
future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
db.commercial_schedules.update_one({"_id": sched["_id"]}, {"$set": {"effective_from": future}})
try:
    print("simulated gap: active schedule v%s effective_from -> %s" % (sched["version"], future))
    print("quote during gap:", admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid},
                                         timeout=30).status_code)
    ev = db.events.find_one({"partner_id": str(pu["_id"]), "status": "published", "price": {"$gt": 0}},
                            {"_id": 1})
    order = member.post(f"{BASE}/checkout",
                        json={"kind": "event", "item_id": str(ev["_id"]), "quantity": 1},
                        timeout=45).json()["order"]
    ver = member.post(f"{BASE}/payments/verify", json={"order_id": order["id"], "simulate": "success"},
                      timeout=60)
    print("order paid during gap:", ver.status_code, ver.json()["order"]["payment_status"])
    time.sleep(2)
    snap = member.get(f"{BASE}/bookings/{order['id']}/commercials", timeout=30)
    print("snapshot during gap:", snap.status_code, snap.text[:120])
    print("settlement row during gap:", db.vendor_settlements.count_documents({"booking_id": order["id"]}))
    db.orders.delete_one({"_id": ObjectId(order["id"])})
    db.booking_commercial_snapshots.delete_many({"booking_id": order["id"]})
    db.vendor_settlements.delete_many({"booking_id": order["id"]})
    print("gap order cleaned up")
finally:
    db.commercial_schedules.update_one({"_id": sched["_id"]}, {"$set": {"effective_from": orig}})
    print("restored effective_from ->", orig)
    print("final quote:", admin.get(f"{BASE}/pricing/quote", params={"vendor_id": vid}, timeout=30).status_code)
