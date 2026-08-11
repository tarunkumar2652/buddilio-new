"""Assign category-appropriate cover images to seeded events (idempotent)."""
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

W = "?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"
P = "?auto=compress&cs=tinysrgb&w=1200"

BY_TITLE = {
    "Skyline Rooftop Social": "https://images.unsplash.com/photo-1684285746670-3d2eeed72192" + W,
    "Chef's Table: 7-Course Tasting": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0" + W,
    "Sunday Brunch & Board Games": "https://images.pexels.com/photos/36729801/pexels-photo-36729801.jpeg" + P,
    "Techno Underground Vol. 12": "https://images.unsplash.com/photo-1762237874410-17ddf6c782a1" + W,
    "Indie Live: Acoustic Evening": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea" + W,
    "Holi Colour Carnival": "https://images.pexels.com/photos/36425046/pexels-photo-36425046.jpeg" + P,
    "Sunrise Trek: Nandi Hills": "https://images.unsplash.com/photo-1622993288089-18298ec89b78" + W,
    "Founders & Friends Mixer": "https://images.unsplash.com/photo-1675716921224-e087a0cca69a" + W,
    "Wine & Cheese Discovery": "https://images.unsplash.com/photo-1509710398975-6454dcdf049f" + W,
    "Goa Weekend Escape": "https://images.unsplash.com/photo-1602231235593-7b55e5db426b" + W,
    "Stand-up Comedy Night": "https://images.unsplash.com/photo-1563841930606-67e2bce48b78" + W,
    "Poolside Sundowner": "https://images.unsplash.com/photo-1758272134331-c953bea718a4" + W,
    "Street Food Crawl: Old Delhi": "https://images.unsplash.com/photo-1599458252573-56ae36120de1" + W,
    "Saturday Football Pickup": "https://images.unsplash.com/photo-1506880648420-aafaa650d147" + W,
    "Art Walk & Gallery Hop": "https://images.pexels.com/photos/17057034/pexels-photo-17057034.jpeg" + P,
    "New Year Countdown Gala": "https://images.pexels.com/photos/8921578/pexels-photo-8921578.jpeg" + P,
    "Cycling Club: 40km Dawn Ride": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3" + W,
}

GALLERY = ["https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3" + W,
           "https://images.pexels.com/photos/15761528/pexels-photo-15761528.jpeg" + P]


async def main():
    n = 0
    for title, url in BY_TITLE.items():
        res = await db.events.update_one({"title": title}, {"$set": {"cover_image": url, "gallery": GALLERY}})
        n += res.modified_count
    print(f"updated {n} event covers")


asyncio.run(main())
