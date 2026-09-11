"""Autopilot — Buddilio writes its own Journal stories and tops up the events calendar.

Runs from the daily-maintenance cron (and an admin "run now" button). Everything it does is
configurable from Admin → Autopilot and recorded in a run log so an admin can see and undo it.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger("buddilio.autopilot")

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
PROVIDER = "gemini"
MODEL = os.environ.get("AUTOPILOT_MODEL", "gemini-3.1-pro-preview")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Rotating brief types, so the Journal never reads like the same article twice.
ANGLES = [
    ("City Guides", "a practical city guide for going out in {city} — areas, the best nights of the week, "
                    "what a good evening actually costs, and how to plan one with people you've just met"),
    ("Nightlife", "a going-out playbook: how to make a night out with new people genuinely good — "
                  "timing, venue choice, group dynamics, knowing when to call it"),
    ("Dining", "a shared-table piece about eating out with new people — supper clubs, ordering for a "
               "table, splitting bills gracefully, why food is the easiest icebreaker"),
    ("Safety", "an honest safety note for meeting people from the internet in real life — public venues, "
               "telling a friend, the small habits experienced members use. Calm and practical, not scary"),
    ("Community", "a piece on why online connection alone leaves people lonely, and what changes when a "
                  "thread turns into a table. Never anti-internet — online is the start, not the end"),
    ("Travel", "a solo-but-not-alone travel piece — joining a trip with strangers, what to check first, "
               "how the good ones are organised"),
]


class SeriesIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=3, max_length=120)
    city: str = Field(min_length=2, max_length=60)
    category: str = "Social Gatherings"
    venue: str = ""
    weekday: int = Field(default=3, ge=0, le=6)      # 0 = Monday
    hour: int = Field(default=20, ge=0, le=23)
    price: float = 0
    capacity: int = Field(default=30, ge=2, le=2000)
    description: str = ""
    weeks_ahead: int = Field(default=3, ge=1, le=8)  # keep this many future dates on the calendar
    active: bool = True


class ConfigIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    blog_enabled: bool = False
    blog_days: List[int] = Field(default_factory=lambda: [0, 2, 4])   # Mon/Wed/Fri = 3 a week    blog_cities: List[str] = Field(default_factory=list)              # empty = live event cities
    blog_publish: bool = True                                         # False = hold in review
    events_enabled: bool = False
    events_per_run: int = Field(default=2, ge=0, le=10)
    events_cities: List[str] = Field(default_factory=list)
    events_days_ahead: int = Field(default=21, ge=3, le=120)
    events_min_upcoming: int = Field(default=6, ge=0, le=100)         # per city, stop topping up above this
    events_host_name: str = "Buddilio Presents"
    ping_search_engines: bool = True
    series: List[SeriesIn] = Field(default_factory=list)

    @field_validator("blog_days")
    @classmethod
    def real_weekdays(cls, v: List[int]) -> List[int]:
        if any(not (0 <= int(d) <= 6) for d in v):
            raise ValueError("Writing days must be 0 (Monday) to 6 (Sunday).")
        return sorted({int(d) for d in v})


DEFAULTS = ConfigIn().model_dump()


def clean_config(doc: Optional[dict]) -> dict:
    merged = {**DEFAULTS, **{k: v for k, v in (doc or {}).items() if k in DEFAULTS}}
    return ConfigIn(**merged).model_dump()


def _json_block(text: str) -> dict:
    """Models like to wrap JSON in prose or fences — take the first object we can parse."""
    raw = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("the model did not return JSON")
    return json.loads(match.group(0))


async def ask(system: str, prompt: str, session: str) -> dict:
    if not LLM_KEY:
        raise ValueError("No LLM key configured.")
    chat = LlmChat(api_key=LLM_KEY, session_id=session, system_message=system).with_model(PROVIDER, MODEL)
    reply = await chat.send_message(UserMessage(text=prompt))
    return _json_block(reply if isinstance(reply, str) else str(reply))


STORY_SYSTEM = """You are the editor of The Buddilio Journal. Buddilio is a social-discovery platform
for adults 21+ who want real experiences with real people — dinners, nightlife, concerts, treks and
trips. It is explicitly NOT a dating app and never framed as one.

Brand position: "Leave the virtual. Live the social." Online connection is a great start and never the
enemy — it simply isn't enough on its own. Never write anything anti-internet or anti-social-media.

House style: British English, warm, specific, confident. Short paragraphs. No emoji, no hype, no
"in today's fast-paced world". Never invent statistics, named venues you cannot vouch for, prices,
quotes or people. Speak from editorial experience, not marketing.

Return ONLY a JSON object, no prose around it, with exactly these keys:
{"title": "...", "excerpt": "one or two sentences, max 220 characters",
 "body": "<p>...</p> HTML using only <p>, <h2>, <ul>, <li>, <b> and <a href=\\"/internal-path\\">",
 "category": "one of Nightlife|Dining|Travel|City Guides|Safety|Community|Events",
 "tags": ["3-6 short lowercase tags"], "seo_title": "under 60 characters",
 "seo_description": "under 155 characters, plain sentence"}

The body must be 700-1000 words of genuinely useful writing, with 3-5 <h2> sections and at least two
internal links chosen from /events, /passes, /membership, /discover, /safety, /blog. Never link
anywhere else. The title must be original and specific — not a listicle cliche."""


def story_prompt(angle: str, city: str, avoid_titles: List[str], events: List[dict]) -> str:
    live = "\n".join(f"- {e['title']} — {e.get('category', '')} in {e.get('city', '')}" for e in events[:8])
    return (f"Write {angle.format(city=city or 'a Buddilio city')}.\n\n"
            f"Primary city focus: {city or 'no single city — keep it broadly useful'}.\n"
            f"Real experiences currently live on Buddilio (use for flavour only, never quote prices or "
            f"promise availability):\n{live or '- none listed'}\n\n"
            f"Titles already published — do not repeat these subjects or phrasings:\n"
            + ("\n".join(f"- {t}" for t in avoid_titles[:25]) or "- none yet"))


EVENT_SYSTEM = """You plan curated social experiences for Buddilio, a platform where adults 21+ book
real evenings out with verified people. You invent the *format*, never a real business: describe the
venue generically ("a rooftop bar in Bandra", "a listening room in Shoreditch"), never by brand name.

Return ONLY a JSON object with exactly these keys:
{"title": "under 60 characters, specific and inviting",
 "description": "<p>...</p> 90-150 words of HTML using only <p>, <ul>, <li>, <b> — what the evening is,
   who it suits, how it runs, what's included",
 "category": "one of the allowed categories given to you",
 "venue": "a generic venue description plus the area, e.g. 'A rooftop bar in Bandra West'",
 "rules": "one short sentence on what guests should know (dress, arrival, ID)",
 "capacity": 20-60, "suggested_price_usd": 0-60}

No emoji. No fake brands, no fake partners, no promises of celebrities or alcohol brands."""


def event_prompt(city: str, country: str, categories: List[str], existing: List[str], when: str) -> str:
    return (f"Plan one curated Buddilio experience for {city}, {country or ''} on {when}.\n"
            f"Allowed categories: {', '.join(categories)}.\n"
            f"Keep it distinct from what is already on the calendar there:\n"
            + ("\n".join(f"- {t}" for t in existing[:15]) or "- nothing yet")
            + "\nMake it something a curious 28-45 year old would actually pay for on a weeknight.")


ALLOWED_EVENT_CATEGORIES = ["Social Gatherings", "Dining", "Nightlife", "Music", "Arts", "Networking",
                            "Lifestyle Experiences", "Sports", "Festivals", "Parties"]

# Stock imagery per category, so auto events never publish without a cover.
COVERS = {
    "Dining": "photo-1517248135467-4c7edcad34c4",
    "Nightlife": "photo-1514933651103-005eec06c04b",
    "Music": "photo-1493225457124-a3eb161ffa5f",
    "Arts": "photo-1499364615650-ec38552f4f34",
    "Networking": "photo-1511795409834-ef04bbd61622",
    "Sports": "photo-1552674605-db6ffd4facb5",
    "Festivals": "photo-1533174072545-7a4b6ad7a6c3",
    "Parties": "photo-1514525253161-7a46d19cd819",
    "Lifestyle Experiences": "photo-1470225620780-dba8ba36b745",
    "Social Gatherings": "photo-1543007630-9710e4a00a20",
}


def cover_for(category: str) -> str:
    pid = COVERS.get(category, COVERS["Social Gatherings"])
    return f"https://images.unsplash.com/{pid}?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"


def next_occurrences(weekday: int, hour: int, weeks: int) -> List[datetime]:
    """The next `weeks` dates for a weekly series, starting with the coming one."""
    now = datetime.now(timezone.utc)
    ahead = (weekday - now.weekday()) % 7
    first = (now + timedelta(days=ahead or 7)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return [first + timedelta(days=7 * i) for i in range(weeks)]
