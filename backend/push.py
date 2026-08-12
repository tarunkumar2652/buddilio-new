"""Standards-based Web Push (VAPID) delivery."""
import asyncio
import json
import logging
import os

from pywebpush import webpush, WebPushException

logger = logging.getLogger("buddilio.push")

PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:hello@buddilio.com")
ICON = "/icons/icon-192.png"


def push_enabled() -> bool:
    return bool(PUBLIC_KEY and PRIVATE_KEY)


def vapid_public_key() -> str:
    return PUBLIC_KEY


def _send(subscription: dict, payload: dict, ttl: int):
    webpush(subscription_info=subscription, data=json.dumps(payload),
            vapid_private_key=PRIVATE_KEY, vapid_claims={"sub": SUBJECT}, ttl=ttl)


async def push_to(db, user_id: str, payload: dict, ttl: int = 86400) -> int:
    """Fan a notification out to every device the member has registered."""
    if not push_enabled():
        return 0
    docs = await db.push_subscriptions.find({"user_id": user_id}).to_list(20)
    body = {"icon": ICON, "badge": ICON, **payload}
    sent = 0
    for d in docs:
        try:
            await asyncio.to_thread(_send, {"endpoint": d["endpoint"], "keys": d["keys"]}, body, ttl)
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                await db.push_subscriptions.delete_one({"_id": d["_id"]})
                logger.info("removed expired push subscription")
            else:
                logger.warning(f"push failed ({status}): {e}")
        except Exception as e:
            logger.warning(f"push error: {e}")
    return sent
