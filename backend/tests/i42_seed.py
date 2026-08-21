"""Seeds iteration-42 fixtures (partner event passes for door + pass reminder). --clean removes them."""
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
db = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
MEMBER = "arjun.sethi@example.com"
PARTNER = "partner@buddilio.com"
TAG = "TEST_I42_DOOR"


def clean():
    oids = [str(o["_id"]) for o in db.orders.find({"item_name": TAG}, {"_id": 1})]
    db.passes.delete_many({"order_id": {"$in": oids}})
    db.orders.delete_many({"item_name": TAG})
    print("cleaned orders:", len(oids))


if "--clean" in sys.argv:
    clean()
    sys.exit(0)

clean()
member = db.users.find_one({"email": MEMBER})
partner = db.users.find_one({"email": PARTNER})
ev = db.events.find_one({"partner_id": str(partner["_id"]), "status": "published"})
other = db.events.find_one({"partner_id": {"$ne": str(partner["_id"])}, "status": "published"})
tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
starts = tomorrow.isoformat()

oid = db.orders.insert_one({
    "order_no": "TESTI42" + uuid.uuid4().hex[:5].upper(), "user_id": str(member["_id"]),
    "user_email": MEMBER, "kind": "event", "ref_id": str(ev["_id"]), "item_name": TAG,
    "quantity": 2, "subtotal": 100.0, "discount": 0.0, "tax": 0.0, "total": 100.0,
    "currency": "USD", "charge_total": 100.0, "base_currency": "USD", "payment_status": "paid",
    "order_status": "completed", "refund_status": "none", "gateway": "paypal",
    "transaction_id": "TESTI42TXN" + uuid.uuid4().hex[:6],
    "created_at": starts, "paid_at": starts}).inserted_id


db.orders.update_one({"_id": oid}, {"$set": {"cancellation": {
    "status": "requested", "requested_at": starts, "reason": "TEST_I42 policy ceiling",
    "deduction_percent": 70, "refundable": 30.0, "prefer": "refund",
    "policy_note": "70% deducted (less than 2 days notice)."}}})


def mk(suffix, quantity):
    block = uuid.uuid4().hex[:4].upper().translate(str.maketrans("01IO", "ABJK"))
    code = f"BUD-{block}-{suffix}"
    db.passes.insert_one({
        "code": code, "order_id": str(oid), "order_no": "TESTI42", "user_id": str(member["_id"]),
        "user_name": member.get("full_name", ""), "kind": "event", "ref_id": str(ev["_id"]),
        "item_name": TAG, "quantity": quantity, "city": ev.get("city", ""), "starts_at": starts,
        "vendor_name": "Buddilio", "amount_label": "$100.00", "status": "valid",
        "redeemed_at": "", "redeemed_by": "", "redeemed_by_name": "", "created_at": starts})
    return code


print("EVENT_ID=" + str(ev["_id"]))
print("OTHER_EVENT_ID=" + str(other["_id"]))
print("DOOR_CODE=" + mk("91", 2))
print("UI_CODE=" + mk("92", 1))
print("REMIND_CODE=" + mk("93", 1))
print("ORDER_ID=" + str(oid))
