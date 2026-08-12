"""Give every published event a price in its own city's currency (organiser-style local pricing)."""
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = os.environ.get("BASE_CURRENCY", "INR")

RATES = {"INR": 1.0, "USD": 0.012, "EUR": 0.011, "GBP": 0.0094, "AED": 0.044, "SGD": 0.016,
         "CAD": 0.016, "AUD": 0.018, "THB": 0.39, "JPY": 1.8}
CURRENCY_BY_COUNTRY = {"IN": "INR", "AE": "AED", "SG": "SGD", "GB": "GBP", "US": "USD", "CA": "CAD",
                       "AU": "AUD", "DE": "EUR", "ES": "EUR", "FR": "EUR", "TH": "THB", "JP": "JPY"}
STEP = {"JPY": 500, "THB": 100, "INR": 50}


def tidy(amount: float, currency: str) -> float:
    step = STEP.get(currency, 5)
    return float(max(step, round(amount / step) * step))


async def main():
    changed = 0
    for ev in await db.events.find({"price": {"$gt": 0}}).to_list(500):
        cur = CURRENCY_BY_COUNTRY.get(ev.get("country_code", ""), BASE)
        local = tidy(ev["price"] * RATES[cur], cur)
        update = {"price_currency": cur, "price_input": local,
                  "price_overrides": {} if cur == BASE else {cur: local},
                  "price": local if cur == BASE else round(local / RATES[cur], 2)}
        await db.events.update_one({"_id": ev["_id"]}, {"$set": update})
        changed += 1
        print(f"{ev['city']:<12} {ev['title'][:38]:<40} {cur} {local:g}")
    print(f"\n{changed} events now priced in their own city's currency")


asyncio.run(main())
