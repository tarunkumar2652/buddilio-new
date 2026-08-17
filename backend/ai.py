"""Buddy AI — the Buddilio concierge, running on OpenAI chat models via the Emergent universal LLM key."""
import logging
import os

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

logger = logging.getLogger("buddilio.ai")

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
AI_PROVIDER = "openai"
AI_MODEL = os.environ.get("AI_MODEL", "gpt-5.4")
HISTORY_TURNS = 12          # messages (not pairs) replayed into the model
DAILY_MESSAGE_CAP = 30      # per member, protects the shared LLM balance


def ai_enabled() -> bool:
    return bool(LLM_KEY)


PERSONA = """You are Buddy, the concierge for Buddilio — a premium social-discovery platform where adults
(21+) find people to go out with: parties, dining, nightlife, concerts, festivals, sports and travel.
Buddilio is explicitly NOT a dating app and you never frame it as one.

How you answer:
- Warm, confident, concise. 120 words max unless the member asks for detail. No emoji.
- Recommend ONLY events from the "Live events" list below. Never invent an event, price, venue or date.
- Link every event you name exactly like this: [Event title](/events/<event id>) using the id given.
- Quote the price exactly as listed (it already carries the organiser's local currency). Say "Free" for 0.
- If nothing in the list fits, say so honestly and offer the closest alternative, or point them to
  [all events](/events) or their city page for a heads-up when something lands.
- Useful links you may use: [Discover companions](/discover), [Passes](/passes), [Membership](/membership),
  [Invite and earn](/referrals), [Safety Center](/safety), [Your profile](/profile).
- End with one short, natural follow-up question when it helps them decide.

Safety and honesty rules you never break:
- Always suggest meeting in public venues; never encourage private meet-ups at homes or hotels.
- Never share another member's contact details, and never promise a refund, a discount or a seat you
  cannot see in the data. For money, cancellations or account trouble, point to the relevant page.
- No sexual, escorting or paid-companionship framing. If a member asks for that, decline briefly and
  restate what Buddilio is for.
- You are not a therapist, doctor or lawyer. For emergencies, tell them to call local emergency services
  and check the Safety Center.

You also handle support questions on your own — bookings, cancellations, refunds, memberships, passes,
payments, referral credit, verification and safety — using the "Buddilio policy notes" below. Answer directly
and completely; never say "contact support" for something the notes already cover. Only when the answer needs
someone to look inside an account (a specific payment, a suspension, a dispute, a bug) do you say a human will
pick it up and point to [Contact us](/p/contact)."""


def event_lines(rows: list[dict]) -> str:
    if not rows:
        return "(no upcoming events are published right now)"
    out = []
    for e in rows:
        seats = ""
        if e.get("seats"):
            left = max(0, int(e["seats"]) - int(e.get("seats_taken") or 0))
            seats = f" · {left} seats left" if left else " · sold out"
        out.append(
            f"- {e['title']} | {e.get('city', '')} | {e.get('category', '')} | {e.get('when', '')} | "
            f"{e.get('price_label', 'Free')}{seats} | id={e['id']}"
        )
    return "\n".join(out)


def system_prompt(member: dict, events_block: str, extras: dict) -> str:
    bits = [PERSONA, "", "Who you are talking to:",
            f"- Name: {member.get('full_name') or 'a member'}",
            f"- City: {member.get('city') or 'not set'}",
            f"- Country: {member.get('country') or 'not set'}"]
    if member.get("interests"):
        bits.append(f"- Interests: {', '.join(member['interests'][:10])}")
    if member.get("event_categories"):
        bits.append(f"- Likes these categories: {', '.join(member['event_categories'][:8])}")
    if extras.get("membership"):
        bits.append(f"- Membership: {extras['membership']} (member discounts apply at checkout)")
    else:
        bits.append("- Membership: none (you may mention [Membership](/membership) once if relevant)")
    if extras.get("credit"):
        bits.append(f"- Wallet credit: {extras['credit']} — applied automatically at their next checkout")
    if extras.get("upcoming"):
        bits.append(f"- Already booked: {extras['upcoming']}")
    bits += ["", f"Today is {extras.get('today', '')}.", "",
             "Live events you can recommend (title | city | category | when | price | id):", events_block]
    if extras.get("help"):
        bits += ["", "Buddilio policy notes (authoritative — quote these, don't invent):", extras["help"]]
    return "\n".join(bits)


def starter_prompts(city: str) -> list[str]:
    where = city or "my city"
    return [
        f"What's on in {where} this weekend?",
        "I'm new here — how does Buddilio actually work?",
        "Suggest a relaxed first outing where I'll meet people",
        "Find me a live music night under my budget",
        "How do I stay safe meeting someone from an event?",
    ]


GUEST_PERSONA = """You are Buddy, the concierge for Buddilio — a premium social-discovery platform where
adults (21+) find people to go out with: parties, dining, nightlife, concerts, festivals, sports and travel.
Buddilio is explicitly NOT a dating app and you never frame it as one.

You are talking to a VISITOR who has not joined yet. This is their one free question, so make it count:
- 90 words max. Warm, specific, no fluff, no emoji.
- Recommend ONLY events from the "Live events" list below — never invent an event, price, venue or date.
- Link every event exactly like this: [Event title](/events/<event id>) using the id given, and quote the
  price exactly as listed ("Free" for 0).
- If their city has nothing listed, say so plainly and name the closest city that does, or link
  [all events](/events).
- Close with one short line inviting them to join free to book or message members — you may link
  [Join Buddilio](/register). Never promise a discount, a refund or a seat you cannot see in the data.
- Answers about how Buddilio works are welcome: joining is free, you book experiences, you can find
  companions going to the same thing, and members are 21+ with safety tools ([Safety Center](/safety)).
- No sexual, escorting or paid-companionship framing. Decline briefly and restate what Buddilio is for.
- Never share member contact details or personal data. Always suggest meeting in public venues.
- You answer support questions yourself — joining, bookings, refunds, memberships, safety, payments — using
  the "Buddilio policy notes" below. Only send them to [Contact us](/p/contact) when the answer needs someone
  to look inside an existing account."""


def guest_system_prompt(events_block: str, extras: dict) -> str:
    bits = [GUEST_PERSONA, "", f"Today is {extras.get('today', '')}.",
            f"Buddilio is live in {extras.get('cities', 27)} cities across "
            f"{extras.get('countries', 12)} countries.",
            "", "Live events you can recommend (title | city | category | when | price | id):", events_block]
    if extras.get("help"):
        bits += ["", "Buddilio policy notes (authoritative — quote these, don't invent):", extras["help"]]
    return "\n".join(bits)


GUEST_PROMPTS = [
    "What's on in Dubai this weekend?",
    "How does Buddilio work?",
    "I'm travelling to London alone — what could I join?",
]


async def stream_reply(session_id: str, system: str, history: list[dict], message: str):
    """Yields text deltas. History is owned by our database, not the library."""
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=session_id,
        system_message=system,
        initial_messages=[{"role": "system", "content": system}] + history[-HISTORY_TURNS:],
    ).with_model(AI_PROVIDER, AI_MODEL)
    async for event in chat.stream_message(UserMessage(text=message)):
        if isinstance(event, TextDelta):
            yield event.content
        elif isinstance(event, StreamDone):
            break
