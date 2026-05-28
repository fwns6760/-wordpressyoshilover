"""sns_realtime_topic — main module: RSSHub fetch → 分類 → render → WP upsert.

ticket 445: SNS リアルタイム話題 (巨人 1軍/2軍/3軍) daily aggregation.

source = 巨人専門 / 球団公式 X 4 account を RSSHub 経由で取得。
1 日 4 fire (10/13/17/21 JST) を内部 time gate で発火。
WP slug = `giants-sns-realtime-{YYYY-MM-DD}` で 1 日 1 URL upsert。

追加コスト ¥0: 新 Scheduler / X API / LLM なし。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import feedparser
import requests

from sns_realtime_topic_classifier import (
    classify_team_level,
    count_mentions,
    load_roster_aliases,
)
from sns_realtime_topic_template import render_full_html, render_trend_chips
from wp_draft_creator import build_oembed_block

_logger = logging.getLogger(__name__)

RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
SOURCE_HANDLES = ["yomiuri_giants", "TokyoGiants", "hochi_giants", "Sanspo_Giants"]
JST = timezone(timedelta(hours=9))
FIRE_SLOTS = {10, 13, 17, 21}
SLOT_MINUTE_WINDOW = 5  # 各 fire slot の :00-:04 内で発火
MAX_PER_SECTION = 5
RSSHUB_TIMEOUT_SECONDS = 20
WP_TIMEOUT_SECONDS = 30


def should_run_now(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(JST)
    return now.hour in FIRE_SLOTS and now.minute < SLOT_MINUTE_WINDOW


def fetch_handle_posts(handle: str, limit: int = 30) -> List[Dict]:
    url = f"{RSSHUB_BASE}/twitter/user/{handle}?limit={limit}"
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
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
            # 公開日時不明は除外 (古い post の混入を避ける)
            continue
        try:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(JST)
        except Exception:
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


def section_oembeds(posts: List[Dict], limit: int = MAX_PER_SECTION) -> List[str]:
    out: List[str] = []
    for p in posts[:limit]:
        url = p.get("url", "")
        if not url:
            continue
        out.append(build_oembed_block(url))
    return out


def build_article(now: Optional[datetime] = None) -> Tuple[str, str, str, Dict]:
    """Return (title, html, slug, meta)."""
    now = now or datetime.now(JST)
    posts = collect_all_posts()
    posts = filter_recent_24h(posts, now)
    roster = load_roster_aliases()
    counts = count_mentions([p["text"] for p in posts], roster)
    trend_html = render_trend_chips(counts)
    by_level = split_by_level(posts, roster)
    sections = [
        ("一軍", section_oembeds(by_level["一軍"])),
        ("二軍", section_oembeds(by_level["二軍"])),
        ("三軍", section_oembeds(by_level["三軍"])),
    ]
    updated_at = now.strftime("%Y-%m-%d %H:%M")
    title = f"巨人 SNS リアルタイム ({updated_at} JST 更新)"
    html = render_full_html(updated_at, trend_html, sections, SOURCE_HANDLES)
    slug = f"giants-sns-realtime-{now.strftime('%Y-%m-%d')}"
    meta = {
        "post_count_24h": len(posts),
        "level_counts": {k: len(v) for k, v in by_level.items()},
        "trend_player_count": len(counts),
    }
    return title, html, slug, meta


def wp_upsert(title: str, content: str, slug: str, wp_client) -> Tuple[str, int]:
    """Return ('updated', post_id) or ('created', post_id).

    新規作成時は status='draft' で作る。 publish は user 判断 (CLAUDE.md §11)。
    """
    api = wp_client.api
    auth = wp_client.auth
    resp = requests.get(
        f"{api}/posts",
        params={"slug": slug, "_fields": "id", "status": "any"},
        auth=auth,
        timeout=WP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    items = resp.json() or []
    if items:
        post_id = int(items[0]["id"])
        upd = requests.post(
            f"{api}/posts/{post_id}",
            auth=auth,
            json={"title": title, "content": content},
            timeout=WP_TIMEOUT_SECONDS,
        )
        upd.raise_for_status()
        return "updated", post_id
    cr = requests.post(
        f"{api}/posts",
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
    """Main entry called from fetcher pipeline. Skip if not in fire slot."""
    now = now or datetime.now(JST)
    if not should_run_now(now):
        return {"ran": False, "reason": "outside_fire_slot", "hour": now.hour, "minute": now.minute}
    title, html, slug, meta = build_article(now)
    if not meta["post_count_24h"]:
        _logger.info("sns_realtime no posts in last 24h; skip wp upsert")
        return {"ran": False, "reason": "no_posts_24h", "slug": slug, "meta": meta}
    if wp_client is None:
        return {
            "ran": False,
            "reason": "no_wp_client",
            "title": title,
            "slug": slug,
            "meta": meta,
        }
    try:
        op, post_id = wp_upsert(title, html, slug, wp_client)
    except Exception as exc:
        _logger.exception("sns_realtime wp_upsert failed slug=%s: %s", slug, exc)
        return {"ran": False, "reason": "wp_upsert_failed", "slug": slug, "error": str(exc)}
    _logger.info(
        "sns_realtime done op=%s post_id=%s slug=%s meta=%s",
        op,
        post_id,
        slug,
        meta,
    )
    return {"ran": True, "op": op, "post_id": post_id, "slug": slug, "title": title, "meta": meta}
