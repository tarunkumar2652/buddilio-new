"""Iteration 54 cleanup/verification: final state check."""
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = requests.post(f"{BASE}/auth/login", json={"email": "admin@buddilio.com",
                                                "password": "Admin@123"}, timeout=30).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}

print("site-content hangouts_enabled:", requests.get(f"{BASE}/site-content", timeout=30).json().get("hangouts_enabled"))
print("settings hide_hangouts:", requests.get(f"{BASE}/admin/settings", headers=h, timeout=30).json().get("hide_hangouts"))
ads = requests.get(f"{BASE}/admin/ads", headers=h, timeout=30).json()
print("head_code:", repr(ads["config"].get("head_code")))
leftovers = [a for a in ads["items"] if a["name"].startswith("TEST_")]
for a in leftovers:
    r = requests.delete(f"{BASE}/admin/ads/{a['id']}", headers=h, timeout=30)
    print("deleted", a["name"], r.status_code)
print("leftover TEST ads now:", [a["name"] for a in requests.get(f"{BASE}/admin/ads", headers=h, timeout=30).json()["items"] if a["name"].startswith("TEST_")])
print("blog page:", requests.get(f"{BASE}/blog?limit=1", timeout=30).status_code)
print("sitemap:", requests.get(f"{BASE}/sitemap.xml", timeout=60).status_code)
threads = requests.get(f"{BASE}/admin/support/threads", headers=h, timeout=30)
print("support threads status:", threads.status_code)
if threads.status_code == 200:
    items = threads.json().get("items", [])
    print("TEST_i54 advertise thread present:", any("TEST_i54" in (t.get("subject", "") + t.get("name", "")) for t in items))
