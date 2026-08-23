"""Seeds three launch stories so the Journal and sitemap have real content from day one."""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import blog  # noqa: E402

POSTS = [
    {
        "title": "The rooftop rule: how to actually enjoy a night out with people you just met",
        "category": "Nightlife",
        "excerpt": "Arriving somewhere loud with strangers can be brilliant or brutal. The difference is almost always the first twenty minutes.",
        "cover_image": "https://images.unsplash.com/photo-1536286144513-881bfbd3f292?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "cover_credit": "Photograph: Unsplash",
        "author_name": "Buddilio Editorial",
        "author_role": "Nightlife desk",
        "tags": ["nightlife", "first meetups", "etiquette"],
        "featured": True,
        "seo_title": "How to enjoy a night out with people you just met | Buddilio",
        "seo_description": "A practical guide to the first twenty minutes of a group night out: arrival, introductions, drinks, money and leaving well.",
        "body": """
<p>Every good night out with new people is decided early. Not by the venue, not by the playlist —
by how the first twenty minutes are handled. Get those right and the evening runs itself.</p>
<h2>Arrive with a plan for the first ten minutes</h2>
<p>Turn up a few minutes early and stand somewhere visible. Groups form around whoever looks settled,
and the person who arrives calm sets the tone for everyone who follows.</p>
<blockquote>You are not there to perform. You are there to be easy to talk to.</blockquote>
<h2>Ask better questions than "so what do you do?"</h2>
<p>Ask what made them pick this event. Ask what they would be doing otherwise. Both questions get a
real answer, and a real answer is the start of an actual conversation.</p>
<h2>Sort the money before the first round</h2>
<p>Agree how the bill works before anyone orders. Separate tabs, one card and a split, or rounds in
turn — any of them works. Deciding it later is what sours an otherwise good night.</p>
<h2>Leave while it is still good</h2>
<p>Say a proper goodbye and go. The people who leave on a high are the ones everyone invites again.</p>
<h3>The short version</h3>
<ul>
<li>Be early, be visible, be easy to approach.</li>
<li>Two good questions beat twenty small ones.</li>
<li>Settle the money first.</li>
<li>Leave before the energy dips.</li>
</ul>
""",
    },
    {
        "title": "Eating alone, together: the rise of the shared table",
        "category": "Dining",
        "excerpt": "Restaurants are quietly redesigning around people who arrive solo but do not want to eat alone.",
        "cover_image": "https://images.pexels.com/photos/36729762/pexels-photo-36729762.jpeg?auto=compress&cs=tinysrgb&w=1600",
        "cover_credit": "Photograph: Pexels",
        "author_name": "Buddilio Editorial",
        "author_role": "Dining desk",
        "tags": ["dining", "supper clubs", "solo"],
        "seo_title": "Shared tables and supper clubs: eating alone, together | Buddilio",
        "seo_description": "Why shared tables and supper clubs are booming, and how to get the most out of your first one.",
        "body": """
<p>The solo diner used to be seated by the kitchen door. Now they are seated at the best table in the
room — a long one, with eleven other people who also booked for one.</p>
<h2>Why the format works</h2>
<p>A shared table removes the hardest part of meeting people: the invitation. Nobody has to ask
anybody anything. You booked a seat, the seat came with company, and the food gives everyone
something to talk about.</p>
<blockquote>The menu does the small talk for you.</blockquote>
<h2>How to do your first one well</h2>
<p>Sit in the middle, not the end. Eat slowly. Offer to pour for the person next to you. And accept
that you will get on brilliantly with two people, politely with four, and that is a good night.</p>
<h2>What to avoid</h2>
<ul>
<li>Arriving late — the table has already bonded without you.</li>
<li>Talking only to the person you came with.</li>
<li>Photographing every course.</li>
</ul>
""",
    },
    {
        "title": "Meeting someone new: the safety checklist we actually use",
        "category": "Safety",
        "excerpt": "Not a lecture. The short, practical list our own team runs through before meeting someone for the first time.",
        "cover_image": "https://images.unsplash.com/photo-1611416457332-946853cc75d6?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600",
        "cover_credit": "Photograph: Unsplash",
        "author_name": "Buddilio Editorial",
        "author_role": "Trust & safety",
        "tags": ["safety", "first meetups", "trust"],
        "seo_title": "The first-meetup safety checklist | Buddilio",
        "seo_description": "A practical safety checklist for meeting someone new: public venues, sharing plans, verification, money and leaving early.",
        "body": """
<p>Buddilio is built for going out with people you have not met before, so safety is not a footnote
here. This is the checklist we use ourselves.</p>
<h2>Before you go</h2>
<ul>
<li>Meet somewhere public with staff and a door.</li>
<li>Tell one person where you are going and when you expect to be back.</li>
<li>Check the profile is verified, and that the event has a named organiser.</li>
</ul>
<h2>While you are there</h2>
<p>Keep your own drink in sight, arrange your own way home, and keep money on the platform rather
than handing cash to someone you have just met.</p>
<blockquote>Leaving early needs no explanation. "I'm going to head off" is a complete sentence.</blockquote>
<h2>Afterwards</h2>
<p>Report anything that felt off, even if nothing happened. Patterns are how we spot the people who
should not be here.</p>
""",
    },
]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    created = 0
    for raw in POSTS:
        payload = blog.PostIn(**raw, status="published")
        doc = blog.to_doc(payload)
        if await db.blog_posts.find_one({"slug": doc["slug"]}):
            print(f"skip (exists): {doc['slug']}")
            continue
        await db.blog_posts.insert_one(doc)
        created += 1
        print(f"created: /blog/{doc['slug']} · {doc['read_minutes']} min")
    print(f"done · {created} stories")


asyncio.run(main())
