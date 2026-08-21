"""Create (--seed) or remove (--clean) a TEST door sale for frontend verification."""
import sys

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


def sess(e, p):
    t = requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {t}"})
    return s


if "--seed" in sys.argv:
    partner = sess("partner@buddilio.com", "Partner@123")
    evs = partner.get(f"{API}/partner/events").json()
    evs = evs.get("items", evs)
    ev = evs[0]
    r = partner.post(f"{API}/partner/events/{ev['id']}/walk-in",
                     json={"guest_name": "TEST_UI Guest", "guest_phone": "9998887777",
                           "quantity": 1, "amount": 25.5, "method": "cash", "check_in_now": False})
    print(r.status_code, r.text[:300])

if "--clean" in sys.argv:
    import asyncio
    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorClient
    be = dotenv_values("/app/backend/.env")

    async def run():
        db = AsyncIOMotorClient(be["MONGO_URL"])[be["DB_NAME"]]
        n = 0
        async for o in db.orders.find({"guest_name": {"$in": ["TEST_UI Guest", "TEST_Door Guest"]}}):
            await db.passes.delete_many({"order_id": str(o["_id"])})
            await db.payments.delete_many({"order_id": str(o["_id"])})
            await db.vendor_settlements.delete_many({"order_no": o["order_no"]})
            await db.event_participants.delete_many({"order_id": str(o["_id"])})
            if o.get("ref_id"):
                await db.events.update_one({"_id": ObjectId(o["ref_id"])},
                                           {"$inc": {"participant_count": -int(o.get("quantity") or 1)}})
            await db.orders.delete_one({"_id": o["_id"]})
            n += 1
        ev = await db.events.delete_many({"title": {"$in": ["TEST_AED diag", "TEST_AED door event"]}})
        po = await db.orders.delete_many({"item_name": {"$in": ["TEST_AED diag", "TEST_AED door event"]}})
        pend = await db.orders.delete_many({"payment_status": "pending", "user_email": "arjun.sethi@example.com",
                                            "gateway": {"$in": ["stripe", "razorpay_sim", "paypal"]},
                                            "created_at": {"$gte": "2026-07"}})
        print(f"cleaned door={n} events={ev.deleted_count} aed_orders={po.deleted_count} pending={pend.deleted_count}")

    asyncio.run(run())
