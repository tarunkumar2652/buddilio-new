"""Migrate existing demo data to Buddilio's global footprint. Run: python globalize.py"""
import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = lambda: datetime.now(timezone.utc)
iso = lambda d: d.isoformat()
PW = bcrypt.hashpw(b"User@123", bcrypt.gensalt()).decode()

CITIES = [
    ("Delhi NCR", "Delhi", "IN", "India"), ("Gurugram", "Haryana", "IN", "India"),
    ("Noida", "Uttar Pradesh", "IN", "India"), ("Mumbai", "Maharashtra", "IN", "India"),
    ("Bengaluru", "Karnataka", "IN", "India"), ("Hyderabad", "Telangana", "IN", "India"),
    ("Pune", "Maharashtra", "IN", "India"), ("Goa", "Goa", "IN", "India"),
    ("Dubai", "Dubai", "AE", "United Arab Emirates"), ("Abu Dhabi", "Abu Dhabi", "AE", "United Arab Emirates"),
    ("Singapore", "Singapore", "SG", "Singapore"),
    ("London", "England", "GB", "United Kingdom"), ("Manchester", "England", "GB", "United Kingdom"),
    ("New York", "New York", "US", "United States"), ("Los Angeles", "California", "US", "United States"),
    ("Miami", "Florida", "US", "United States"), ("Austin", "Texas", "US", "United States"),
    ("Toronto", "Ontario", "CA", "Canada"), ("Vancouver", "British Columbia", "CA", "Canada"),
    ("Sydney", "New South Wales", "AU", "Australia"), ("Melbourne", "Victoria", "AU", "Australia"),
    ("Berlin", "Berlin", "DE", "Germany"),
    ("Barcelona", "Catalonia", "ES", "Spain"), ("Madrid", "Madrid", "ES", "Spain"),
    ("Paris", "Île-de-France", "FR", "France"),
    ("Bangkok", "Bangkok", "TH", "Thailand"),
    ("Tokyo", "Tokyo", "JP", "Japan"),
]
CITY_MAP = {c[0]: {"code": c[2], "name": c[3]} for c in CITIES}

IMG = {
    "Dubai": "https://images.unsplash.com/flagged/photo-1559717201-fbb671ff56b7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "London": "https://images.unsplash.com/photo-1581954548122-4dff8989c0f7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Singapore": "https://images.unsplash.com/photo-1624003974266-7cdbf877ec00?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Bangkok": "https://images.unsplash.com/photo-1543676774-064b3f7c5ad7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "New York": "https://images.unsplash.com/photo-1569783721854-33a99b4c0bae?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Sydney": "https://images.unsplash.com/photo-1695142887255-2ce7c1b33dda?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Tokyo": "https://images.unsplash.com/photo-1572291244855-44aa55da2137?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Barcelona": "https://images.unsplash.com/photo-1581954548218-415cd6ee5f4d?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
}

GLOBAL_EVENTS = [
    ("Marina Rooftop Sundowner", "Nightlife", "Dubai", "SLS Dubai, Business Bay", 6500, 80),
    ("Soho Supper Club: Chef's Six", "Dining", "London", "Berwick Street Kitchen, Soho", 9500, 24),
    ("Skyline Cocktail Social", "Nightlife", "Singapore", "1-Altitude, Raffles Place", 5200, 60),
    ("Night Market Food Crawl", "Dining", "Bangkok", "Ratchada Rot Fai Market", 1800, 20),
    ("Chelsea Gallery Hop", "Lifestyle Experiences", "New York", "West 24th Street, Chelsea", 3200, 30),
    ("Harbour Sunset Picnic", "Social Gatherings", "Sydney", "Observatory Hill, The Rocks", 2400, 40),
    ("Omoide Yokocho Izakaya Trail", "Dining", "Tokyo", "Shinjuku Omoide Yokocho", 4200, 16),
    ("Gothic Quarter Tapas Walk", "Dining", "Barcelona", "Plaça Reial", 3800, 22),
]

GLOBAL_MEMBERS = [
    ("Sofia Marin", "sofia.marin@example.com", "female", "Barcelona", 31),
    ("Liam O'Connor", "liam.oconnor@example.com", "male", "London", 34),
    ("Amara Okafor", "amara.okafor@example.com", "female", "New York", 29),
    ("Yuki Tanaka", "yuki.tanaka@example.com", "female", "Tokyo", 27),
    ("Omar Al Rashid", "omar.alrashid@example.com", "male", "Dubai", 36),
    ("Chloe Nguyen", "chloe.nguyen@example.com", "female", "Sydney", 30),
]

CURRENCIES = {
    "INR": {"rate": 1.0, "symbol": "₹", "label": "Indian Rupee"},
    "USD": {"rate": 0.012, "symbol": "$", "label": "US Dollar"},
    "EUR": {"rate": 0.011, "symbol": "€", "label": "Euro"},
    "GBP": {"rate": 0.0094, "symbol": "£", "label": "British Pound"},
    "AED": {"rate": 0.044, "symbol": "AED ", "label": "UAE Dirham"},
    "SGD": {"rate": 0.016, "symbol": "S$", "label": "Singapore Dollar"},
    "CAD": {"rate": 0.016, "symbol": "C$", "label": "Canadian Dollar"},
    "AUD": {"rate": 0.018, "symbol": "A$", "label": "Australian Dollar"},
    "THB": {"rate": 0.39, "symbol": "฿", "label": "Thai Baht"},
    "JPY": {"rate": 1.8, "symbol": "¥", "label": "Japanese Yen"},
}

INTERESTS = ["Live Music", "Fine Dining", "Stand-up Comedy", "Cafe Hopping", "Craft Beer",
             "Photography", "Art Galleries", "Wine Tasting", "Techno", "Book Clubs", "Yoga", "Startups"]
CATS = ["Parties", "Dining", "Nightlife", "Concerts", "Festivals", "Sports", "Travel",
        "Networking", "Social Gatherings", "Lifestyle Experiences"]
LIFESTYLE = ["Night Owl", "Fitness Focused", "Social Drinker", "Frequent Traveller", "Pet Lover"]


async def main():
    await db.cities.delete_many({})
    await db.cities.insert_many([{"name": n, "state": s, "country_code": cc, "country": cn}
                                 for n, s, cc, cn in CITIES])
    print(f"cities → {len(CITIES)} in 12 countries")

    for coll in ("users", "events"):
        for doc in await db[coll].find({}, {"city": 1}).to_list(1000):
            c = CITY_MAP.get(doc.get("city", ""), {"code": "IN", "name": "India"})
            await db[coll].update_one({"_id": doc["_id"]},
                                      {"$set": {"country": c["name"], "country_code": c["code"]}})
    print("backfilled country on users and events")

    partners = await db.users.find({"role": "partner"}).to_list(10)
    for i, (title, cat, city, venue, price, cap) in enumerate(GLOBAL_EVENTS):
        if await db.events.find_one({"title": title}):
            continue
        c = CITY_MAP[city]
        p = partners[i % len(partners)]
        start = now() + timedelta(days=random.randint(5, 55), hours=random.randint(0, 9))
        await db.events.insert_one({
            "title": title, "description": (
                f"{title} is a curated Buddilio experience in {city}. Expect a warm, vetted crowd of members, "
                "a great venue and zero awkward icebreakers — our hosts make introductions so nobody stands "
                "around alone. Come solo or bring a companion you met on Buddilio."),
            "category": cat, "city": city, "country": c["name"], "country_code": c["code"], "venue": venue,
            "starts_at": iso(start), "ends_at": iso(start + timedelta(hours=4)),
            "cover_image": IMG[city], "gallery": [],
            "price": price, "capacity": cap,
            "rules": "Photo ID required at entry. 21+ only. Be respectful — our community guidelines apply.",
            "cancellation_policy": "Full refund up to 48 hours before start. 50% within 48 hours. No refund on no-show.",
            "approval_mode": "instant", "featured": i < 2, "status": "published",
            "partner_id": str(p["_id"]), "partner_name": p.get("org_name") or p["full_name"],
            "participant_count": 0, "rating": 0, "rating_count": 0,
            "created_at": iso(now() - timedelta(days=random.randint(1, 20)))})
    print(f"events → added international line-up ({len(GLOBAL_EVENTS)} cities)")

    for i, (name, email, gender, city, age) in enumerate(GLOBAL_MEMBERS):
        if await db.users.find_one({"email": email}):
            continue
        c = CITY_MAP[city]
        await db.users.insert_one({
            "full_name": name, "email": email, "mobile": f"+1555000{1000 + i}",
            "password_hash": PW, "role": "user", "status": "active",
            "dob": f"{now().year - age}-05-14", "age": age, "gender": gender,
            "city": city, "country": c["name"], "country_code": c["code"],
            "bio": random.choice([
                "Just moved here — looking for a crew for gigs and long dinners.",
                "Design by day, natural wine and vinyl bars by night.",
                "Runs in the morning, rooftops in the evening.",
                "Always hunting the next great neighbourhood restaurant.",
            ]),
            "photo": f"https://i.pravatar.cc/400?img={40 + i}",
            "interests": random.sample(INTERESTS, 5), "event_categories": random.sample(CATS, 3),
            "lifestyle": random.sample(LIFESTYLE, 3), "verified": True, "email_verified": True,
            "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
            "notification_prefs": {"email": True, "in_app": True, "sms": False, "push": True},
            "blocked": [], "connections": [], "saved_events": [],
            "created_at": iso(now() - timedelta(days=random.randint(2, 60)))})
    print(f"members → added {len(GLOBAL_MEMBERS)} international profiles")

    await db.products.update_many({"city": "All India"}, {"$set": {"city": "Global"}})
    await db.products.update_one({"name": {"$regex": "^Night Pass"}}, {"$set": {"city": "Dubai"}})
    await db.products.update_one({"name": {"$regex": "^Dining Experience"}}, {"$set": {"city": "London"}})
    await db.products.update_one({"name": {"$regex": "^Buddilio Gift Card"}},
                                 {"$set": {"name": "Buddilio Gift Card", "city": "Global",
                                           "description": "Give the gift of great company and better nights out, "
                                                          "redeemable in any Buddilio city."}})
    print("products → globalised")

    await db.settings.update_one({}, {"$set": {
        "currencies": CURRENCIES, "base_currency": "INR",
        "contact_number": "+1 628 555 0100",
        "seo_description": "Discover events, parties, dining and lifestyle experiences in 27 cities across "
                           "12 countries, and find verified companions to go with.",
    }})

    await db.cms_pages.update_one({"slug": "safety"}, {"$set": {"content": (
        "Meet in public places for first meetups.\n"
        "Protect your personal information — never share financial details.\n"
        "Never send money directly to another member.\n"
        "Report suspicious behaviour immediately; our safety team reviews every report.\n"
        "In an emergency, call your local emergency number first — 112 in India and the EU, 911 in the US and "
        "Canada, 999 in the UK, UAE and Singapore, 000 in Australia.\n"
        "Use Buddilio chat until you are comfortable moving elsewhere.")}})
    await db.cms_pages.update_one({"slug": "contact"}, {"$set": {"content": (
        "Email hello@buddilio.com — our member care team replies within one business day, in every timezone "
        "we operate in.\nCity teams: Delhi NCR · Mumbai · Bengaluru · Dubai · Singapore · London · New York · "
        "Toronto · Sydney · Berlin · Barcelona · Paris · Bangkok · Tokyo.\n"
        "Press and partnerships: partners@buddilio.com.")}})
    await db.cms_pages.update_one({"slug": "refund"}, {"$set": {"content": (
        "Event passes: full refund up to 48 hours before the event, 50% within 48 hours, no refund for no-shows.\n"
        "Memberships: refundable within 7 days if unused.\n"
        "Refunds are returned to your original payment method in the currency you paid, and usually arrive "
        "within 5-7 working days depending on your bank.")}})
    await db.cms_pages.update_one({"slug": "privacy"}, {"$set": {"content": (
        "We collect only what we need to run Buddilio: your identity, city, country, interests and payment "
        "records. Your mobile number, date of birth and email are never shown publicly. You control your "
        "profile visibility and who can message you. Data is processed on servers in the region closest to "
        "you where local law requires it.")}})
    print("settings and CMS pages → globalised")

    print("users:", await db.users.count_documents({}),
          "| events:", await db.events.count_documents({}),
          "| published:", await db.events.count_documents({"status": "published"}),
          "| countries live:", len(await db.events.distinct("country", {"status": "published"})))


asyncio.run(main())
