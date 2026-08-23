"""Encrypted credential store so the Super Admin can rotate keys without touching the server.

Values are AES-GCM encrypted at rest in Mongo and decrypted into the process environment on boot and
on save, so every existing module (paypal, emailer, push, crons) keeps reading os.environ as before.
Secrets are write-only from the UI: nothing here ever returns a stored value to the browser.
"""
import base64
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"buddilio-credential:v1:"
COLL = "platform_credentials"

# What the Super Admin can rotate in-app, grouped for the UI.
MANAGED = [
    ("Payments", "PAYPAL_ENV", "PayPal mode", "Type live or sandbox", False),
    ("Payments", "PAYPAL_CLIENT_ID", "PayPal client ID (live)", "From your PayPal app", True),
    ("Payments", "PAYPAL_CLIENT_SECRET", "PayPal secret (live)", "From your PayPal app", True),
    ("Payments", "PAYPAL_SANDBOX_CLIENT_ID", "PayPal client ID (sandbox)", "For test mode", True),
    ("Payments", "PAYPAL_SANDBOX_CLIENT_SECRET", "PayPal secret (sandbox)", "For test mode", True),
    ("Payments", "PAYPAL_WEBHOOK_ID", "PayPal webhook ID", "Usually set by Connect webhook", True),
    ("Payments", "PAYPAL_CURRENCY", "Charge currency", "USD", False),
    ("Payments", "STRIPE_API_KEY", "Stripe secret key", "Only if you switch on Stripe", True),
    ("Payments", "RAZORPAY_KEY_ID", "Razorpay key ID", "Only if you switch on Razorpay", True),
    ("Payments", "RAZORPAY_KEY_SECRET", "Razorpay key secret", "Only if you switch on Razorpay", True),
    ("Email & AI", "RESEND_API_KEY", "Resend API key", "Transactional email", True),
    ("Email & AI", "EMERGENT_LLM_KEY", "AI key", "Powers Buddy AI", True),
    ("Notifications", "VAPID_PUBLIC_KEY", "Push public key", "Browser notifications", True),
    ("Notifications", "VAPID_PRIVATE_KEY", "Push private key", "Browser notifications", True),
    ("Notifications", "VAPID_SUBJECT", "Push contact", "mailto:you@yourdomain", False),
    ("Automation", "WEBHOOK_CRON_SECRET", "Scheduled jobs secret", "Protects the cron endpoints", True),
    ("Security", "JWT_SECRET", "Login token secret", "Changing it logs everyone out", True),
]
NAMES = {m[1] for m in MANAGED}

# What the server booted with, so "revert to server file" can put it back.
BOOT_ENV = {n: os.environ.get(n, "") for n in NAMES}


def _key() -> bytes:
    raw = os.environ.get("SECRETS_KEY_B64", "")
    if not raw:
        raise RuntimeError("SECRETS_KEY_B64 is not configured")
    k = base64.urlsafe_b64decode(raw.encode())
    if len(k) not in (16, 24, 32):
        raise RuntimeError("SECRETS_KEY_B64 must decode to 16, 24 or 32 bytes")
    return k


def encrypt(name: str, value: str) -> dict:
    nonce = os.urandom(12)
    blob = AESGCM(_key()).encrypt(nonce, value.encode(), AAD + str(name).encode())
    return {"ciphertext": base64.b64encode(blob).decode(),
            "nonce": base64.b64encode(nonce).decode(), "key_version": 1}


def decrypt(doc: dict) -> str:
    return AESGCM(_key()).decrypt(base64.b64decode(doc["nonce"]),
                                  base64.b64decode(doc["ciphertext"]),
                                  AAD + str(doc["_id"]).encode()).decode()


def mask(value: str) -> str:
    """Enough to recognise a key, never enough to use it."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:3]}{'•' * 8}{value[-3:]}"


async def load_into_env(db) -> int:
    """Apply stored overrides to this process. Called once at startup."""
    loaded = 0
    async for doc in db[COLL].find({}):
        if doc["_id"] not in NAMES:
            continue
        try:
            os.environ[doc["_id"]] = decrypt(doc)
            loaded += 1
        except Exception:            # a bad/rotated key must not stop the app booting
            continue
    return loaded


async def set_secret(db, name: str, value: str) -> None:
    if name not in NAMES:
        raise KeyError(name)
    await db[COLL].update_one({"_id": name},
                              {"$set": {**encrypt(name, value),
                                        "updated_at": datetime.now(timezone.utc).isoformat()}},
                              upsert=True)
    os.environ[name] = value


async def clear_secret(db, name: str) -> None:
    if name not in NAMES:
        raise KeyError(name)
    await db[COLL].delete_one({"_id": name})
    if BOOT_ENV.get(name):
        os.environ[name] = BOOT_ENV[name]
    else:
        os.environ.pop(name, None)


async def status(db) -> list[dict]:
    """Metadata only — group, label, whether it is set, where it came from, when it changed."""
    stored = {d["_id"]: d async for d in db[COLL].find({}, {"ciphertext": 0, "nonce": 0})}
    out = []
    for group, name, label, hint, sensitive in MANAGED:
        live = os.environ.get(name, "")
        out.append({"group": group, "name": name, "label": label, "hint": hint,
                    "sensitive": sensitive, "configured": bool(live),
                    "source": "dashboard" if name in stored else ("server file" if live else "not set"),
                    "preview": mask(live) if sensitive else live,
                    "updated_at": stored.get(name, {}).get("updated_at", "")})
    return out
