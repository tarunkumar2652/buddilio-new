"""Seed / cleanup helper for iteration-38 UI testing.  python i38_seed.py seed|clean"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BANK = {"bank_account_name": "TEST_ UI Vendor", "bank_account_number": "123456789012",
        "bank_ifsc": "ICIC0000123", "bank_name": "ICICI Bank", "bank_branch": "Andheri",
        "bank_account_type": "current", "bank_swift": "", "upi_id": ""}


def clean():
    ids = [str(v["_id"]) for v in db.vendor_profiles.find({"legal_name": {"$regex": "^TEST_"}})]
    db.vendor_settlements.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_payout_batches.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_commission_invoices.delete_many({"vendor_id": {"$in": ids}})
    db.vendor_profiles.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
    print("cleaned vendors:", ids)
    print("vendors left:", db.vendor_profiles.count_documents({}),
          "settlements:", db.vendor_settlements.count_documents({}),
          "batches:", db.vendor_payout_batches.count_documents({}),
          "CIs:", [c["invoice_no"] for c in db.vendor_commission_invoices.find({}, {"invoice_no": 1})])


def seed():
    clean()
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=3)).isoformat()
    created = (now - timedelta(days=40)).isoformat()
    a = db.vendor_profiles.insert_one({
        "legal_name": "TEST_ UI Payable Vendor", "email": "test_ui_a@example.com", "user_id": "",
        "status": "approved", "vendor_kind": "venue", "payout_hold": False, "pan": "AAACT1234A",
        "registered_address": "1 Test Road, Mumbai", **BANK}).inserted_id
    b = db.vendor_profiles.insert_one({
        "legal_name": "TEST_ UI Held Vendor", "email": "test_ui_b@example.com", "user_id": "",
        "status": "approved", "vendor_kind": "venue", "payout_hold": True,
        "payout_hold_reason": "bank verification pending", **BANK}).inserted_id

    def s(vid, gross, n):
        return {"vendor_id": str(vid), "booking_id": f"TEST_{vid}_{n}", "order_no": f"TESTORD{n}",
                "gross": gross, "commission": round(gross * 0.1, 2), "platform_fee": round(gross * 0.05, 2),
                "refunds": 0.0, "adjustments": 0.0, "net": round(gross * 0.85, 2), "currency": "INR",
                "status": "pending", "due_on": past, "created_at": created}
    db.vendor_settlements.insert_many([s(a, 1000.0, 1), s(a, 2000.0, 2), s(b, 500.0, 3)])
    print("seeded", {"payable": str(a), "held": str(b), "period": created[:7]})


if __name__ == "__main__":
    (seed if sys.argv[1] == "seed" else clean)()
