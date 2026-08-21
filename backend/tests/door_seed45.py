"""Seed (--seed) / remove (--clean) two TEST45 door sales (one AED event, one USD event) for UI checks."""
import sys

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
NAMES = ["TEST45_UI AED", "TEST45_UI USD"]


def sess(e, p):
    t = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=45).json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {t}"})
    return s


if "--seed" in sys.argv:
    partner = sess("partner@buddilio.com", "Partner@123")
    evs = partner.get(f"{API}/partner/events", timeout=60).json()
    evs = evs.get("items", evs)
    aed = next((e for e in evs if e.get("price_currency") == "AED"), None)
    usd = next((e for e in evs if (e.get("price_currency") or "USD") == "USD"), None)
    for ev, name, amt in ((aed, NAMES[0], 25.5), (usd, NAMES[1], 10.0)):
        if not ev:
            print("skip", name)
            continue
        r = partner.post(f"{API}/partner/events/{ev['id']}/walk-in",
                         json={"guest_name": name, "guest_phone": "9998887777", "quantity": 1,
                               "amount": amt, "method": "cash", "check_in_now": False}, timeout=60)
        print(name, ev.get("price_currency"), r.status_code, r.json().get("order_no"))
    print(partner.get(f"{API}/partner/door-takings", timeout=60).json() | {"items": "..."})

if "--clean" in sys.argv:
    import asyncio

    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorClient
    be = dotenv_values("/app/backend/.env")

    async def run():
        db = AsyncIOMotorClient(be["MONGO_URL"])[be["DB_NAME"]]
        n = 0
        async for o in db.orders.find({"guest_name": {"$in": NAMES}}):
            await db.passes.delete_many({"order_id": str(o["_id"])})
            await db.payments.delete_many({"order_id": str(o["_id"])})
            await db.vendor_settlements.delete_many({"order_no": o["order_no"]})
            await db.event_participants.delete_many({"order_id": str(o["_id"])})
            if o.get("ref_id"):
                await db.events.update_one({"_id": ObjectId(o["ref_id"])},
                                           {"$inc": {"participant_count": -int(o.get("quantity") or 1)}})
            await db.orders.delete_one({"_id": o["_id"]})
            n += 1
        pend = await db.orders.delete_many({"payment_status": "pending",
                                           "user_email": "arjun.sethi@example.com",
                                           "created_at": {"$gte": "2026-07"}})
        print(f"cleaned door={n} pending={pend.deleted_count}")

    asyncio.run(run())
