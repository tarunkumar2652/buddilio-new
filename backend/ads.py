"""House ads — your own promo banners with an ad-network fallback for the same slots."""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLACEMENTS = [
    ("home", "Home page (below the fold)"),
    ("events", "Events list (between rows)"),
    ("journal", "Journal index"),
    ("article", "Inside an article"),
    ("membership", "Membership page"),
    ("passes", "Passes page"),
    ("footer", "Slim strip above the footer"),
]
PLACEMENT_KEYS = [k for k, _ in PLACEMENTS]


class AdIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=80)
    headline: str = ""
    body: str = ""
    image: str = ""
    cta_label: str = "Find out more"
    url: str = ""
    advertiser: str = ""
    placements: List[str] = Field(default_factory=list, min_length=1)
    cities: List[str] = []
    priority: int = 5
    status: Literal["active", "paused"] = "active"
    starts_at: str = ""
    ends_at: str = ""

    @field_validator("placements")
    @classmethod
    def known_placements(cls, v: List[str]) -> List[str]:
        picked = [p for p in v if p in PLACEMENT_KEYS]
        if not picked:
            raise ValueError("Pick at least one place for the ad to appear.")
        return picked


class AdConfigIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    network_enabled: bool = False
    network_client: str = ""            # e.g. AdSense publisher id
    network_slots: dict = {}            # placement -> ad unit id
    code_slots: dict = {}               # placement -> raw ad snippet, pasted as-is
    head_code: str = ""                 # site-wide snippet (Auto ads / verification)
    hide_for_plans: List[str] = []      # plan names that never see ads


def to_doc(payload: AdIn) -> dict:
    doc = payload.model_dump()
    doc["placements"] = [p for p in payload.placements if p in PLACEMENT_KEYS]
    if not doc["placements"]:
        raise ValueError("Pick at least one place for the ad to appear.")
    doc["priority"] = max(1, min(payload.priority, 10))
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    return doc


def public_card(doc: dict) -> dict:
    return {"id": doc["id"], "headline": doc.get("headline", ""), "body": doc.get("body", ""),
            "image": doc.get("image", ""), "cta_label": doc.get("cta_label", "Find out more"),
            "url": doc.get("url", ""), "advertiser": doc.get("advertiser", "")}


def admin_card(doc: dict) -> dict:
    return doc | {"views": int(doc.get("views") or 0), "clicks": int(doc.get("clicks") or 0),
                  "ctr": round((int(doc.get("clicks") or 0) / int(doc.get("views") or 0)) * 100, 1)
                  if doc.get("views") else 0.0}


def live_query(placement: str, city: str, now_iso: str) -> dict:
    return {"status": "active", "placements": placement,
            "$and": [{"$or": [{"starts_at": ""}, {"starts_at": {"$lte": now_iso}}]},
                     {"$or": [{"ends_at": ""}, {"ends_at": {"$gte": now_iso}}]},
                     {"$or": [{"cities": []}, {"cities": city}]}]}
