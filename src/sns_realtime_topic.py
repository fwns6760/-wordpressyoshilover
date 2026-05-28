"""sns_realtime_topic — main module: RSSHub fetch → 分類 → render → WP upsert (page split).

ticket 445: SNS リアルタイム話題 daily aggregation (page split: 一軍 / ファーム).

URL モデル: **permanent 2 URL** (Yahoo リアルタイム検索式)
- `giants-sns-realtime-1gun` — 一軍 投稿 上位 15 件
- `giants-sns-realtime-farm` — 二軍 上位 5 + 三軍 上位 5 = 最大 10 件

source = 巨人専門 / 球団公式 X 4 account を RSSHub 経由で取得。
1 日 4 fire (10/13/17/21 JST) を内部 time gate で発火。

enhancement (a) + (b):
- (a) 急上昇 marker: 昨日の言及回数 (GCS、 page 別 nested dict) と diff
       初日 (前日 counts なし) は badge 抑制 (全員 ↑+N 出ないようにする)
- (b) tag chip → WP tag page link
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote as urlquote

import feedparser
import requests

from sns_realtime_topic_classifier import (
    classify_team_level,
    count_mentions,
    load_roster_aliases,
)
from sns_realtime_topic_state import (
    PageCounts,
    load_previous_counts,
    save_counts,
)
from sns_realtime_topic_template import render_full_html, render_trend_chips
from wp_draft_creator import build_oembed_block

_logger = logging.getLogger(__name__)

RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
SOURCE_HANDLES = ["yomiuri_giants", "TokyoGiants", "hochi_giants", "Sanspo_Giants"]
JST = timezone(timedelta(hours=9))
FIRE_SLOTS = {10, 13, 17, 21}
SLOT_MINUTE_WINDOW = 5
RSSHUB_TIMEOUT_SECONDS = 20
WP_TIMEOUT_SECONDS = 30
WP_TAG_URL_BASE = "https://yoshilover.com/tag"
# ticket 445: post type を post → page に切替 (2026-05-28 user 判断)。
# 理由: post type は yoshilover-post-noindex plugin (is_single() check) +
# SEO SIMPLE PACK 設定で site-wide noindex、 個別 checkbox 操作必要。
# page type は両 plugin の noindex 対象外 (既存 /data/ /about-yoshilover/ で確認済)、
# 切替だけで index 許可される。 plugin / SEO 設定 / user 手動 一切不要。
WP_POST_TYPE = "pages"  # /wp/v2/pages endpoint

# page split limits — user 「一日のSNSは見える量にしたい、 一軍は無理かも」
PAGE_1GUN = {
    "key": "1gun",
    "slug": "giants-sns-realtime-1gun",
    "title_suffix": "(一軍)",
    "levels": ("一軍",),
    "max_per_section": 15,
}
PAGE_FARM = {
    "key": "farm",
    "slug": "giants-sns-realtime-farm",
    "title_suffix": "(二軍・三軍)",
    "levels": ("二軍", "三軍"),
    "max_per_section": 5,
}
PAGES = (PAGE_1GUN, PAGE_FARM)


def should_run_now(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(JST)
    return now.hour in FIRE_SLOTS and now.minute < SLOT_MINUTE_WINDOW


def fetch_handle_posts(handle: str, limit: int = 30) -> List[Dict]:
    url = f"{RSSHUB_BASE}/twitter/user/{handle}?limit={limit}"
    try:
        feed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime fetch exception handle=%s url=%s err=%s", handle, url, exc)
        return []
    entries = getattr(feed, "entries", None) or []
    if not entries:
        _logger.warning("sns_realtime fetch empty handle=%s bozo=%s", handle, getattr(feed, "bozo", 0))
        return []
    posts: List[Dict] = []
    for entry in entries[:limit]:
        link = entry.get("link", "") or ""
        if not link:
            continue
        title = entry.get("title", "") or ""
        summary = entry.get("summary", "") or ""
        text = re.sub(r"<[^>]+>", " ", title + " " + summary)
        text = re.sub(r"\s+", " ", text).strip()
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        posts.append(
            {
                "url": link,
                "text": text,
                "handle": handle,
                "published": published,
            }
        )
    return posts


def filter_recent_24h(posts: List[Dict], now: Optional[datetime] = None) -> List[Dict]:
    now = now or datetime.now(JST)
    cutoff = now - timedelta(hours=24)
    out: List[Dict] = []
    for p in posts:
        pub = p.get("published")
        if pub is None:
            continue
        try:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(JST)
        except Exception:  # noqa: BLE001
            continue
        if pub_dt >= cutoff:
            out.append(p)
    return out


def collect_all_posts(handles: List[str] = SOURCE_HANDLES) -> List[Dict]:
    seen_urls = set()
    all_posts: List[Dict] = []
    for h in handles:
        for p in fetch_handle_posts(h):
            url = p.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_posts.append(p)
    return all_posts


def split_by_level(posts: List[Dict], roster_aliases) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {"一軍": [], "二軍": [], "三軍": []}
    for p in posts:
        level = classify_team_level(p.get("text", ""), roster_aliases)
        out[level].append(p)
    return out


def section_oembeds(posts: List[Dict], limit: int) -> List[str]:
    out: List[str] = []
    for p in posts[:limit]:
        url = p.get("url", "")
        if not url:
            continue
        out.append(build_oembed_block(url))
    return out


def wp_tag_url_for(name: str) -> str:
    """WP default tag slug = URL-encoded UTF-8 name."""
    return f"{WP_TAG_URL_BASE}/{urlquote(name, safe='')}/"


def build_pages(
    now: Optional[datetime] = None,
    prev_counts_by_page: Optional[PageCounts] = None,
) -> Tuple[List[Dict], PageCounts]:
    """Return (list of page dicts, counts_by_page).

    page dict: {title, html, slug, page_key, meta}
    counts_by_page: GCS 保存用の {page_key: {name: count}}
    """
    now = now or datetime.now(JST)
    posts = collect_all_posts()
    posts = filter_recent_24h(posts, now)
    roster = load_roster_aliases()
    by_level = split_by_level(posts, roster)
    prev_by_page = prev_counts_by_page or {}
    updated_at = now.strftime("%Y-%m-%d %H:%M")

    pages: List[Dict] = []
    counts_by_page: PageCounts = {}
    updated_at_iso = now.strftime("%Y-%m-%dT%H:%M:00+09:00")
    for page in PAGES:
        page_posts: List[Dict] = []
        for level in page["levels"]:
            page_posts.extend(by_level.get(level, []))
        page_counts = count_mentions([p["text"] for p in page_posts], roster)
        counts_by_page[page["key"]] = page_counts
        prev = prev_by_page.get(page["key"], {})

        trend_html = render_trend_chips(
            page_counts,
            prev_counts=prev,
            tag_url_for=wp_tag_url_for,
        )

        sections: List[Tuple[str, List[str]]] = []
        # JSON-LD ItemList 用 (oEmbed と同じ順序 / 件数で抽出)
        posts_for_listing: List[Dict] = []
        if len(page["levels"]) == 1:
            # 一軍 page = 単一 section、 max_per_section 件まで表示
            level = page["levels"][0]
            level_posts = by_level.get(level, [])
            sections.append(("最新の投稿", section_oembeds(level_posts, limit=page["max_per_section"])))
            posts_for_listing = level_posts[: page["max_per_section"]]
        else:
            # farm page = 二軍 + 三軍 を別 section で
            for level in page["levels"]:
                lvl_posts = by_level.get(level, [])
                blocks = section_oembeds(lvl_posts, limit=page["max_per_section"])
                if blocks:
                    sections.append((level, blocks))
                posts_for_listing.extend(lvl_posts[: page["max_per_section"]])

        page_url = f"https://yoshilover.com/{page['slug']}/"
        page_label = page["title_suffix"]  # "(一軍)" 等
        html = render_full_html(
            updated_at,
            trend_html,
            sections,
            SOURCE_HANDLES,
            page_label=page_label,
            stats={"posts": len(page_posts), "trend": len(page_counts)},
            page_url=page_url,
            updated_at_iso=updated_at_iso,
            posts_for_listing=posts_for_listing,
        )
        title = f"巨人 SNS リアルタイム {page['title_suffix']} (最終更新: {updated_at} JST)"
        pages.append(
            {
                "title": title,
                "html": html,
                "slug": page["slug"],
                "page_key": page["key"],
                "meta": {
                    "post_count": len(page_posts),
                    "trend_player_count": len(page_counts),
                    "prev_count_loaded": bool(prev),
                    "section_counts": {lvl: len(by_level.get(lvl, [])) for lvl in page["levels"]},
                },
            }
        )
    return pages, counts_by_page


def wp_upsert(title: str, content: str, slug: str, wp_client) -> Tuple[str, int]:
    """page (post type=page) に upsert。 post type を page にすることで
    yoshilover-post-noindex plugin + SEO SIMPLE PACK の noindex 対象外 → 自動 index。"""
    api = wp_client.api
    auth = wp_client.auth
    resp = requests.get(
        f"{api}/{WP_POST_TYPE}",
        params={"slug": slug, "_fields": "id", "status": "any"},
        auth=auth,
        timeout=WP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    items = resp.json() or []
    if items:
        page_id = int(items[0]["id"])
        upd = requests.post(
            f"{api}/{WP_POST_TYPE}/{page_id}",
            auth=auth,
            json={"title": title, "content": content},
            timeout=WP_TIMEOUT_SECONDS,
        )
        upd.raise_for_status()
        return "updated", page_id
    cr = requests.post(
        f"{api}/{WP_POST_TYPE}",
        auth=auth,
        json={
            "title": title,
            "content": content,
            "slug": slug,
            "status": "draft",
        },
        timeout=WP_TIMEOUT_SECONDS,
    )
    cr.raise_for_status()
    return "created", int(cr.json()["id"])


def run(wp_client=None, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now(JST)
    if not should_run_now(now):
        return {"ran": False, "reason": "outside_fire_slot", "hour": now.hour, "minute": now.minute}
    prev_by_page = load_previous_counts(now)
    pages, counts_by_page = build_pages(now, prev_counts_by_page=prev_by_page)
    if not any(p["meta"]["post_count"] for p in pages):
        _logger.info("sns_realtime no posts in last 24h; skip wp upsert")
        return {"ran": False, "reason": "no_posts_24h", "pages": [p["meta"] for p in pages]}
    if wp_client is None:
        return {
            "ran": False,
            "reason": "no_wp_client",
            "pages": [{"slug": p["slug"], "title": p["title"], "meta": p["meta"]} for p in pages],
        }
    results: List[Dict] = []
    for page in pages:
        if not page["meta"]["post_count"]:
            results.append({"slug": page["slug"], "skipped": "no_posts"})
            continue
        try:
            op, post_id = wp_upsert(page["title"], page["html"], page["slug"], wp_client)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("sns_realtime wp_upsert failed slug=%s: %s", page["slug"], exc)
            results.append({"slug": page["slug"], "error": str(exc)})
            continue
        results.append({"slug": page["slug"], "op": op, "post_id": post_id, "meta": page["meta"]})
    save_ok = save_counts(counts_by_page, now)
    _logger.info("sns_realtime done save_ok=%s results=%s", save_ok, results)
    return {"ran": True, "results": results, "save_counts_ok": save_ok}
