"""Remove TEST_ support threads created by iteration-51 tests (also clears the guest rate limit)."""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    res = await db.support_threads.delete_many(
        {"$or": [{"subject": {"$regex": "^TEST"}}, {"name": {"$regex": "^TEST"}},
                 {"email": {"$regex": "^test\\."}}]})
    print("deleted", res.deleted_count)
    print("remaining", await db.support_threads.count_documents({}))


asyncio.run(main())
