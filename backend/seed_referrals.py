"""Seed rewarded referrals so the monthly leaderboard and last month's champion have real data. Idempotent."""
import asyncio, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
REWARD = float(os.environ.get("REFERRAL_REWARD", "250"))

# referrer email -> friends who joined and paid, this month
LADDER = [
    ("tara.joshi@example.com", 6),
    ("sofia.marin@example.com", 4),
    ("liam.oconnor@example.com", 3),
    ("kabir.nair@example.com", 2),
    ("omar.alrashid@example.com", 1),
]

# last month, so there is a champion to announce (a different winner reads better)
PREV_LADDER = [
    ("sofia.marin@example.com", 3),
    ("liam.oconnor@example.com", 2),
    ("kabir.nair@example.com", 1),
]


async def seed(ladder, stamp_for, pool, label):
    made = 0
    for i, (email, count) in enumerate(ladder):
        ref = await db.users.find_one({"email": email}, {"full_name": 1, "referral_code": 1})
        if not ref:
            print(f"skip {email} — not in this dataset")
            continue
        for _ in range(count):
            if not pool:
                print(f"pool exhausted during {label}")
                return made
            invitee = pool.pop(0)
            stamp = stamp_for(made + i)
            res = await db.referrals.insert_one({
                "referrer_id": str(ref["_id"]), "invitee_id": str(invitee["_id"]),
                "invitee_name": invitee["full_name"], "code": ref.get("referral_code") or "BUDDILIO",
                "status": "rewarded", "created_at": stamp, "rewarded_at": stamp, "seed": True})
            await db.credits.insert_one({
                "user_id": str(ref["_id"]), "amount": REWARD, "type": "earned",
                "reason": f"Referral bonus — {invitee['full_name']} made their first booking",
                "referral_id": str(res.inserted_id), "created_at": stamp, "seed": True})
            made += 1
    print(f"{label}: {made} rewarded referrals")
    return made


async def main():
    now = datetime.now(timezone.utc)
    prev = (now.replace(day=1) - __import__("datetime").timedelta(days=1))
    await db.referrals.delete_many({"seed": True})
    await db.credits.delete_many({"seed": True})
    await db.prizes.delete_many({})

    taken = {r["invitee_id"] for r in await db.referrals.find({}, {"invitee_id": 1}).to_list(2000)}
    referrers = {e for e, _ in LADDER} | {e for e, _ in PREV_LADDER}
    pool = [u for u in await db.users.find({"role": "user"}, {"full_name": 1, "email": 1}).to_list(500)
            if u["email"] not in referrers and str(u["_id"]) not in taken]

    await seed(LADDER, lambda n: now.replace(day=min(n % 27 + 1, 28)).isoformat(), pool, now.strftime("%Y-%m"))
    await seed(PREV_LADDER, lambda n: prev.replace(day=min(n % 27 + 1, 28)).isoformat(), pool, prev.strftime("%Y-%m"))

    if pool:  # one pending invite so "awaiting first booking" is visible too
        top = await db.users.find_one({"email": LADDER[0][0]}, {"full_name": 1, "referral_code": 1})
        invitee = pool.pop(0)
        await db.referrals.insert_one({
            "referrer_id": str(top["_id"]), "invitee_id": str(invitee["_id"]),
            "invitee_name": invitee["full_name"], "code": top.get("referral_code") or "BUDDILIO",
            "status": "joined", "created_at": now.isoformat(), "seed": True})
        print("+ 1 pending invite")
    print("done — run POST /api/cron/monthly-prize to award last month's champion")


asyncio.run(main())
