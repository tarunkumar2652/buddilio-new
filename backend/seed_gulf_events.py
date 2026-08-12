"""Fill out the Gulf: more Dubai and Abu Dhabi nights plus a few local members. Idempotent."""
import asyncio, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PHOTO = "https://images.unsplash.com/photo-{}?crop=entropy&cs=srgb&fm=jpg&w=1200&q=80"
RATE_AED = 0.044          # AED per INR, matching the platform's static FX table

RULES = "Photo ID required at entry. 21+ only. Smart-casual dress code — no shorts or beachwear."
CANCEL = "Full refund up to 48 hours before start. 50% within 48 hours. No refund after the event begins."

# title, category, venue, days from now, hour, AED price, capacity, photo id, description
DUBAI = [
    ("Marina Yacht Sundowner", "Nightlife", "Dubai Harbour, Marina", 5, 18, 450, 40,
     "1527354711091-dfe0e5f699be",
     "Four hours on the water as the Marina lights come up — house music, canapés and a crowd that "
     "actually talks to each other. Boarding closes 15 minutes before departure."),
    ("Alserkal Gallery Hop & Dinner", "Arts", "Alserkal Avenue, Al Quoz", 9, 19, 220, 26,
     "1695128751971-b3b050b5e13e",
     "Three warehouse galleries with the curators walking us through, then a long shared table at a "
     "neighbourhood kitchen in Al Quoz. Our most conversational night in Dubai."),
    ("DIFC Rooftop Jazz", "Music", "Gate Village, DIFC", 12, 20, 300, 60,
     "1563138216-8ff2e182ccbd",
     "A live quartet, skyline on three sides and a bar that knows what it's doing. Come straight from "
     "work — half the room does."),
    ("Padel & Poolside Brunch", "Sports", "Jumeirah, Dubai", 16, 10, 260, 24,
     "1533030265665-8a0445a83c61",
     "Ninety minutes of mixed-doubles padel for all levels, then a poolside brunch that runs until the "
     "afternoon. Rackets provided; bring trainers."),
    ("Old Dubai Food Walk", "Food", "Al Seef & Deira Souks", 20, 17, 180, 18,
     "1677824437185-7f8893605152",
     "Abra across the creek, then eight tastings through the spice and gold souks with a guide who "
     "grew up here. Ends with karak chai on the water."),
]

ABU_DHABI = [
    ("Desert Camp Dinner Under the Stars", "Travel", "Al Khatim Desert", 7, 17, 390, 30,
     "1527419105721-af1f23c86dec",
     "Dune drive out at golden hour, then a long dinner on carpets with live oud and a telescope once "
     "the sky goes properly dark. Back in the city by midnight."),
    ("Louvre Late & Waterfront Supper", "Arts", "Saadiyat Island", 11, 18, 240, 28,
     "1758952519367-a761da38a69b",
     "A curator-led hour inside Louvre Abu Dhabi after the crowds leave, then supper under the dome's "
     "rain of light on the waterfront."),
    ("Corniche Sunrise Ride & Breakfast", "Sports", "Corniche Beach", 14, 6, 120, 25,
     "1761859310226-cbb2bc29375f",
     "A flat, easy 18km along the Corniche as the sun comes up, finishing with breakfast and very good "
     "coffee. Bikes available to hire on request."),
    ("Yas Island Race Night", "Nightlife", "Yas Marina Circuit", 18, 19, 520, 45,
     "1762687508992-effc04be64b8",
     "Grandstand seats, pit-lane walk and an after-party at the marina. One of the loudest, happiest "
     "nights on the Buddilio calendar."),
]

GULF_MEMBERS = [
    ("Layla Haddad", "layla.haddad@example.com", 29, "Female", "Dubai",
     "Brand strategist, padel four times a week, always looking for a dinner table with new faces.",
     "https://i.pravatar.cc/400?img=45", ["Padel", "Art", "Brunch"]),
    ("Rohan Mehra", "rohan.mehra@example.com", 33, "Male", "Dubai",
     "Moved from Mumbai two years ago. Rooftops, live jazz and the Deira food walks.",
     "https://i.pravatar.cc/400?img=33", ["Live music", "Food", "Sailing"]),
    ("Noor Al Suwaidi", "noor.alsuwaidi@example.com", 27, "Female", "Abu Dhabi",
     "Museum curator by day. Desert camps, gallery lates and long Corniche rides.",
     "https://i.pravatar.cc/400?img=27", ["Art", "Cycling", "Desert"]),
    ("Daniel Okonkwo", "daniel.okonkwo@example.com", 31, "Male", "Abu Dhabi",
     "Engineer, race-weekend regular, will always say yes to a boat.",
     "https://i.pravatar.cc/400?img=52", ["Motorsport", "Boats", "Padel"]),
]


async def main():
    now = datetime.now(timezone.utc)
    partners = await db.users.find({"role": "partner"}).to_list(5)
    assert partners, "no partner accounts — run seed_data.py first"
    hashed = (await db.users.find_one({"role": "user"}, {"password_hash": 1}))["password_hash"]

    made_users = 0
    for name, email, age, gender, city, bio, photo, interests in GULF_MEMBERS:
        country = "United Arab Emirates"
        res = await db.users.update_one({"email": email}, {"$setOnInsert": {
            "full_name": name, "email": email, "mobile": "", "password_hash": hashed,
            "role": "user", "status": "active", "dob": "", "age": age, "gender": gender,
            "city": city, "country": country, "country_code": "AE", "bio": bio, "photo": photo,
            "interests": interests, "event_categories": ["Nightlife", "Food", "Arts"],
            "lifestyle": {}, "verified": True, "email_verified": True,
            "privacy": {"profile": "members"}, "notification_prefs": {},
            "blocked": [], "connections": [], "saved_events": [],
            "created_at": now.isoformat()}}, upsert=True)
        made_users += 1 if res.upserted_id else 0

    made_events = 0
    for city, rows in (("Dubai", DUBAI), ("Abu Dhabi", ABU_DHABI)):
        for i, (title, cat, venue, days, hour, aed, cap, pid, desc) in enumerate(rows):
            partner = partners[i % len(partners)]
            starts = (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
            doc = {
                "title": title, "description": desc, "category": cat, "city": city,
                "country": "United Arab Emirates", "country_code": "AE", "venue": venue,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=4)).isoformat(),
                "cover_image": PHOTO.format(pid), "gallery": [],
                "price": round(aed / RATE_AED, 2), "price_currency": "AED", "price_input": float(aed),
                "price_overrides": {"AED": float(aed)}, "capacity": cap,
                "rules": RULES, "cancellation_policy": CANCEL, "approval_mode": "instant",
                "featured": i == 0, "status": "published",
                "partner_id": str(partner["_id"]),
                "partner_name": partner.get("org_name") or partner["full_name"],
                "participant_count": 0, "rating": 0, "rating_count": 0,
                "created_at": now.isoformat(), "seed_gulf": True,
            }
            res = await db.events.update_one({"title": title, "city": city}, {"$set": doc}, upsert=True)
            made_events += 1 if res.upserted_id else 0

    print(f"{made_users} new Gulf members, {made_events} new Gulf events")
    for c in ("Dubai", "Abu Dhabi", "Delhi NCR"):
        print(f"  {c}: {await db.events.count_documents({'city': c, 'status': 'published'})} events, "
              f"{await db.users.count_documents({'city': c, 'role': 'user'})} members")


asyncio.run(main())
