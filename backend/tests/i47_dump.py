"""Dump the USD totals the iteration_47 review asks about."""
import json
import os

import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login",
                    json={"email": "admin@buddilio.com", "password": "Admin@123"}, timeout=60).json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}

led = requests.get(f"{API}/admin/ledger?limit=1", headers=h, timeout=90).json()
print("LEDGER currency:", led.get("currency"), "totals:", json.dumps(led["totals"]))
st = requests.get(f"{API}/admin/stats?days=3650", headers=h, timeout=90).json()
print("STATS currency:", st.get("currency"),
      {k: st[k] for k in ("gross_sales", "membership_revenue", "event_revenue", "pass_revenue")})
po = requests.get(f"{API}/admin/payouts", headers=h, timeout=90).json()
print("PAYOUTS currency:", po.get("currency"), "totals:", po["totals"],
      "row currencies:", sorted({p.get("currency") for p in po["items"]}))
