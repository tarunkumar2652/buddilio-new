"""Buddilio Journal — editorial posts that give search engines something worth crawling."""
import re
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ["Nightlife", "Dining", "Travel", "City Guides", "Safety", "Community", "Events"]
READ_WPM = 220


def slugify(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return out[:80] or "post"


def plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def read_minutes(html: str) -> int:
    words = len(plain_text(html).split())
    return max(1, round(words / READ_WPM))


def excerpt_of(post: dict) -> str:
    if post.get("excerpt"):
        return post["excerpt"]
    return plain_text(post.get("body", ""))[:180].rstrip() + "…"


class PostIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=3, max_length=180)
    slug: str = ""
    category: str = "Community"
    excerpt: str = ""
    body: str = ""                       # rich HTML from the editor
    cover_image: str = ""
    cover_credit: str = ""
    author_name: str = ""
    author_role: str = ""
    tags: List[str] = []
    seo_title: str = ""
    seo_description: str = ""
    featured: bool = False
    status: Literal["published", "draft"] = "draft"
    published_at: str = ""
    related_city: str = ""
    cta_label: str = ""
    cta_url: str = ""


def to_doc(payload: PostIn, existing: Optional[dict] = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    doc = payload.model_dump()
    doc["slug"] = slugify(payload.slug or payload.title)
    doc["category"] = payload.category if payload.category in CATEGORIES else "Community"
    doc["excerpt"] = payload.excerpt.strip() or excerpt_of(doc)
    doc["read_minutes"] = read_minutes(payload.body)
    doc["tags"] = [t.strip() for t in payload.tags if t.strip()][:8]
    doc["updated_at"] = now
    if payload.status == "published":
        doc["published_at"] = payload.published_at or (existing or {}).get("published_at") or now
    if not existing:
        doc["created_at"] = now
        doc["views"] = 0
    return doc


def card(doc: dict) -> dict:
    """What listings need — never the full body."""
    return {"id": doc["id"], "slug": doc["slug"], "title": doc["title"], "category": doc["category"],
            "excerpt": doc.get("excerpt", ""), "cover_image": doc.get("cover_image", ""),
            "author_name": doc.get("author_name", "Buddilio Editorial"),
            "read_minutes": doc.get("read_minutes", 3), "featured": bool(doc.get("featured")),
            "published_at": doc.get("published_at", ""), "tags": doc.get("tags", []),
            "views": int(doc.get("views") or 0)}


def article_jsonld(doc: dict, site: str) -> dict:
    return {"@context": "https://schema.org", "@type": "BlogPosting",
            "headline": doc["title"], "description": doc.get("excerpt", ""),
            "image": doc.get("cover_image", ""),
            "datePublished": doc.get("published_at", ""), "dateModified": doc.get("updated_at", ""),
            "author": {"@type": "Person", "name": doc.get("author_name") or "Buddilio Editorial"},
            "publisher": {"@type": "Organization", "name": "Buddilio",
                          "url": site},
            "mainEntityOfPage": f"{site}/blog/{doc['slug']}",
            "articleSection": doc.get("category", ""),
            "keywords": ", ".join(doc.get("tags", []))}
