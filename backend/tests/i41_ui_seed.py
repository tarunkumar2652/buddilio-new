"""Seeds one paid order + valid Buddilio Pass for the member (UI test), or cleans up with --clean."""
import sys
import uuid

from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
db = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
MEMBER = "arjun.sethi@example.com"
TAG = "TEST_UI_PASS"

if "--clean" in sys.argv:
    oids = [str(o["_id"]) for o in db.orders.find({"item_name": TAG}, {"_id": 1})]
    db.passes.delete_many({"order_id": {"$in": oids}})
    db.orders.delete_many({"item_name": TAG})
    print("cleaned", len(oids))
else:
    user = db.users.find_one({"email": MEMBER})
    oid = db.orders.insert_one({
        "order_no": "TESTUI" + uuid.uuid4().hex[:5].upper(), "user_id": str(user["_id"]),
        "user_email": MEMBER, "kind": "product", "ref_id": "", "item_name": TAG, "quantity": 2,
        "subtotal": 150.0, "discount": 0.0, "tax": 0.0, "total": 150.0, "currency": "USD",
        "charge_total": 150.0, "base_currency": "INR", "payment_status": "paid",
        "order_status": "completed", "refund_status": "none", "gateway": "paypal",
        "transaction_id": "TESTUITXN" + uuid.uuid4().hex[:6],
        "created_at": "2026-07-01T00:00:00+00:00", "paid_at": "2026-07-01T00:00:00+00:00"}).inserted_id
    block = uuid.uuid4().hex[:4].upper().replace("0", "A").replace("1", "B").replace("I", "J") \
        .replace("O", "K")
    code = f"BUD-{block}-99"
    db.passes.insert_one({
        "code": code, "order_id": str(oid), "order_no": "TESTUI", "user_id": str(user["_id"]),
        "user_name": user.get("full_name", ""), "kind": "product", "ref_id": "", "item_name": TAG,
        "quantity": 2, "city": "Mumbai", "starts_at": "", "vendor_name": "Buddilio",
        "amount_label": "$150.00", "status": "valid", "redeemed_at": "", "redeemed_by": "",
        "redeemed_by_name": "", "created_at": "2026-07-01T00:00:00+00:00"})
    print(f"order={oid} code={code}")
