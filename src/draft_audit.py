"""
draft_audit.py — WordPress の直近下書きを source 別 / 記事型別に棚卸しする

使用例:
    python3 src/draft_audit.py --limit 15
    python3 src/draft_audit.py --limit 30 --json
"""

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from rss_fetcher import _detect_article_subtype
from wp_client import WPClient

SOURCE_CONFIG_FILE = ROOT / "config" / "rss_sources.json"
PROJECT_CATEGORIES = {
    "試合速報",
    "選手情報",
    "首脳陣",
    "ドラフト・育成",
    "OB・解説者",
    "補強・移籍",
    "球団情報",
    "コラム",
}
REFERENCE_SECTION_RE = re.compile(r"📰\s*参照元:\s*(.*?)</p>", re.S)
ANCHOR_RE = re.compile(r'<a [^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
BADGE_RE = re.compile(r"📰\s*([^<]+)</span>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
PARAGRAPH_RE = re.compile(r"<p\b([^>]*)>(.*?)</p>", re.I | re.S)
REF_HEADING_RE = re.compile(
    r"<h[1-6][^>]*>\s*【引用元】\s*</h[1-6]>(?:\s|<!--.*?-->)*(<p\b[^>]*>.*?</p>)",
    re.I | re.S,
)
MARKDOWN_LINK_RE = re.compile(r"\[\[\d+\]\]\((https?://[^)\s]+)\)")
SOURCE_LABEL_RE = re.compile(r"(引用元|出典|参考|参照元|source)\s*[:：]", re.I)
FOOTER_STYLE_RE = re.compile(r"(font-size\s*:\s*(?:0\.8em|0\.9em|12px|13px))|(color\s*:\s*#(?:666|999))", re.I)
SOURCE_HOST_PATTERNS = (
    "npb.jp",
    "baseball.yahoo.co.jp",
    "sports.yahoo.co.jp",
    "news.yahoo.co.jp",
    "nikkansports.com",
    "hochi.news",
    "sponichi.co.jp",
    "sanspo.com",
    "baseballking.jp",
    "full-count.jp",
    "giants.jp",
    "tokyo-sports.co.jp",
    "daily.co.jp",
    "chunichi.co.jp",
    "number.bunshun.jp",
)
EXCLUDED_SOURCE_HOST_PATTERNS = (
    "twitter.com",
    "x.com",
    "t.co",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
)


def _strip_html(value: str) -> str:
    text = TAG_RE.sub(" ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[\s　/／・|]+", "", html.unescape(value or "")).lower()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = _normalize_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _is_supported_source_url(url: str, strict: bool = True) -> bool:
    try:
        parsed = urlparse(html.unescape(url))
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if any(pattern in host for pattern in EXCLUDED_SOURCE_HOST_PATTERNS):
        return False
    if not strict:
        return True
    return any(pattern in host for pattern in SOURCE_HOST_PATTERNS)


def _extract_anchor_items(fragment: str, strict: bool = True) -> list[dict]:
    items = []
    for url, label in ANCHOR_RE.findall(fragment):
        clean_url = html.unescape(url)
        if not _is_supported_source_url(clean_url, strict=strict):
            continue
        name = _strip_html(label) or clean_url
        items.append({"name": name, "url": clean_url})
    return items


def _append_unique_source_items(target: list[dict], items: list[dict]) -> None:
    seen = {(item.get("url") or "", _normalize_key(item.get("name") or "")) for item in target}
    for item in items:
        key = (item.get("url") or "", _normalize_key(item.get("name") or ""))
        if key in seen:
            continue
        seen.add(key)
        target.append(item)


def load_source_catalog() -> dict[str, dict]:
    if not SOURCE_CONFIG_FILE.exists():
        return {}
    with open(SOURCE_CONFIG_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    catalog = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        catalog[_normalize_key(name)] = {
            "name": name,
            "type": row.get("type", "unknown"),
        }
    return catalog


def extract_source_links(content_html: str) -> list[dict]:
    content_html = content_html or ""
    found_items: list[dict] = []

    match = REFERENCE_SECTION_RE.search(content_html)
    if match:
        _append_unique_source_items(found_items, _extract_anchor_items(match.group(1), strict=False))

    for match in REF_HEADING_RE.finditer(content_html):
        _append_unique_source_items(found_items, _extract_anchor_items(match.group(1), strict=False))

    for attrs, body in PARAGRAPH_RE.findall(content_html):
        paragraph_html = f"<p{attrs}>{body}</p>"
        plain = _strip_html(body)
        if SOURCE_LABEL_RE.search(plain):
            _append_unique_source_items(found_items, _extract_anchor_items(paragraph_html, strict=False))
            continue
        style_attrs = attrs or ""
        if FOOTER_STYLE_RE.search(style_attrs):
            _append_unique_source_items(found_items, _extract_anchor_items(paragraph_html))

    for url in MARKDOWN_LINK_RE.findall(content_html):
        clean_url = html.unescape(url)
        if _is_supported_source_url(clean_url):
            _append_unique_source_items(
                found_items,
                [{"name": clean_url, "url": clean_url}],
            )

    if found_items:
        return found_items

    badge_match = BADGE_RE.search(content_html)
    if not badge_match:
        return []

    names = []
    for raw in re.split(r"\s*/\s*", _strip_html(badge_match.group(1))):
        clean = raw.strip()
        if clean:
            names.append(clean)
    return [{"name": name, "url": ""} for name in _dedupe_preserve_order(names)]


def _resolve_source_info(source_links: list[dict], catalog: dict[str, dict]) -> tuple[list[dict], str]:
    resolved = []
    type_set = set()
    for item in source_links:
        original_name = (item.get("name") or "").strip()
        match = catalog.get(_normalize_key(original_name), {})
        source_type = match.get("type", "unknown")
        canonical_name = match.get("name", original_name or "source不明")
        type_set.add(source_type)
        resolved.append(
            {
                "name": canonical_name,
                "type": source_type,
                "url": item.get("url", ""),
            }
        )

    if not resolved:
        return [], "unknown"
    if len(type_set) == 1:
        return resolved, next(iter(type_set))
    return resolved, "mixed"


def _primary_category(category_ids: list[int], category_map: dict[int, str]) -> tuple[str, list[str]]:
    category_names = [category_map.get(cid, str(cid)) for cid in category_ids]
    for name in category_names:
        if name in PROJECT_CATEGORIES:
            return name, category_names
    return (category_names[0] if category_names else "未分類"), category_names


def audit_post(post: dict, category_map: dict[int, str], source_catalog: dict[str, dict], base_url: str) -> dict:
    title_data = post.get("title") or {}
    content_data = post.get("content") or {}
    title = title_data.get("raw") or title_data.get("rendered") or ""
    content_html = content_data.get("raw") or content_data.get("rendered") or ""
    primary_category, category_names = _primary_category(post.get("categories") or [], category_map)
    source_links = extract_source_links(content_html)
    resolved_sources, source_bucket = _resolve_source_info(source_links, source_catalog)
    subtype = _detect_article_subtype(title, _strip_html(content_html), primary_category, primary_category == "試合速報")
    post_id = post.get("id")
    return {
        "id": post_id,
        "title": title,
        "status": post.get("status", ""),
        "modified": post.get("modified") or post.get("date") or "",
        "primary_category": primary_category,
        "categories": category_names,
        "article_subtype": subtype,
        "source_bucket": source_bucket,
        "sources": resolved_sources,
        "source_names": [item["name"] for item in resolved_sources],
        "edit_url": f"{base_url.rstrip('/')}/wp-admin/post.php?post={post_id}&action=edit" if post_id else "",
    }


def build_report_rows(audited_posts: list[dict]) -> list[str]:
    rows = []
    rows.append(f"total_drafts: {len(audited_posts)}")
    rows.append("")

    bucket_counter = Counter(post["source_bucket"] for post in audited_posts)
    rows.append("[source_bucket]")
    for name, count in bucket_counter.most_common():
        rows.append(f"{name}: {count}")
    rows.append("")

    type_counter = Counter(f"{post['primary_category']} / {post['article_subtype']}" for post in audited_posts)
    rows.append("[category_subtype]")
    for name, count in type_counter.most_common():
        rows.append(f"{name}: {count}")
    rows.append("")

    source_counter = Counter()
    for post in audited_posts:
        if not post["sources"]:
            source_counter["unknown | source不明"] += 1
            continue
        for source in post["sources"]:
            source_counter[f"{source['type']} | {source['name']}"] += 1
    rows.append("[source]")
    for name, count in source_counter.most_common():
        rows.append(f"{name}: {count}")
    rows.append("")

    rows.append("[posts]")
    for post in audited_posts:
        sources = ", ".join(post["source_names"]) if post["source_names"] else "source不明"
        rows.append(
            f"{post['id']} | {post['modified']} | {post['primary_category']}/{post['article_subtype']} "
            f"| {post['source_bucket']} | {sources} | {post['title']}"
        )
        if post["edit_url"]:
            rows.append(f"  {post['edit_url']}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="WordPress の直近下書きを棚卸しする")
    parser.add_argument("--limit", type=int, default=15, help="取得件数")
    parser.add_argument("--page", type=int, default=1, help="ページ番号")
    parser.add_argument("--status", default="draft", help="取得する投稿ステータス")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    wp = WPClient()
    categories = wp.get_categories()
    category_map = {int(row["id"]): row["name"] for row in categories}
    source_catalog = load_source_catalog()
    posts = wp.list_posts(
        status=args.status,
        per_page=args.limit,
        page=args.page,
        orderby="modified",
        order="desc",
        context="edit",
        fields=["id", "date", "modified", "status", "title", "content", "categories"],
    )
    audited = [audit_post(post, category_map, source_catalog, wp.base_url) for post in posts]

    if args.json:
        print(json.dumps(audited, ensure_ascii=False, indent=2))
        return

    for line in build_report_rows(audited):
        print(line)


if __name__ == "__main__":
    main()
