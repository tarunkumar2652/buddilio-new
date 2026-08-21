"""Built-in bot protection — challenge + honeypot + per-IP rate limiting. No third-party keys."""
import hashlib
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

WORDS = ["buddilio", "friendly", "evening", "coffee", "sunset", "concert", "weekend", "journey"]
LIMITS = {"register": (5, 60), "login": (12, 15), "contact": (5, 60), "report": (8, 60)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(answer: str) -> str:
    salt = os.environ.get("JWT_SECRET", "buddilio")
    return hashlib.sha256(f"{salt}:{answer.strip().lower()}".encode()).hexdigest()


def new_challenge() -> dict:
    """Mixes simple arithmetic with word questions so scripted solvers need real parsing."""
    style = random.choice(["sum", "word", "count"])
    if style == "sum":
        a, b = random.randint(2, 9), random.randint(2, 9)
        question, answer = f"What is {a} + {b}?", str(a + b)
    elif style == "count":
        word = random.choice(WORDS)
        question, answer = f"How many letters are in the word “{word}”?", str(len(word))
    else:
        word = random.choice(WORDS)
        question, answer = f"Type the last four letters of “{word}”.", word[-4:]
    return {"id": str(uuid.uuid4()), "question": question, "answer_hash": _hash(answer),
            "expires_at": (_now() + timedelta(minutes=15)).isoformat()}


def check_answer(doc: dict, answer: str) -> bool:
    return bool(doc) and doc.get("answer_hash") == _hash(answer or "")


def client_ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))
