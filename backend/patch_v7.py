"""Apply city pages, referral leaderboard and organiser local pricing to server.py."""
from pathlib import Path

p = Path("/app/backend/server.py")
src = p.read_text()


def patch(anchor: str, replacement: str, label: str):
    global src
    assert src.count(anchor) == 1, f"{label}: anchor found {src.count(anchor)} times"
    src = src.replace(anchor, replacement)
    print(f"ok  {label}")


# ---- 1. city helpers + city pages -------------------------------------------------
patch(
    '@api.get("/meta")',
    '''def city_slug(name: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in (name or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def find_city(slug: str) -> tuple[str, dict]:
    for c in COUNTRIES:
        for city in c["cities"]:
            if city_slug(city) == slug:
                return city, c
    raise HTTPException(status_code=404, detail="Buddilio isn't in that city yet.")


def short_name(full: str) -> str:
    parts = [p for p in (full or "").split(" ") if p]
    if not parts:
        return "Member"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


@api.get("/cities")
async def list_city_pages():
    ev_counts = {d["_id"]: d["n"] for d in await db.events.aggregate(
        [{"$match": {"status": "published"}}, {"$group": {"_id": "$city", "n": {"$sum": 1}}}]).to_list(500)}
    mem_counts = {d["_id"]: d["n"] for d in await db.users.aggregate(
        [{"$match": {"role": "user", "status": "active"}}, {"$group": {"_id": "$city", "n": {"$sum": 1}}}]).to_list(500)}
    items = []
    for c in COUNTRIES:
        for city in c["cities"]:
            events = ev_counts.get(city, 0)
            items.append({"name": city, "slug": city_slug(city), "country": c["name"],
                          "country_code": c["code"], "currency": c["currency"],
                          "events": events, "members": mem_counts.get(city, 0), "live": events > 0})
    items.sort(key=lambda i: (-i["events"], i["name"]))
    return {"items": items, "cities": len(items), "countries": len(COUNTRIES),
            "live_cities": sum(1 for i in items if i["live"])}


@api.get("/cities/{slug}")
async def city_page(slug: str):
    city, country = find_city(slug)
    stamp = iso(now_utc())
    upcoming = await db.events.find({"city": city, "status": "published", "starts_at": {"$gte": stamp}}) \\
        .sort([("starts_at", 1)]).limit(6).to_list(6)
    published = await db.events.find({"city": city, "status": "published"},
                                     {"_id": 1, "cover_image": 1, "category": 1, "starts_at": 1}).to_list(300)
    ids = [str(e["_id"]) for e in published]
    quotes = []
    for r in await db.reviews.find({"event_id": {"$in": ids}, "status": {"$ne": "hidden"},
                                    "comment": {"$nin": ["", None]}}) \\
            .sort([("rating", -1), ("created_at", -1)]).limit(2).to_list(2):
        try:
            u = await db.users.find_one({"_id": ObjectId(r["user_id"])}, {"full_name": 1})
        except Exception:
            u = None
        quotes.append({"rating": r["rating"], "comment": r["comment"],
                       "user_name": short_name((u or {}).get("full_name", ""))})
    faces = [{"id": str(u["_id"]), "name": short_name(u.get("full_name", "")), "photo": u.get("photo", "")}
             for u in await db.users.find({"city": city, "role": "user", "status": "active",
                                           "photo": {"$nin": ["", None]}},
                                          {"full_name": 1, "photo": 1}).limit(8).to_list(8)]
    hero = next((e.get("cover_image") for e in upcoming if e.get("cover_image")), "") \\
        or next((e.get("cover_image") for e in published if e.get("cover_image")), "")
    return {
        "name": city, "slug": slug, "country": country["name"], "country_code": country["code"],
        "currency": country["currency"], "tax_label": country["tax_label"],
        "tax_percent": country["tax_percent"], "emergency": country["emergency"],
        "hero": hero, "upcoming": [clean(e) for e in upcoming],
        "events_total": len(ids),
        "past_events": sum(1 for e in published if e.get("starts_at", "") < stamp),
        "members": await db.users.count_documents({"city": city, "role": "user", "status": "active"}),
        "organisers": await db.users.count_documents({"city": city, "role": "partner"}),
        "categories": sorted({e.get("category", "") for e in published if e.get("category")}),
        "faces": faces, "quotes": quotes,
        "waiting": await db.city_waitlist.count_documents({"city": city}),
        "nearby": [{"name": n, "slug": city_slug(n)} for n in country["cities"] if n != city][:6],
    }


@api.post("/cities/{slug}/waitlist")
async def join_city_waitlist(slug: str, body: dict):
    city, _ = find_city(slug)
    email = (body.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    await db.city_waitlist.update_one(
        {"city": city, "email": email},
        {"$set": {"city": city, "email": email, "updated_at": iso(now_utc())},
         "$setOnInsert": {"created_at": iso(now_utc())}}, upsert=True)
    return {"message": f"You're on the list for {city} — we'll email you the moment we open.",
            "waiting": await db.city_waitlist.count_documents({"city": city})}


@api.get("/meta")''',
    "city endpoints",
)

# ---- 2. referral badges + leaderboard --------------------------------------------
patch(
    '''async def register_referral(code: str, invitee_id: str, invitee_name: str):''',
    '''BADGES = [(10, "Legend"), (5, "Ambassador"), (3, "Connector"), (1, "Starter")]


def badge_for(count: int) -> dict:
    """Lifetime rewarded invites decide the badge; `next` is the invites needed for the following tier."""
    nxt = next((n for n, _ in reversed(BADGES) if n > count), 0)
    for need, name in BADGES:
        if count >= need:
            return {"name": name, "at": need, "next": nxt}
    return {"name": "", "at": 0, "next": 1}


async def register_referral(code: str, invitee_id: str, invitee_name: str):''',
    "badge helper",
)

patch(
    '''@api.get("/referrals/{code}")''',
    '''@api.get("/referrals/leaderboard")
async def referral_leaderboard(month: str = "", user: dict = Depends(get_current_user)):
    month = (month or now_utc().strftime("%Y-%m"))[:7]
    docs = await db.referrals.find({"status": "rewarded",
                                    "rewarded_at": {"$regex": f"^{month}"}},
                                   {"referrer_id": 1}).to_list(5000)
    tally: dict[str, int] = {}
    for d in docs:
        tally[d["referrer_id"]] = tally.get(d["referrer_id"], 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = []
    for i, (uid, count) in enumerate(ranked[:10]):
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"full_name": 1, "photo": 1, "city": 1})
        except Exception:
            u = None
        lifetime = await db.referrals.count_documents({"referrer_id": uid, "status": "rewarded"})
        rows.append({"rank": i + 1, "name": short_name((u or {}).get("full_name", "")),
                     "photo": (u or {}).get("photo", ""), "city": (u or {}).get("city", ""),
                     "invites": count, "credit": round(count * REFERRAL_REWARD, 2),
                     "badge": badge_for(lifetime)["name"], "me": uid == user["id"]})
    mine = tally.get(user["id"], 0)
    lifetime = await db.referrals.count_documents({"referrer_id": user["id"], "status": "rewarded"})
    return {"month": month, "items": rows, "reward": REFERRAL_REWARD,
            "me": {"rank": next((i + 1 for i, (uid, _) in enumerate(ranked) if uid == user["id"]), 0),
                   "invites": mine, "lifetime": lifetime,
                   "credit": round(mine * REFERRAL_REWARD, 2), "badge": badge_for(lifetime)},
            "participants": len(ranked)}


@api.get("/referrals/{code}")''',
    "leaderboard endpoint",
)

patch(
    '''    return {"code": code, "link": f"{FRONTEND_URL}/register?ref={code}", "reward": REFERRAL_REWARD,
            "balance": await credit_balance(user["id"]), "invites": invites, "credits": credits,
            "joined": len(invites), "rewarded": sum(1 for i in invites if i["status"] == "rewarded")}''',
    '''    rewarded = sum(1 for i in invites if i["status"] == "rewarded")
    return {"code": code, "link": f"{FRONTEND_URL}/register?ref={code}", "reward": REFERRAL_REWARD,
            "balance": await credit_balance(user["id"]), "invites": invites, "credits": credits,
            "joined": len(invites), "rewarded": rewarded, "badge": badge_for(rewarded)}''',
    "badge on my referrals",
)

# ---- 3. organiser local pricing ---------------------------------------------------
patch(
    '''    price: float = 0
    capacity: int = 50''',
    '''    price: float = 0
    price_currency: str = ""
    capacity: int = 50''',
    "EventIn.price_currency",
)

patch(
    '''def with_country(doc: dict) -> dict:''',
    '''async def price_event(doc: dict) -> dict:
    """Organisers price in their city's own currency; we store the base amount plus an exact-currency override."""
    cur = (doc.pop("price_currency", "") or BASE_CURRENCY).upper()
    rates = await fx_rates()
    if cur not in rates:
        raise HTTPException(status_code=400, detail="We don't support that currency yet.")
    amount = round(float(doc.get("price") or 0), 2)
    rate = rates[cur] or 1.0
    doc["price_currency"] = cur
    doc["price_input"] = amount
    if cur == BASE_CURRENCY:
        doc["price"], doc["price_overrides"] = amount, {}
    else:
        doc["price"] = round(amount / rate, 2)
        doc["price_overrides"] = {cur: amount}
    return doc


def with_country(doc: dict) -> dict:''',
    "price_event helper",
)

patch(
    '''    doc = with_country(payload.model_dump())''',
    '''    doc = await price_event(with_country(payload.model_dump()))''',
    "create_event pricing",
)

patch(
    '''    await db.events.update_one({"_id": ev["_id"]}, {"$set": with_country(payload.model_dump())})''',
    '''    await db.events.update_one({"_id": ev["_id"]},
                               {"$set": await price_event(with_country(payload.model_dump()))})''',
    "update_event pricing",
)

patch(
    '''    await db.push_subscriptions.create_index("endpoint", unique=True)''',
    '''    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.city_waitlist.create_index([("city", 1), ("email", 1)], unique=True)''',
    "waitlist index",
)

p.write_text(src)
import ast
ast.parse(src)
print("server.py patched and parses cleanly")
