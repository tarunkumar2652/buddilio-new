"""Remove iteration-53 TEST_ support threads / ads / stories and reset the ad config."""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    r1 = await db.support_threads.delete_many({"subject": {"$regex": "TEST_"}})
    r2 = await db.support_threads.delete_many({"name": {"$regex": "^TEST_"}})
    r3 = await db.ads.delete_many({"name": {"$regex": "^TEST_"}})
    r4 = await db.blog_posts.delete_many({"title": {"$regex": "^TEST_"}})
    await db.ad_settings.update_one({"_id": "ads"}, {"$set": {
        "network_enabled": False, "network_client": "", "network_slots": {},
        "code_slots": {}, "head_code": "", "hide_for_plans": []}}, upsert=True)
    print("threads", r1.deleted_count, r2.deleted_count, "ads", r3.deleted_count,
          "posts", r4.deleted_count)
    print("ads left:", await db.ads.count_documents({}))
    print("config:", await db.ad_settings.find_one({"_id": "ads"}))


asyncio.run(main())
