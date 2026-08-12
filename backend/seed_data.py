"""Seed realistic demo data for Buddilio. Run: python seed_data.py"""
import asyncio, os, random, uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import bcrypt

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
CATS = ["Parties", "Dining", "Nightlife", "Concerts", "Festivals", "Sports",
        "Travel", "Networking", "Social Gatherings", "Lifestyle Experiences", "Other"]
INTERESTS = ["Live Music", "Fine Dining", "Stand-up Comedy", "Trekking", "Cafe Hopping",
             "Board Games", "Craft Beer", "Photography", "Cycling", "Art Galleries",
             "Wine Tasting", "Road Trips", "Yoga", "Startups", "Football", "Cricket",
             "Theatre", "Techno", "Bollywood Nights", "Book Clubs"]
LIFESTYLE = ["Early Riser", "Night Owl", "Fitness Focused", "Vegetarian", "Social Drinker",
             "Non Smoker", "Pet Lover", "Frequent Traveller"]

EVENT_IMGS = [
    "https://images.unsplash.com/photo-1684285746670-3d2eeed72192?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.pexels.com/photos/36729801/pexels-photo-36729801.jpeg?auto=compress&w=1200",
    "https://images.unsplash.com/photo-1762237874410-17ddf6c782a1?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.pexels.com/photos/36425046/pexels-photo-36425046.jpeg?auto=compress&w=1200",
    "https://images.unsplash.com/photo-1622993288089-18298ec89b78?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1675716921224-e087a0cca69a?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1509710398975-6454dcdf049f?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1602231235593-7b55e5db426b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1563841930606-67e2bce48b78?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1758272134331-c953bea718a4?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1599458252573-56ae36120de1?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.unsplash.com/photo-1506880648420-aafaa650d147?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "https://images.pexels.com/photos/17057034/pexels-photo-17057034.jpeg?auto=compress&w=1200",
    "https://images.pexels.com/photos/8921578/pexels-photo-8921578.jpeg?auto=compress&w=1200",
    "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
]

NAMES = [
    ("Aarav", "Mehta", "male"), ("Diya", "Sharma", "female"), ("Kabir", "Nair", "male"),
    ("Ananya", "Kapoor", "female"), ("Rohan", "Iyer", "male"), ("Ishita", "Bansal", "female"),
    ("Vivaan", "Chopra", "male"), ("Meera", "Rao", "female"), ("Arjun", "Sethi", "male"),
    ("Nisha", "Verma", "female"), ("Dev", "Malhotra", "male"), ("Tara", "Joshi", "female"),
    ("Kunal", "Bhatia", "male"), ("Sanya", "Grover", "female"), ("Yash", "Pillai", "male"),
    ("Riya", "Deshpande", "female"), ("Aditya", "Menon", "male"), ("Kavya", "Reddy", "female"),
    ("Neel", "Saxena", "male"), ("Pooja", "Trivedi", "female"), ("Siddharth", "Ghosh", "male"),
    ("Aisha", "Khan", "female"),
    ("Sofia", "Marin", "female"), ("Liam", "O'Connor", "male"), ("Amara", "Okafor", "female"),
    ("Yuki", "Tanaka", "female"), ("Omar", "AlRashid", "male"), ("Chloe", "Nguyen", "female"),
]

CITY_IMG = {
    "Dubai": "https://images.unsplash.com/flagged/photo-1559717201-fbb671ff56b7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "London": "https://images.unsplash.com/photo-1581954548122-4dff8989c0f7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Singapore": "https://images.unsplash.com/photo-1624003974266-7cdbf877ec00?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Bangkok": "https://images.unsplash.com/photo-1543676774-064b3f7c5ad7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "New York": "https://images.unsplash.com/photo-1569783721854-33a99b4c0bae?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Sydney": "https://images.unsplash.com/photo-1695142887255-2ce7c1b33dda?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Tokyo": "https://images.unsplash.com/photo-1572291244855-44aa55da2137?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
    "Barcelona": "https://images.unsplash.com/photo-1581954548218-415cd6ee5f4d?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
}

EVENTS = [
    ("Skyline Rooftop Social", "Nightlife", "Delhi NCR", "Aer Terrace, Aerocity", 1499, 60),
    ("Chef's Table: 7-Course Tasting", "Dining", "Delhi NCR", "Indian Accent, Lodhi Road", 3499, 20),
    ("Sunday Brunch & Board Games", "Social Gatherings", "Gurugram", "The Hive, Sector 29", 0, 40),
    ("Techno Underground Vol. 12", "Nightlife", "Mumbai", "Bonobo, Bandra", 999, 120),
    ("Indie Live: Acoustic Evening", "Concerts", "Bengaluru", "Fandom, Koramangala", 799, 150),
    ("Holi Colour Carnival", "Festivals", "Noida", "Sector 62 Grounds", 1299, 300),
    ("Sunrise Trek: Nandi Hills", "Sports", "Bengaluru", "Nandi Hills Base", 599, 30),
    ("Founders & Friends Mixer", "Networking", "Gurugram", "WeWork Cyber City", 0, 80),
    ("Wine & Cheese Discovery", "Lifestyle Experiences", "Mumbai", "Sula Tasting Room, Lower Parel", 1899, 25),
    ("Goa Weekend Escape", "Travel", "Goa", "Anjuna Beach Villas", 8999, 18),
    ("Stand-up Comedy Night", "Lifestyle Experiences", "Delhi NCR", "Canvas Laugh Club, Noida", 699, 100),
    ("Poolside Sundowner", "Parties", "Hyderabad", "Park Hyatt Poolside", 1799, 70),
    ("Street Food Crawl: Old Delhi", "Dining", "Delhi NCR", "Chandni Chowk Metro Gate 5", 499, 25),
    ("Saturday Football Pickup", "Sports", "Pune", "Turf Park, Baner", 300, 22),
    ("Art Walk & Gallery Hop", "Lifestyle Experiences", "Delhi NCR", "Lodhi Art District", 0, 35),
    ("New Year Countdown Gala", "Parties", "Mumbai", "Taj Lands End Ballroom", 4999, 200),
    ("Cycling Club: 40km Dawn Ride", "Sports", "Delhi NCR", "India Gate C-Hexagon", 0, 50),
    ("Marina Rooftop Sundowner", "Nightlife", "Dubai", "SLS Dubai, Business Bay", 6500, 80),
    ("Soho Supper Club: Chef's Six", "Dining", "London", "Berwick Street Kitchen, Soho", 9500, 24),
    ("Skyline Cocktail Social", "Nightlife", "Singapore", "1-Altitude, Raffles Place", 5200, 60),
    ("Night Market Food Crawl", "Dining", "Bangkok", "Ratchada Rot Fai Market", 1800, 20),
    ("Chelsea Gallery Hop", "Lifestyle Experiences", "New York", "West 24th Street, Chelsea", 3200, 30),
    ("Harbour Sunset Picnic", "Social Gatherings", "Sydney", "Observatory Hill, The Rocks", 2400, 40),
    ("Omoide Yokocho Izakaya Trail", "Dining", "Tokyo", "Shinjuku Omoide Yokocho", 4200, 16),
    ("Gothic Quarter Tapas Walk", "Dining", "Barcelona", "Plaça Reial", 3800, 22),
]


async def wipe():
    for c in ["users", "events", "event_participants", "membership_plans", "user_memberships",
              "products", "orders", "payments", "coupons", "coupon_usage", "conversations",
              "messages", "notifications", "reports", "cities", "event_categories", "interests",
              "cms_pages", "settings", "audit_logs", "saved_events"]:
        await db[c].delete_many({"email": {"$ne": os.environ["ADMIN_EMAIL"]}} if c == "users" else {})


async def main():
    await wipe()
    await db.cities.insert_many([{"name": n, "state": s, "country_code": cc, "country": cn}
                                 for n, s, cc, cn in CITIES])
    await db.event_categories.insert_many([{"name": c, "slug": c.lower().replace(" ", "-")} for c in CATS])
    await db.interests.insert_many([{"name": i} for i in INTERESTS])

    await db.settings.insert_one({
        "platform_name": "Buddilio", "contact_email": "hello@buddilio.com",
        "contact_number": "+1 628 555 0100", "currency": "INR", "base_currency": "INR", "tax_percent": 18,
        "gateway": "razorpay", "gateway_mode": "test", "min_age": 21,
        "currencies": {
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
        },
        "platform_fee_percent": 15, "payout_hold_hours": 48,
        "require_email_verification": False, "auto_approve_events": False,
        "moderation_auto_suspend_reports": 3,
        "social": {"instagram": "https://instagram.com/buddilio", "linkedin": "https://linkedin.com/company/buddilio",
                   "x": "https://x.com/buddilio"},
        "seo_title": "Buddilio — Find your people for every experience",
        "seo_description": "Discover events, parties, dining and lifestyle experiences in 27 cities across 12 countries, and find verified companions to go with.",
    })

    plans = [
        {"name": "Basic", "price": 0, "duration_days": 365, "description": "Get started and explore Buddilio.",
         "benefits": ["Browse all public events", "Send 5 messages a week", "Basic discovery filters"],
         "discount_percent": 0, "active": True, "created_at": iso(now())},
        {"name": "Premium Monthly", "price": 799, "duration_days": 30,
         "description": "Full access to companions, priority passes and member pricing.",
         "benefits": ["Unlimited messaging", "Premium discovery filters", "10% off all passes",
                      "Priority event access", "Verified member badge"],
         "discount_percent": 10, "active": True, "created_at": iso(now())},
        {"name": "Premium Annual", "price": 6999, "duration_days": 365,
         "description": "Best value — everything in Premium for a full year.",
         "benefits": ["Everything in Premium Monthly", "15% off all passes", "Early access to curated experiences",
                      "Invite-only member nights", "Dedicated concierge support"],
         "discount_percent": 15, "active": True, "created_at": iso(now())},
    ]
    plan_ids = (await db.membership_plans.insert_many(plans)).inserted_ids

    products = [
        ("Buddilio Party Pass", "Entry to any one partner party in your city, all month long.", 1499, 10, 30, "Global"),
        ("Night Pass (Weekend)", "Two weekend nightlife entries with priority queue access.", 2499, 15, 15, "Dubai"),
        ("Dining Experience Pass", "Curated chef-led dinner with 8 fellow members.", 3299, 5, 45, "London"),
        ("Festival Season Pass", "Access to all Buddilio festival meetups this season.", 4999, 20, 90, "Global"),
        ("Buddilio Gift Card", "Give the gift of great company and better nights out, redeemable in any Buddilio city.", 2000, 0, 365, "Global"),
    ]
    await db.products.insert_many([{
        "name": n, "description": d, "price": p, "discount_percent": disc, "tax_percent": 18,
        "image": EVENT_IMGS[i % len(EVENT_IMGS)], "validity_days": v, "city": c,
        "inventory": 100, "member_discount_percent": 10, "active": True, "created_at": iso(now())}
        for i, (n, d, p, disc, v, c) in enumerate(products)])

    await db.coupons.insert_many([
        {"code": "BUDDY20", "discount_type": "percent", "value": 20, "min_order": 500, "usage_limit": 500,
         "members_only": False, "expires_at": iso(now() + timedelta(days=90)), "active": True, "created_at": iso(now())},
        {"code": "MEMBER500", "discount_type": "fixed", "value": 500, "min_order": 1500, "usage_limit": 200,
         "members_only": True, "expires_at": iso(now() + timedelta(days=60)), "active": True, "created_at": iso(now())},
        {"code": "FIRSTNIGHT", "discount_type": "percent", "value": 10, "min_order": 0, "usage_limit": 1000,
         "members_only": False, "expires_at": iso(now() + timedelta(days=180)), "active": True, "created_at": iso(now())},
    ])

    # partners
    partner_defs = [("Nightfall Collective", "partner@buddilio.com", "Ravi Anand"),
                    ("Curated Table Co.", "partner2@buddilio.com", "Sneha Kulkarni")]
    partner_ids = []
    for org, email, person in partner_defs:
        r = await db.users.insert_one({
            "full_name": person, "email": email, "mobile": "+919810000001",
            "password_hash": bcrypt.hashpw(b"Partner@123", bcrypt.gensalt()).decode(),
            "role": "partner", "status": "active", "org_name": org, "city": "Delhi NCR",
            "age": 34, "dob": "1991-04-12", "gender": "other", "bio": f"{org} curates premium social experiences.",
            "photo": "", "interests": [], "event_categories": [], "lifestyle": [], "verified": True,
            "email_verified": True, "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
            "notification_prefs": {"email": True, "in_app": True, "sms": False},
            "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now())})
        partner_ids.append(str(r.inserted_id))

    # users
    user_ids = []
    for i, (fn, ln, g) in enumerate(NAMES):
        city = CITIES[i % len(CITIES)][0]
        home = CITY_MAP[city]
        r = await db.users.insert_one({
            "full_name": f"{fn} {ln}", "email": f"{fn.lower()}.{ln.lower()}@example.com",
            "mobile": f"+9198{random.randint(10000000, 99999999)}", "password_hash": PW,
            "role": "user", "status": "active", "dob": f"{random.randint(1978, 2003)}-0{random.randint(1,9)}-1{random.randint(0,8)}",
            "age": random.randint(22, 46), "gender": g, "city": city,
            "country": home["name"], "country_code": home["code"],
            "bio": random.choice([
                "Weekend explorer. Always up for live music and long dinners.",
                "New in the city and looking for a solid group to explore with.",
                "Trek in the morning, techno at night. Balance is everything.",
                "Foodie with a spreadsheet of every place worth trying.",
                "Product designer by day, gig-hopper by night.",
                "Cricket, coffee and comedy shows — in that order.",
            ]),
            "photo": f"https://i.pravatar.cc/400?img={(i % 70) + 1}",
            "interests": random.sample(INTERESTS, 5), "event_categories": random.sample(CATS, 3),
            "lifestyle": random.sample(LIFESTYLE, 3),
            "verified": i % 3 == 0, "email_verified": True,
            "privacy": {"profile_visibility": "public", "who_can_message": "everyone"},
            "notification_prefs": {"email": True, "in_app": True, "sms": False},
            "blocked": [], "connections": [], "saved_events": [], "created_at": iso(now() - timedelta(days=random.randint(1, 120)))})
        user_ids.append(str(r.inserted_id))

    # events
    event_ids = []
    for i, (title, cat, city, venue, price, cap) in enumerate(EVENTS):
        start = now() + timedelta(days=random.randint(2, 60), hours=random.randint(0, 10))
        status = "published" if i < 15 or i >= 17 else "submitted"
        home = CITY_MAP[city]
        r = await db.events.insert_one({
            "title": title, "description": (
                f"{title} is a curated Buddilio experience in {city}. Expect a warm, vetted crowd of members, "
                "a great venue and zero awkward icebreakers — our hosts make introductions so you never feel out of place. "
                "Come solo or bring a companion you met on Buddilio."),
            "category": cat, "city": city, "country": home["name"], "country_code": home["code"], "venue": venue,
            "starts_at": iso(start), "ends_at": iso(start + timedelta(hours=4)),
            "cover_image": CITY_IMG.get(city, EVENT_IMGS[i % len(EVENT_IMGS)]),
            "gallery": [EVENT_IMGS[(i + 1) % len(EVENT_IMGS)], EVENT_IMGS[(i + 2) % len(EVENT_IMGS)]],
            "price": price, "capacity": cap,
            "rules": "Photo ID required at entry. 21+ only. Be respectful — our community guidelines apply.",
            "cancellation_policy": "Full refund up to 48 hours before start. 50% within 48 hours. No refund on no-show.",
            "approval_mode": ["instant", "instant", "organizer"][i % 3],
            "featured": i < 4, "status": status,
            "partner_id": partner_ids[i % 2], "partner_name": partner_defs[i % 2][0],
            "participant_count": 0, "created_at": iso(now() - timedelta(days=random.randint(1, 30)))})
        event_ids.append(str(r.inserted_id))

    # participation
    for eid in event_ids[:12]:
        for uid in random.sample(user_ids, random.randint(3, 9)):
            await db.event_participants.insert_one({"event_id": eid, "user_id": uid, "status": "confirmed",
                                                   "created_at": iso(now())})
        c = await db.event_participants.count_documents({"event_id": eid})
        await db.events.update_one({"_id": ObjectId(eid)}, {"$set": {"participant_count": c}})

    # memberships + orders
    for uid in user_ids[:8]:
        pid = str(plan_ids[random.choice([1, 2])])
        plan = await db.membership_plans.find_one({"_id": ObjectId(pid)})
        total = round(plan["price"] * 1.18, 2)
        o = await db.orders.insert_one({
            "order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": uid, "user_email": "",
            "kind": "membership", "ref_id": pid, "item_name": plan["name"], "quantity": 1,
            "subtotal": plan["price"], "discount": 0, "tax": round(plan["price"] * 0.18, 2), "total": total,
            "coupon": "", "currency": "INR", "payment_status": "paid", "order_status": "completed",
            "refund_status": "none", "gateway": "razorpay_sim", "transaction_id": "pay_" + uuid.uuid4().hex[:14],
            "created_at": iso(now() - timedelta(days=random.randint(1, 25)))})
        await db.user_memberships.insert_one({
            "user_id": uid, "plan_id": pid, "plan_name": plan["name"], "status": "active",
            "starts_at": iso(now() - timedelta(days=5)),
            "ends_at": iso(now() + timedelta(days=plan["duration_days"])),
            "order_id": str(o.inserted_id), "created_at": iso(now())})

    prods = await db.products.find({}).to_list(10)
    for uid in random.sample(user_ids, 10):
        p = random.choice(prods)
        sub = p["price"]
        await db.orders.insert_one({
            "order_no": "BUD" + uuid.uuid4().hex[:8].upper(), "user_id": uid, "user_email": "",
            "kind": "product", "ref_id": str(p["_id"]), "item_name": p["name"], "quantity": 1,
            "subtotal": sub, "discount": 0, "tax": round(sub * 0.18, 2), "total": round(sub * 1.18, 2),
            "coupon": "", "currency": "INR",
            "payment_status": random.choice(["paid", "paid", "paid", "failed"]),
            "order_status": "completed", "refund_status": "none", "gateway": "razorpay_sim",
            "transaction_id": "pay_" + uuid.uuid4().hex[:14],
            "created_at": iso(now() - timedelta(days=random.randint(1, 28)))})

    # conversations
    convo_lines = [
        "Hey! Saw you're going to the rooftop social — first time?",
        "Yes! Booked it last night. Are you coming with friends?",
        "Solo actually, that's kind of the point of Buddilio 😄",
        "Same. Let's find each other at the entrance around 8?",
        "Perfect. See you there!",
    ]
    for i in range(5):
        a, b = user_ids[i], user_ids[i + 6]
        c = await db.conversations.insert_one({
            "type": "direct", "members": [a, b], "event_id": "", "title": "",
            "last_message": convo_lines[-1], "updated_at": iso(now()), "created_at": iso(now())})
        for j, line in enumerate(convo_lines):
            await db.messages.insert_one({"conversation_id": str(c.inserted_id),
                                          "sender_id": a if j % 2 == 0 else b, "body": line,
                                          "read": True, "created_at": iso(now() - timedelta(minutes=30 - j * 5))})

    # reports + notifications
    await db.reports.insert_many([
        {"reporter_id": user_ids[0], "reporter_email": "aarav.mehta@example.com", "target_type": "user",
         "target_id": user_ids[5], "reason": "Inappropriate messages",
         "details": "Kept asking for personal contact details after I declined.", "status": "open",
         "created_at": iso(now() - timedelta(days=2))},
        {"reporter_id": user_ids[1], "reporter_email": "diya.sharma@example.com", "target_type": "event",
         "target_id": event_ids[3], "reason": "Misleading event details",
         "details": "Listed venue did not match the actual location.", "status": "open",
         "created_at": iso(now() - timedelta(days=1))},
    ])
    for uid in user_ids[:10]:
        await db.notifications.insert_many([
            {"user_id": uid, "title": "Welcome to Buddilio",
             "body": "Complete your profile to unlock better companion matches.", "type": "registration",
             "link": "/profile", "read": False, "created_at": iso(now() - timedelta(days=3))},
            {"user_id": uid, "title": "New events near you",
             "body": "5 curated experiences just opened in your city.", "type": "event",
             "link": "/events", "read": False, "created_at": iso(now() - timedelta(hours=6))},
        ])

    pages = {
        "about": ("About Buddilio", "Buddilio exists for one reason: great experiences are better shared. We are a curated social discovery platform where verified adults find companions for parties, dinners, concerts, treks and travel. We are not a dating app — we are the answer to 'I want to go, but not alone.'"),
        "safety": ("Safety Center", "Meet in public places for first meetups.\nProtect your personal information — never share financial details.\nNever send money directly to another member.\nReport suspicious behaviour immediately; our safety team reviews every report.\nIn an emergency, call your local emergency number first — 112 in India and the EU, 911 in the US and Canada, 999 in the UK, UAE and Singapore, 000 in Australia.\nUse Buddilio chat until you are comfortable moving elsewhere."),
        "terms": ("Terms & Conditions", "By using Buddilio you confirm you are at least 21 years old and agree to our community standards, payment terms and cancellation policies. Memberships renew only when you choose to renew. Event passes are governed by the individual event's cancellation policy."),
        "privacy": ("Privacy Policy", "We collect only what we need to run Buddilio: your identity, city, country, interests and payment records. Your mobile number, date of birth and email are never shown publicly. You control your profile visibility and who can message you. Data is processed on servers in the region closest to you where local law requires it."),
        "refund": ("Refund Policy", "Event passes: full refund up to 48 hours before the event, 50% within 48 hours, no refund for no-shows. Memberships: refundable within 7 days if unused. Refunds are returned to your original payment method in the currency you paid, usually within 5-7 working days."),
        "guidelines": ("Community Guidelines", "Be a good guest. Show up when you say you will.\nNo harassment, hate speech or unsolicited advances.\nRespect consent and personal boundaries at all times.\nNo soliciting, selling or fundraising inside the community.\nOne real identity per member — impersonation results in a permanent ban."),
        "contact": ("Contact Us", "Email hello@buddilio.com — our member care team replies within one business day, in every timezone we operate in. City teams: Delhi NCR, Mumbai, Bengaluru, Dubai, Singapore, London, New York, Toronto, Sydney, Berlin, Barcelona, Paris, Bangkok and Tokyo. Press and partnerships: partners@buddilio.com."),
        "faq": ("FAQ", "Is Buddilio a dating app? — No. Buddilio is for finding companions for experiences.\nDo I need a membership? — No, browsing and free events are open to all registered members.\nHow are members verified? — Email, mobile and optional ID verification, plus active moderation.\nCan I attend alone? — Absolutely, most members do. Hosts make introductions."),
    }
    await db.cms_pages.insert_many([
        {"slug": s, "title": t, "content": c, "seo_title": f"{t} | Buddilio",
         "seo_description": c[:150], "updated_at": iso(now())} for s, (t, c) in pages.items()])

    print("Seed complete:", len(user_ids), "users,", len(event_ids), "events")
    print("Now run: python seed_past_events.py  (adds finished events, reviews and payouts)")


asyncio.run(main())
