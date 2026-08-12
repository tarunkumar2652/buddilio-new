"""Seed rewarded referrals so the monthly leaderboard has real ranks to show. Idempotent."""
import asyncio, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
REWARD = float(os.environ.get("REFERRAL_REWARD", "250"))

# referrer email -> number of friends who joined and paid this month
LADDER = [
    ("tara.joshi@example.com", 6),
    ("sofia.marin@example.com", 4),
    ("liam.oconnor@example.com", 3),
    ("kabir.nair@example.com", 2),
    ("omar.alrashid@example.com", 1),
]


async def main():
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    await db.referrals.delete_many({"seed": True})
    await db.credits.delete_many({"seed": True})

    taken = {r["invitee_id"] for r in await db.referrals.find({}, {"invitee_id": 1}).to_list(2000)}
    referrer_emails = [e for e, _ in LADDER]
    pool = [u for u in await db.users.find({"role": "user"}, {"full_name": 1, "email": 1}).to_list(500)
            if u["email"] not in referrer_emails and str(u["_id"]) not in taken]

    day = 1
    made = 0
    for email, count in LADDER:
        ref = await db.users.find_one({"email": email}, {"full_name": 1, "referral_code": 1})
        if not ref:
            print(f"skip {email} — not in this dataset")
            continue
        code = ref.get("referral_code") or "BUDDILIO"
        for _ in range(count):
            if not pool:
                break
            invitee = pool.pop(0)
            day = day % 27 + 1
            stamp = now.replace(day=min(day, 28)).isoformat()
            res = await db.referrals.insert_one({
                "referrer_id": str(ref["_id"]), "invitee_id": str(invitee["_id"]),
                "invitee_name": invitee["full_name"], "code": code, "status": "rewarded",
                "created_at": stamp, "rewarded_at": stamp, "seed": True})
            await db.credits.insert_one({
                "user_id": str(ref["_id"]), "amount": REWARD, "type": "earned",
                "reason": f"Referral bonus — {invitee['full_name']} made their first booking",
                "referral_id": str(res.inserted_id), "created_at": stamp, "seed": True})
            made += 1

    # one pending invite so the "awaiting first booking" state is visible too
    if pool:
        top = await db.users.find_one({"email": LADDER[0][0]}, {"full_name": 1, "referral_code": 1})
        invitee = pool.pop(0)
        await db.referrals.insert_one({
            "referrer_id": str(top["_id"]), "invitee_id": str(invitee["_id"]),
            "invitee_name": invitee["full_name"], "code": top.get("referral_code") or "BUDDILIO",
            "status": "joined", "created_at": now.isoformat(), "seed": True})

    print(f"seeded {made} rewarded referrals for {month} + 1 pending invite")


asyncio.run(main())
