"""Human support conversations — visitors escalate from Buddy AI, staff reply from the admin inbox."""
import secrets
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, ConfigDict, Field

STATUSES = ("open", "pending", "closed")
MAX_MESSAGES = 200


class StartIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=2, max_length=2000)
    name: str = ""
    email: str = ""
    subject: str = ""
    page: str = ""
    ai_transcript: List[str] = []


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=1, max_length=2000)
    token: str = ""


def new_token() -> str:
    return secrets.token_urlsafe(24)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def message(role: str, body: str, author: str = "") -> dict:
    """role: 'visitor' | 'staff' | 'note'"""
    return {"role": role, "author": author, "body": body.strip()[:2000], "created_at": now_iso()}


def public_thread(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]), "status": doc.get("status", "open"), "subject": doc.get("subject", ""),
        "updated_at": doc.get("updated_at", ""),
        "messages": [{"role": m["role"], "author": m.get("author", ""), "body": m["body"],
                      "created_at": m["created_at"]}
                     for m in doc.get("messages", []) if m["role"] != "note"],
    }


def staff_card(doc: dict) -> dict:
    msgs = doc.get("messages", [])
    last = msgs[-1] if msgs else {}
    return {
        "id": str(doc["_id"]), "status": doc.get("status", "open"),
        "subject": doc.get("subject", ""), "name": doc.get("name", "") or "Visitor",
        "email": doc.get("email", ""), "user_id": doc.get("user_id", ""),
        "is_member": bool(doc.get("user_id")), "page": doc.get("page", ""),
        "messages_count": len(msgs), "unread": bool(doc.get("unread_for_staff")),
        "last_message": (last.get("body", "") or "")[:140],
        "last_role": last.get("role", ""), "updated_at": doc.get("updated_at", ""),
        "created_at": doc.get("created_at", ""),
    }
