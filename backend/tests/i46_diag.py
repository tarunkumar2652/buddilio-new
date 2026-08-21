"""Diagnostics + cleanup for iteration 46 currency re-test."""
import asyncio
import os
import sys

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
MONGO = os.environ.get("MONGO_URL") or env["MONGO_URL"]
DB = os.environ.get("DB_NAME") or env["DB_NAME"]


async def main(mode):
    db = AsyncIOMotorClient(MONGO)[DB]
    if mode == "diag":
        cur = {}
        async for o in db.orders.find({}, {"currency": 1, "total": 1, "charge_total": 1, "payment_status": 1}):
            cur[o.get("currency")] = cur.get(o.get("currency"), 0) + 1
        print("orders by currency:", cur)
        u = await db.users.find_one({"email": "arjun.sethi@example.com"}, {"_id": 1})
        rows = await db.orders.find({"user_id": str(u["_id"])},
                                   {"order_no": 1, "currency": 1, "total": 1, "charge_total": 1,
                                    "payment_status": 1, "item_name": 1}).to_list(200)
        print(f"member orders: {len(rows)}")
        for r in rows[:40]:
            print("  ", r.get("order_no"), r.get("currency"), "total=", r.get("total"),
                  "charge_total=", r.get("charge_total"), r.get("payment_status"), r.get("item_name"))
        sc = {}
        async for s in db.vendor_settlements.find({}, {"currency": 1, "status": 1, "net": 1}):
            k = (s.get("currency"), s.get("status"))
            sc[k] = sc.get(k, 0) + 1
        print("settlements by (currency,status):", sc)
    elif mode == "clean":
        u = await db.users.find_one({"email": "arjun.sethi@example.com"}, {"_id": 1})
        r = await db.orders.delete_many({"user_id": str(u["_id"]), "payment_status": "pending"})
        print("deleted pending member orders:", r.deleted_count)


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "diag"))
