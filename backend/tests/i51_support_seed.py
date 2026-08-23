"""Helper: create a guest support thread + staff reply so the UI test can attach to it."""
import json
import requests

BASE = "https://lifestyle-connect-17.preview.emergentagent.com/api"
r = requests.post(f"{BASE}/support/threads", json={
    "message": "TEST_ poll check guest message", "name": "TEST Poll Guest",
    "email": "test.poll51@example.com", "page": "/"}, timeout=30)
print("start:", r.status_code, r.text[:200])
if r.status_code == 200:
    d = r.json()
    tok = requests.post(f"{BASE}/auth/login",
                        json={"email": "admin@buddilio.com", "password": "Admin@123"},
                        timeout=30).json()["access_token"]
    rep = requests.post(f"{BASE}/admin/support/{d['thread']['id']}/reply",
                        json={"message": "TEST_ poll staff answer"},
                        headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    print("reply:", rep.status_code)
    print(json.dumps({"id": d["thread"]["id"], "token": d["token"]}))
