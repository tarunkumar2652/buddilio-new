"""Iteration 52 cleanup: TEST_ subscribers, TEST support threads/canned replies, newsletter_sent_at."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path("/app/backend/.env"))
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

adm = db.users.find_one({"email": "admin@buddilio.com"}, {"full_name": 1})
print("admin full_name:", adm.get("full_name") if adm else None)

print("subs deleted:", db.newsletter_subs.delete_many(
    {"email": {"$regex": "^test_|^TEST_", "$options": "i"}}).deleted_count)
print("threads deleted:", db.support_threads.delete_many(
    {"$or": [{"name": {"$regex": "^TEST", "$options": "i"}},
             {"subject": {"$regex": "^TEST", "$options": "i"}},
             {"email": {"$regex": "^test_", "$options": "i"}}]}).deleted_count)
print("canned deleted:", db.canned_replies.delete_many(
    {"title": {"$regex": "^TEST", "$options": "i"}}).deleted_count)
print("drafts deleted:", db.blog_posts.delete_many(
    {"title": {"$regex": "^TEST", "$options": "i"}}).deleted_count)
print("posts unsent:", db.blog_posts.update_many(
    {"newsletter_sent_at": {"$nin": ["", None]}},
    {"$unset": {"newsletter_sent_at": "", "newsletter_sent_count": ""}}).modified_count)
print("notifications deleted:", db.notifications.delete_many(
    {"type": "support", "title": {"$regex": "^TEST", "$options": "i"}}).deleted_count)
print("remaining active subs:", db.newsletter_subs.count_documents({"status": "active"}))
print("remaining canned:", [r["title"] for r in db.canned_replies.find({}, {"title": 1})])
