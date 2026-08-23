"""SEO operations — IndexNow submissions so new/updated pages get crawled without waiting."""
import logging
import secrets
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# api.indexnow.org shares the submission with every participating engine (Bing, Yandex, Seznam, Naver).
ENDPOINTS = [
    ("IndexNow (Bing, Yandex, Seznam, Naver)", "https://api.indexnow.org/indexnow"),
    ("Bing direct", "https://www.bing.com/indexnow"),
]
MAX_URLS = 9000


def new_key() -> str:
    return secrets.token_hex(16)


def host_of(site_url: str) -> str:
    return urlparse(site_url if "://" in site_url else f"https://{site_url}").netloc


async def submit(site_url: str, key: str, urls: list[str]) -> list[dict]:
    """Posts the URL list to each IndexNow endpoint and reports each response verbatim."""
    host = host_of(site_url)
    payload = {"host": host, "key": key, "keyLocation": f"{site_url.rstrip('/')}/{key}.txt",
               "urlList": urls[:MAX_URLS]}
    out = []
    async with httpx.AsyncClient(timeout=30) as client:
        for label, endpoint in ENDPOINTS:
            try:
                r = await client.post(endpoint, json=payload,
                                      headers={"Content-Type": "application/json; charset=utf-8"})
                out.append({"engine": label, "status": r.status_code, "ok": r.status_code in (200, 202),
                            "detail": (r.text or "")[:200]})
            except Exception as e:
                logger.error(f"IndexNow submit to {endpoint} failed: {e}")
                out.append({"engine": label, "status": 0, "ok": False, "detail": str(e)[:200]})
    return out
