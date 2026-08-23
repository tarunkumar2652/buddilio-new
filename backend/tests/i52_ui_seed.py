"""Seed for the iteration 52 UI pass: one newsletter token + one guest support thread."""
import json
import os
import uuid
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))
API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

email = f"TEST_ui_{uuid.uuid4().hex[:6]}@example.com"
requests.post(f"{API}/newsletter/subscribe", json={"email": email}, timeout=40).raise_for_status()
token = db.newsletter_subs.find_one({"email": email.lower()})["token"]

name = "TEST Priya Sharma"
r = requests.post(f"{API}/support/threads", json={
    "name": name, "email": f"TEST_ui_guest_{uuid.uuid4().hex[:5]}@example.com",
    "message": "TEST I need a human about my booking", "subject": "TEST UI thread",
    "page": "/", "ai_transcript": []}, timeout=60)
thread = r.json().get("thread", {}) if r.status_code == 200 else {}
print(json.dumps({"email": email, "token": token, "thread": thread.get("id"),
                  "thread_status": r.status_code, "name": name}))
