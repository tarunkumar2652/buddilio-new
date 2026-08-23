"""Cleanup after iteration-51 UI tests: TEST_ blog post, TEST support threads, SEO test values."""
import requests

BASE = "https://lifestyle-connect-17.preview.emergentagent.com/api"
tok = requests.post(f"{BASE}/auth/login",
                    json={"email": "admin@buddilio.com", "password": "Admin@123"},
                    timeout=30).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

posts = requests.get(f"{BASE}/admin/blog", headers=H, timeout=30).json()
items = posts.get("items", posts if isinstance(posts, list) else [])
for p in items:
    if str(p.get("title", "")).startswith("TEST_"):
        r = requests.delete(f"{BASE}/admin/blog/{p['id']}", headers=H, timeout=30)
        print("deleted post", p["title"], r.status_code)

# restore SEO settings to a safe state (no live domain -> IndexNow submission stays disabled)
r = requests.put(f"{BASE}/admin/seo", headers=H,
                 json={"gsc_verification": "", "site_url": ""}, timeout=30)
print("seo reset:", r.status_code, r.json().get("message"))
print("seo now:", requests.get(f"{BASE}/seo/public", timeout=30).json())
