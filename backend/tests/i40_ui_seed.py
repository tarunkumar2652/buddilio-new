"""Seeds UI fixtures for iteration-40 frontend tests: one pending order for the member,
one simulated paid order and one partially-refunded simulated order (admin refund UI)."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from bson import ObjectId
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path('/app/backend/.env'))
BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def iso():
    return datetime.now(timezone.utc).isoformat()


def cleanup():
    n = db.orders.delete_many({"order_no": {"$regex": "^TESTUI"}}).deleted_count
    print(f"deleted {n} TESTUI orders")


if len(sys.argv) > 1 and sys.argv[1] == "clean":
    cleanup()
    raise SystemExit

tok = requests.post(f"{API}/auth/login",
                    json={"email": "arjun.sethi@example.com", "password": "User@12345"},
                    timeout=30).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
uid = requests.get(f"{API}/auth/me", headers=h, timeout=30).json()["id"]
prod = db.products.find_one({"active": True}) or db.products.find_one({})

r = requests.post(f"{API}/checkout", headers=h,
                  json={"kind": "product", "item_id": str(prod["_id"]), "quantity": 1,
                        "currency": "INR", "use_credit": False}, timeout=60)
pending = r.json()["order"]["id"]
db.orders.update_one({"_id": ObjectId(pending)},
                     {"$set": {"order_no": "TESTUI" + uuid.uuid4().hex[:6].upper(),
                               "payment_status": "failed", "order_status": "failed",
                               "failure_reason": "card declined"}})


def paid(refunded=0.0, total=1000.0):
    doc = {"order_no": "TESTUI" + uuid.uuid4().hex[:6].upper(), "user_id": uid,
           "user_email": "arjun.sethi@example.com", "user_name": "Arjun Sethi",
           "kind": "product", "ref_id": str(prod["_id"]), "item_name": "TEST_ UI Paid Pass",
           "quantity": 1, "subtotal": total, "discount": 0.0, "tax": 0.0, "total": total,
           "tax_percent": 0.0, "tax_label": "No tax", "credit_applied": 0.0, "charge_credit": 0.0,
           "coupon": "", "currency": "INR", "fx_rate": 1.0, "base_currency": "INR",
           "charge_subtotal": total, "charge_discount": 0.0, "charge_tax": 0.0,
           "charge_total": total, "payment_status": "paid", "order_status": "completed",
           "refund_status": "partial" if refunded else "none",
           "refunded_amount": refunded, "gateway": "stripe_sim",
           "transaction_id": "TESTUI_sim_" + uuid.uuid4().hex[:6],
           "created_at": iso(), "paid_at": iso()}
    return str(db.orders.insert_one(doc).inserted_id)


out = {"pending": pending, "paid": paid(), "partial": paid(refunded=250.0)}
print(json.dumps(out))
Path("/tmp/i40_ui_ids.json").write_text(json.dumps(out))
