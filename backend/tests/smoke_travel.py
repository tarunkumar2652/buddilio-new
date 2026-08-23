import os, requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv("/app/backend/.env")
BASE = "https://lifestyle-connect-17.preview.emergentagent.com"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(e, p):
    return requests.post(f"{BASE}/api/auth/login", json={"email": e, "password": p}, timeout=30).json()["access_token"]


def h(t):
    return {"Authorization": f"Bearer {t}"}


trav = login("tara.joshi@example.com", "User@12345")
prov = login("kabir.nair@example.com", "User@12345")
admin = login("admin@buddilio.com", "Admin@123")
tid = str(DB.users.find_one({"email": "tara.joshi@example.com"})["_id"])
pid = str(DB.users.find_one({"email": "kabir.nair@example.com"})["_id"])
DB.users.update_one({"_id": ObjectId(pid)}, {"$unset": {"provider": ""}})
DB.trips.delete_many({"host_id": {"$in": [tid, pid]}})
DB.travel_bookings.delete_many({"traveller_id": tid})
DB.service_requests.delete_many({"traveller_id": tid})
DB.payouts.delete_many({"kind": "travel"})

print("meta:", requests.get(f"{BASE}/api/travel/meta", headers=h(trav)).json()["provider_fee"])

# 1. trip posted and joined for free
t = requests.post(f"{BASE}/api/travel/trips", headers=h(trav), json={
    "title": "Kedarkantha trek", "destination": "Dehradun", "activity": "Trekking", "group_size": 4,
    "budget": 12000, "starts_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
    "notes": "<p>Moderate trek, 4 nights</p>"}).json()
print("trip:", t["title"], t["status"], t["joined"])
j = requests.post(f"{BASE}/api/travel/trips/{t['id']}/join", headers=h(prov), json={"note": "Count me in"})
print("join:", j.status_code, j.json())
reqs = requests.get(f"{BASE}/api/travel/trips/{t['id']}/requests", headers=h(trav)).json()["items"]
print("host sees:", [(r["name"], r["status"]) for r in reqs])
print("outsider 403:", requests.get(f"{BASE}/api/travel/trips/{t['id']}/requests", headers=h(prov)).status_code)
d = requests.post(f"{BASE}/api/travel/trips/{t['id']}/requests/{reqs[0]['id']}", headers=h(trav),
                  json={"action": "approve", "note": ""})
print("approve:", d.json())

# 2. provider registration: fee -> pending -> approved
ap = requests.post(f"{BASE}/api/me/provider", headers=h(prov), json={
    "roles": ["trek_guide", "cook"], "day_rate": 2000, "destinations": ["Dehradun", "Manali"],
    "languages": ["Hindi", "English"], "headline": "Himalayan trek lead, 40+ summits",
    "about": "<p>I run winter treks</p>", "experience_years": 8, "accept_terms": True,
    "documents": [{"url": "/api/files/test-doc.pdf", "name": "Guide licence"}]}).json()
print("apply:", ap["status"], ap.get("provider_fee"))
o = requests.post(f"{BASE}/api/checkout", headers=h(prov),
                  json={"kind": "provider_fee", "item_id": pid, "use_credit": False}).json()["order"]
print("fee order:", o["total"])
requests.post(f"{BASE}/api/payments/verify", headers=h(prov), json={"order_id": o["id"]})
print("after fee:", DB.users.find_one({"_id": ObjectId(pid)}, {"provider.status": 1, "provider.fee_paid": 1}))
print("early approve blocked?", requests.post(f"{BASE}/api/admin/providers/{pid}", headers=h(admin),
                                              json={"action": "approve", "note": ""}).json())
lst = requests.get(f"{BASE}/api/travel/providers", headers=h(trav)).json()
me = [i for i in lst["items"] if i["id"] == pid]
print("listed:", [(i["name"], i["day_price"]) for i in me], "(2000 + 18% markup = 2360)")

# 3. booking + payout 75/25
bk = requests.post(f"{BASE}/api/travel/providers/{pid}/bookings", headers=h(trav), json={
    "days": 3, "starts_at": (datetime.now(timezone.utc) + timedelta(days=25)).isoformat(), "people": 1}).json()
print("booking:", bk["amount"])
o2 = requests.post(f"{BASE}/api/checkout", headers=h(trav),
                   json={"kind": "travel", "item_id": bk["booking_id"], "use_credit": False}).json()["order"]
requests.post(f"{BASE}/api/payments/verify", headers=h(trav), json={"order_id": o2["id"]})
b = DB.travel_bookings.find_one({"_id": ObjectId(bk["booking_id"])})
print("confirmed:", b["status"], b["amount"], b["provider_net"], b["platform_fee"])
print("payout:", DB.payouts.find_one({"booking_id": bk["booking_id"]}, {"net": 1, "fee": 1, "kind": 1}))

# 4. service request -> quote -> accept -> pay
sr = requests.post(f"{BASE}/api/travel/requests", headers=h(trav), json={
    "destination": "Manali", "roles": ["cook"], "days": 2, "people": 3,
    "starts_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}).json()
q = requests.post(f"{BASE}/api/travel/requests/{sr['id']}/quotes", headers=h(prov),
                  json={"amount": 5000, "note": "Veg + non-veg"}).json()
print("quote (5000 + markup):", q)
mine = requests.get(f"{BASE}/api/travel/requests?mine=true", headers=h(trav)).json()["items"][0]
acc = requests.post(f"{BASE}/api/travel/quotes/{mine['quotes'][0]['id']}/accept", headers=h(trav)).json()
print("accepted:", acc["amount"])

# 5. ledger + invoice
led = requests.get(f"{BASE}/api/admin/ledger", headers=h(admin), params={"direction": "in", "kind": "travel"}).json()
print("ledger travel rows:", [(r["reference"], r["gross"], r["commission"]) for r in led["items"][:2]])
inv = requests.get(f"{BASE}/api/orders/{o2['id']}/invoice", headers=h(trav)).json()
print("invoice:", inv["invoice_no"], inv["receipt_no"], inv["total"], inv["buyer"]["name"])
print("other user invoice 403:", requests.get(f"{BASE}/api/orders/{o2['id']}/invoice", headers=h(prov)).status_code)

# cleanup
DB.trips.delete_many({"host_id": {"$in": [tid, pid]}})
DB.trip_joins.delete_many({})
DB.travel_bookings.delete_many({"traveller_id": tid})
DB.service_requests.delete_many({"traveller_id": tid})
DB.service_quotes.delete_many({"provider_id": pid})
DB.payouts.delete_many({"kind": "travel"})
DB.orders.delete_many({"kind": {"$in": ["travel", "provider_fee"]}})
DB.users.update_one({"_id": ObjectId(pid)}, {"$unset": {"provider": ""}})
print("cleaned")
