"""Adds the positioning launch story to the Journal. Safe to re-run — it updates by slug."""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

SLUG = "leave-the-virtual-live-the-social"
BODY = """
<p>We built Buddilio around a small, stubborn observation: most people's social lives look busy on a
screen and quiet in real life. The group chat is alive. The calendar isn't.</p>

<p>That gap is what we're here for. Not to argue with the internet — the internet is how most of us
find our people in the first place. Online is a brilliant beginning. It's just a terrible ending.</p>

<h2>Online is where it starts</h2>
<p>A recommendation from a stranger who loves the same music. A city page that tells you about the
supper club two streets away. A message thread that turns into a plan. All of that is the internet
doing its best work.</p>
<p>What rarely follows is the part that actually changes how a week feels: turning up. Sitting down.
Ordering something you've never had. Laughing at a joke that only lands in person.</p>

<h2>Live the social</h2>
<p>So Buddilio picks up where the scrolling stops. You tell us your city and what you enjoy, we show
you curated experiences worth leaving the house for, and you go with verified people who genuinely
want to be there too.</p>
<ul>
  <li><b>Real experiences, not feeds.</b> Dinners, gigs, treks, getaways — things with a start time
  and an address.</li>
  <li><b>Real people, checked.</b> Every member is 21+, age-verified and moderated. Chat inside
  Buddilio until you're comfortable.</li>
  <li><b>Real places.</b> Public venues, hosts who do the introductions, and a safety team that reads
  every report.</li>
</ul>

<h2>What doesn't change</h2>
<p>We're still not a dating app, and we're still not asking you to log off. Keep the group chats, keep
the recommendations, keep the memes. Just let a few of those threads end somewhere with a table, a
view, or a trail.</p>

<p><b>Meet real people. Share real experiences.</b> That's the whole idea — and it's what every part
of Buddilio, from the events calendar to the member passes, is built to make easy.</p>
"""


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "slug": SLUG,
        "title": "Leave the virtual. Live the social.",
        "category": "Community",
        "excerpt": ("Online is where it starts — it just isn't where it should end. The thinking behind "
                    "Buddilio's new line, and what it means for how you spend your week."),
        "body": BODY.strip(),
        "cover_image": ("https://images.unsplash.com/photo-1696627958251-775068a8ddbc?crop=entropy&cs=srgb"
                        "&fm=jpg&q=85&w=1600"),
        "cover_credit": "Unsplash",
        "author_name": "Buddilio Editorial",
        "author_role": "Editorial desk",
        "tags": ["positioning", "community", "real experiences"],
        "seo_title": "Leave the virtual. Live the social. — Buddilio",
        "seo_description": ("Why Buddilio exists: online connection is a great start, but real life is "
                            "where a social life actually happens."),
        "read_minutes": 3,
        "featured": True,
        "status": "published",
        "published_at": now,
        "updated_at": now,
        "views": 0,
    }
    existing = await db.blog_posts.find_one({"slug": SLUG}, {"_id": 1, "published_at": 1})
    if existing:
        doc["published_at"] = existing.get("published_at") or now
        await db.blog_posts.update_one({"_id": existing["_id"]}, {"$set": doc})
        print(f"updated /blog/{SLUG}")
    else:
        doc["created_at"] = now
        await db.blog_posts.insert_one(doc)
        print(f"created /blog/{SLUG}")


asyncio.run(main())
