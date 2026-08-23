"""Prerender output checks — build/blog/index.html, build/blog/<slug>/index.html, sitemap.xml."""
import re
from pathlib import Path

import pytest

BUILD = Path("/app/frontend/build")


@pytest.fixture(scope="module")
def index_html():
    p = BUILD / "blog" / "index.html"
    if not p.exists():
        pytest.fail("build/blog/index.html missing — prerender did not run")
    return p.read_text(encoding="utf-8")


def article_dirs():
    return [d for d in (BUILD / "blog").iterdir() if d.is_dir() and (d / "index.html").exists()]


def test_sitemap_file_exists():
    p = BUILD / "sitemap.xml"
    assert p.exists(), "build/sitemap.xml missing"
    assert "<urlset" in p.read_text(encoding="utf-8")


def test_blog_index_html(index_html):
    assert "<title>The Buddilio Journal" in index_html
    assert re.search(r'<meta name="description" content="[^"]{40,}"', index_html)
    assert re.search(r'<link rel="canonical" href="https?://[^"]+/blog"', index_html)
    assert 'application/ld+json' in index_html
    body = index_html.split('<div id="root">')[1].split("</div>")[0]
    assert "<article>" in body and "<h1>" in body
    # category links use '+' encoding
    cats = re.findall(r'href="[^"]*/blog\?category=([^"]+)"', index_html)
    assert cats, "no category links prerendered"
    assert all("%20" not in c and " " not in c for c in cats), cats


def test_article_pages_prerendered(index_html):
    dirs = article_dirs()
    assert len(dirs) >= 1, "no article directories prerendered"
    for d in dirs:
        html = (d / "index.html").read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert title and "Buddilio — " not in title, f"{d.name}: generic title {title!r}"
        assert re.search(r'<meta name="description" content="[^"]{20,}"', html), d.name
        assert f'<link rel="canonical" href' in html and f"/blog/{d.name}" in html, d.name
        assert '<script type="application/ld+json">' in html, d.name
        root = html.split('<div id="root">')[1]
        assert "<h1>" in root and "<article>" in root, d.name
        assert len(re.sub(r"<[^>]+>", " ", root.split("</main>")[0])) > 600, f"{d.name}: thin body"
