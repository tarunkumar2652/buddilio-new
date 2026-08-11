"""Add two finished events with paid orders so reviews and payouts have real data."""
import asyncio, os, uuid, random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = lambda: datetime.now(timezone.utc)
iso = lambda d: d.isoformat()

PAST = [
    ("Rooftop Jazz & Tapas Night", "Nightlife", "Delhi NCR", "Olive Bar, Mehrauli", 1299, 40, 12,
     "https://images.unsplash.com/photo-1684285746670-3d2eeed72192?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"),
    ("Supper Club: Regional Thali Trail", "Dining", "Gurugram", "Comorin, Sector 29", 2199, 24, 6,
     "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"),
]

COMMENTS = [
    (5, "Genuinely well hosted — introductions were made and nobody felt left out."),
    (4, "Great crowd and venue. Started about 20 minutes late but worth it."),
    (5, "Came alone, left with four new people to plan next weekend with."),
    (4, "Food was excellent. Would prefer a slightly smaller group next time."),
    (3, "Fun evening, though the venue was louder than I expected."),
]


async def main():
    partner = await db.users.find_one({"role": "partner"})
    users = await db.users.find({"role": "user"}).to_list(30)
    if not partner or not users:
        print("run seed_data.py first")
        return

    for title, cat, city, venue, price, cap, attendees, img in PAST:
        existing = await db.events.find_one({"title": title})
        if existing:
            eid = str(existing["_id"])
        else:
            start = now() - timedelta(days=random.randint(6, 20), hours=3)
            res = await db.events.insert_one({
                "title": title, "description": (
                    f"{title} was a curated Buddilio evening in {city} — a vetted group of members, "
                    "a great venue and hosts who make the introductions so nobody stands around awkwardly."),
                "category": cat, "city": city, "venue": venue,
                "starts_at": iso(start), "ends_at": iso(start + timedelta(hours=4)),
                "cover_image": img, "gallery": [img], "price": price, "capacity": cap,
                "rules": "Government ID required at entry. 21+ only.",
                "cancellation_policy": "Full refund up to 48 hours before start.",
                "approval_mode": "instant", "featured": False, "status": "completed",
                "partner_id": str(partner["_id"]), "partner_name": partner.get("org_name", "Buddilio Partner"),
                "participant_count": attendees, "created_at": iso(start - timedelta(days=20))})
            eid = str(res.inserted_id)

        picked = random.sample(users, min(attendees, len(users)))
        for i, u in enumerate(picked):
            uid = str(u["_id"])
            if await db.event_participants.find_one({"event_id": eid, "user_id": uid}):
                continue
            sub = price
            o = await db.orders.insert_one({
                "order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": uid, "user_email": u["email"],
                "kind": "event", "ref_id": eid, "item_name": title, "quantity": 1,
                "subtotal": sub, "discount": 0, "tax": round(sub * 0.18, 2), "total": round(sub * 1.18, 2),
                "coupon": "", "currency": "INR", "fx_rate": 1, "base_currency": "INR",
                "charge_subtotal": sub, "charge_discount": 0, "charge_tax": round(sub * 0.18, 2),
                "charge_total": round(sub * 1.18, 2),
                "payment_status": "paid", "order_status": "completed", "refund_status": "none",
                "gateway": "razorpay_sim", "transaction_id": "pay_" + uuid.uuid4().hex[:14],
                "created_at": iso(now() - timedelta(days=random.randint(21, 30)))})
            await db.event_participants.insert_one({
                "event_id": eid, "user_id": uid, "status": "confirmed", "order_id": str(o.inserted_id),
                "reminded": True, "created_at": iso(now() - timedelta(days=22))})
            if i < 4:
                rating, comment = COMMENTS[i % len(COMMENTS)]
                if not await db.reviews.find_one({"event_id": eid, "user_id": uid}):
                    await db.reviews.insert_one({
                        "event_id": eid, "user_id": uid, "partner_id": str(partner["_id"]),
                        "rating": rating, "comment": comment,
                        "status": "published", "flag_count": 0, "flagged": False, "reply": None,
                        "created_at": iso(now() - timedelta(days=random.randint(1, 5)))})

        revs = await db.reviews.find({"event_id": eid}, {"rating": 1}).to_list(100)
        if revs:
            await db.events.update_one({"_id": ObjectId(eid)}, {"$set": {
                "rating": round(sum(r["rating"] for r in revs) / len(revs), 2), "rating_count": len(revs)}})

    for title, keep in [("Rooftop Jazz & Tapas Night", "tara.joshi@example.com"),
                        ("Supper Club: Regional Thali Trail", "pooja.trivedi@example.com")]:
        ev = await db.events.find_one({"title": title})
        if not ev:
            continue
        eid = str(ev["_id"])
        u = await db.users.find_one({"email": keep})
        if not u:
            continue
        uid = str(u["_id"])
        if not await db.event_participants.find_one({"event_id": eid, "user_id": uid}):
            await db.event_participants.insert_one({"event_id": eid, "user_id": uid, "status": "confirmed",
                                                    "reminded": True, "created_at": ev["created_at"]})
        await db.reviews.delete_one({"event_id": eid, "user_id": uid})
        c = await db.event_participants.count_documents({"event_id": eid, "status": "confirmed"})
        await db.events.update_one({"_id": ObjectId(eid)}, {"$set": {"participant_count": c}})

    prs = await db.reviews.find({"partner_id": str(partner["_id"])}, {"rating": 1}).to_list(500)
    if prs:
        await db.users.update_one({"_id": partner["_id"]}, {"$set": {
            "rating": round(sum(r["rating"] for r in prs) / len(prs), 2), "rating_count": len(prs)}})

    # one organiser reply and one flagged review so moderation + replies are demoable straight away
    by = {"by": str(partner["_id"]), "by_name": partner.get("org_name") or partner["full_name"]}
    jazz = await db.events.find_one({"title": PAST[0][0]})
    if jazz:
        eid = str(jazz["_id"])
        replied = await db.reviews.find_one({"event_id": eid, "rating": 4})
        if replied and not replied.get("reply"):
            await db.reviews.update_one({"_id": replied["_id"]}, {"$set": {"reply": {
                **by, "body": "Thanks for the honest note — we've doubled the tapas count for the next rooftop "
                              "night. Drop us a line and we'll hold a seat for you.",
                "at": iso(now() - timedelta(days=1))}}})
        reporter = await db.users.find_one({"email": "diya.sharma@example.com"})
        flagged = await db.reviews.find_one({"event_id": eid, "reply": None})
        if flagged and reporter and str(flagged["user_id"]) != str(reporter["_id"]) \
                and not await db.reports.find_one({"target_type": "review", "target_id": str(flagged["_id"])}):
            await db.reviews.update_one({"_id": flagged["_id"]}, {"$set": {"flag_count": 1, "flagged": True}})
            await db.reports.insert_one({
                "reporter_id": str(reporter["_id"]), "reporter_email": reporter["email"],
                "target_type": "review", "target_id": str(flagged["_id"]), "reason": "Fake or spam review",
                "details": "Reads like it was written by someone who never attended.", "status": "open",
                "meta": {"event_id": eid}, "created_at": iso(now() - timedelta(hours=6))})

    print("past events, paid orders and reviews ready")
    print("Note: a couple of attendees are intentionally left un-reviewed so the "
          "'Rate your recent experiences' prompt is visible on their dashboard.")


asyncio.run(main())
