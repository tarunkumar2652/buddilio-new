import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values
env = dotenv_values("/app/backend/.env")

async def main():
    c = AsyncIOMotorClient(env["MONGO_URL"])
    db = c[env["DB_NAME"]]
    n = await db.newsletter_subs.count_documents({})
    print("total subs", n, "active", await db.newsletter_subs.count_documents({"status": "active"}))
    rows = await db.newsletter_subs.find({}).sort("created_at", -1).limit(500).to_list(500)
    print("first5", [(r["email"], r.get("status"), r.get("created_at")) for r in rows[:5]])
    print("TEST_ rows", [(r["email"], r.get("status"), r.get("created_at")) for r in rows if r["email"].startswith("test_")][:10])

asyncio.run(main())
