"""Shared test hygiene: purge the TEST_* artefacts suites create so they never reach public pages."""
import os
from pathlib import Path

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TEST_TITLE = {"$regex": "^TEST", "$options": "i"}
TEST_EMAIL = {"$regex": "^test_|^TEST_", "$options": "i"}


@pytest.fixture(scope="session", autouse=True)
def purge_test_artifacts():
    yield
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    events = list(db.events.find({"title": TEST_TITLE}, {"_id": 1}))
    eids = [str(e["_id"]) for e in events]
    if eids:
        db.orders.delete_many({"ref_id": {"$in": eids}})
        db.event_participants.delete_many({"event_id": {"$in": eids}})
        db.conversations.delete_many({"event_id": {"$in": eids}})
        db.reviews.delete_many({"event_id": {"$in": eids}})
        db.events.delete_many({"_id": {"$in": [ObjectId(i) for i in eids]}})

    users = list(db.users.find({"$or": [{"full_name": TEST_TITLE}, {"email": TEST_EMAIL}]}, {"_id": 1}))
    uids = [str(u["_id"]) for u in users]
    if uids:
        for r in db.referrals.find({"invitee_id": {"$in": uids}}, {"_id": 1}):
            db.credits.delete_many({"referral_id": str(r["_id"])})
        db.referrals.delete_many({"$or": [{"invitee_id": {"$in": uids}}, {"referrer_id": {"$in": uids}}]})
        db.orders.delete_many({"user_id": {"$in": uids}})
        db.credits.delete_many({"user_id": {"$in": uids}})
        db.event_participants.delete_many({"user_id": {"$in": uids}})
        db.users.delete_many({"_id": {"$in": [ObjectId(i) for i in uids]}})

    db.city_waitlist.delete_many({"email": TEST_EMAIL})
    print(f"\n[conftest] purged {len(eids)} TEST events and {len(uids)} TEST users")
