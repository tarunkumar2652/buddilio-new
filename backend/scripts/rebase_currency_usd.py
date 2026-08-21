"""One-off: move the platform base currency from INR to USD.

Converts forward-looking catalogue prices (plans, products, events, coupons, commercial schedules,
settings fees) at RATE and rebases the currency table so USD = 1. Historical money — orders,
payments, payouts, settlements, snapshots, credits — is left exactly as it was, because each of those
rows already carries the currency it was charged in and rewriting them would falsify the books.

    python scripts/rebase_currency_usd.py            # dry run
    python scripts/rebase_currency_usd.py --apply
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

RATE = float(os.environ.get("REBASE_INR_PER_USD", "83.33"))     # 1 USD = 83.33 INR
APPLY = "--apply" in sys.argv

CURRENCIES = {
    "USD": {"rate": 1.0, "symbol": "$", "label": "US Dollar", "stripe_min": 50},
    "INR": {"rate": RATE, "symbol": "₹", "label": "Indian Rupee", "stripe_min": 4200},
    "EUR": {"rate": 0.92, "symbol": "€", "label": "Euro", "stripe_min": 50},
    "GBP": {"rate": 0.79, "symbol": "£", "label": "British Pound", "stripe_min": 30},
    "AED": {"rate": 3.67, "symbol": "AED ", "label": "UAE Dirham", "stripe_min": 200},
    "SGD": {"rate": 1.34, "symbol": "S$", "label": "Singapore Dollar", "stripe_min": 50},
    "CAD": {"rate": 1.36, "symbol": "C$", "label": "Canadian Dollar", "stripe_min": 50},
    "AUD": {"rate": 1.50, "symbol": "A$", "label": "Australian Dollar", "stripe_min": 50},
    "THB": {"rate": 32.5, "symbol": "฿", "label": "Thai Baht", "stripe_min": 1000},
    "JPY": {"rate": 150.0, "symbol": "¥", "label": "Japanese Yen", "stripe_min": 50},
}

# collection -> plain money fields converted from INR to USD
PLAIN = {
    "membership_plans": ["price"],
    "products": ["price"],
    "events": ["price", "price_input"],
    "commercial_schedules": ["vendor_net_rate", "pricing_floor", "commission_fixed",
                             "platform_fee_fixed"],
}


def usd(v) -> float:
    return round(float(v or 0) / RATE, 2)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    changed = 0

    for coll, fields in PLAIN.items():
        async for doc in db[coll].find({}):
            if doc.get("currency") and str(doc["currency"]).upper() == "USD":
                continue                                    # already priced in USD
            update = {f: usd(doc[f]) for f in fields if isinstance(doc.get(f), (int, float))}
            if coll == "events":
                if str(doc.get("price_currency") or "INR").upper() == "INR":
                    update["price_currency"] = "USD"
                    update["price_overrides"] = {}
                else:
                    update.pop("price_input", None)         # keep the organiser's own-currency amount
            if coll == "commercial_schedules":
                update["currency"] = "USD"
            if not update:
                continue
            changed += 1
            print(f"{coll} {doc.get('name') or doc.get('title') or doc['_id']}: {update}")
            if APPLY:
                await db[coll].update_one({"_id": doc["_id"]}, {"$set": update})

    async for p in db.products.find({"price_overrides": {"$exists": True, "$ne": {}}}):
        if APPLY:
            await db.products.update_one({"_id": p["_id"]}, {"$set": {"price_overrides": {}}})
        print(f"products {p.get('name')}: cleared stale price_overrides")

    async for c in db.coupons.find({}):
        update = {}
        if c.get("discount_type") != "percent" and isinstance(c.get("value"), (int, float)):
            update["value"] = usd(c["value"])
        if isinstance(c.get("min_order"), (int, float)) and c["min_order"]:
            update["min_order"] = usd(c["min_order"])
        if update:
            changed += 1
            print(f"coupons {c.get('code')}: {update}")
            if APPLY:
                await db.coupons.update_one({"_id": c["_id"]}, {"$set": update})

    s = await db.settings.find_one({})
    sett = {"currency": "USD", "base_currency": "USD", "currencies": CURRENCIES}
    if isinstance(s.get("hangout_request_fee"), (int, float)) and s["hangout_request_fee"]:
        sett["hangout_request_fee"] = usd(s["hangout_request_fee"])
    print(f"settings: currency USD, hangout fee {sett.get('hangout_request_fee', s.get('hangout_request_fee'))}, "
          f"{len(CURRENCIES)} currencies rebased to USD=1")
    if APPLY:
        await db.settings.update_one({"_id": s["_id"]}, {"$set": sett})

    print(f"\n{'APPLIED' if APPLY else 'DRY RUN'} · rate 1 USD = {RATE} INR · {changed} priced rows")


asyncio.run(main())
