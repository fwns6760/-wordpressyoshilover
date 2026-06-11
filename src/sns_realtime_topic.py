"""sns_realtime_topic — main module: RSSHub fetch → 分類 → render → WP upsert (page split).

ticket 445: SNS リアルタイム話題 daily aggregation (page split: 一軍 / ファーム).

URL モデル: **permanent 2 URL** (Yahoo リアルタイム検索式)
- `giants-sns-realtime-1gun` — 一軍 投稿 上位 15 件
- `giants-sns-realtime-farm` — 二軍 上位 5 + 三軍 上位 5 = 最大 10 件

source = 巨人専門 / 球団公式 / 主要スポーツ紙 X account を RSSHub 経由で取得。
10:00 / 12:00 / 15:00-17:00 / 22:00 は毎時、試合中 18:00-21:15 は
15分に1回の内部 time gate で発火。

enhancement (a) + (b):
- (a) 急上昇 marker: 昨日の言及回数 (GCS、 page 別 nested dict) と diff
       初日 (前日 counts なし) は badge 抑制 (全員 ↑+N 出ないようにする)
- (b) tag chip → WP tag page link
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote as urlquote

import feedparser
import requests

from sns_realtime_topic_classifier import (
    classify_team_level,
    count_mentions,
    is_giants_relevant,
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
# 巨人専門アカウント = 全 post 通す (team news が keyword 無しでも巨人確定)
# 巨人公式は @TokyoGiants。 旧 yomiuri_giants は RSSHub で死にデータ (1月の「@趣味」RT) を
# 返す死にハンドルだったため除外 (実feed検証済 2026-06-01)。
GIANTS_SPECIALIST_HANDLES = ["TokyoGiants", "hochi_giants", "Sanspo_Giants"]
# 大手の野球全般アカウント = 全12球団 post を含むため巨人 relevance filter を適用
# (巨人 + 元巨人 OB MLB 岡本/菅野 のみ通過、 大谷 等 非 OB MLB は drop)
MAJOR_GENERAL_HANDLES = [
    "sponichiyakyuu",   # スポニチ 野球
    "nikkan_yakyuude",  # 日刊スポーツ 野球取材基地
    "Daily_Online",     # デイリースポーツ
    "sponichiannex",    # スポニチ 公式 (general)
    "nikkansports",     # 日刊スポーツ 公式 (general)
]
SOURCE_HANDLES = GIANTS_SPECIALIST_HANDLES + MAJOR_GENERAL_HANDLES
GIANTS_FILTER_HANDLES = set(MAJOR_GENERAL_HANDLES)
JST = timezone(timedelta(hours=9))
# 2026-06-03 user: 朝(10,12)+ 15時から毎時 (練習シーン増・試合・試合後)。
# 2026-06-07 user: 試合中SNSは15分に1回、21:15まででよい。
# /run は giants-* trigger が該当時刻に発火済み
# (6-16 hourly + 17-21 0,30 + 18-21 15,45 + 22/23)。
# Gemini 不使用ページなので頻度UPしてもコスト増ほぼ無し (RSSHub+Cloud Runのみ)。
REGULAR_FIRE_HOURS = {10, 12, 15, 16, 17, 22}
GAME_FIRE_HOURS = {18, 19, 20, 21}
FIRE_SLOTS = REGULAR_FIRE_HOURS | GAME_FIRE_HOURS
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
WP_DATA_PAGE_URL_BASE = "https://yoshilover.com/data"
DATA_PAGES_CACHE: Dict[str, set] = {}  # process-local cache: {api_url: {slug, slug, ...}}

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
SOURCE_LABEL = "巨人公式・専門メディア・主要スポーツ紙X"
EXTRA_GAME_DATE_ENV = "SNS_REALTIME_EXTRA_GAME_DATE"
EXTRA_GAME_START_ENV = "SNS_REALTIME_EXTRA_GAME_START"
EXTRA_GAME_END_ENV = "SNS_REALTIME_EXTRA_GAME_END"


def _minute_in_slot_window(minute: int, slot_start: int) -> bool:
    return slot_start <= minute < min(slot_start + SLOT_MINUTE_WINDOW, 60)


def _parse_hhmm(value: str) -> Optional[int]:
    raw = (value or "").strip()
    if not raw:
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _extra_game_window_minutes(now: datetime) -> Optional[tuple[int, int]]:
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    game_date = (os.environ.get(EXTRA_GAME_DATE_ENV) or "").strip()
    if not game_date or game_date != now_jst.date().isoformat():
        return None
    start = _parse_hhmm(os.environ.get(EXTRA_GAME_START_ENV, ""))
    end = _parse_hhmm(os.environ.get(EXTRA_GAME_END_ENV, ""))
    if start is None or end is None or end < start:
        return None
    return start, end


def _extra_game_fire_minute_slots(now: datetime) -> tuple[int, ...]:
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    window = _extra_game_window_minutes(now)
    if window is None:
        return ()
    start, end = window
    hour_base = now_jst.hour * 60
    slots = []
    for slot in (0, 15, 30, 45):
        minute_of_day = hour_base + slot
        if start <= minute_of_day <= end:
            slots.append(slot)
    return tuple(slots)


def _is_extra_game_fire_slot(now: datetime) -> bool:
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    return any(_minute_in_slot_window(now_jst.minute, start) for start in _extra_game_fire_minute_slots(now_jst))


def _game_fire_minute_slots(hour: int) -> tuple[int, ...]:
    if hour == 21:
        return (0, 15)
    return (0, 15, 30, 45)


def should_run_now(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    if _is_extra_game_fire_slot(now_jst):
        return True
    if now_jst.hour in GAME_FIRE_HOURS:
        return any(_minute_in_slot_window(now_jst.minute, start) for start in _game_fire_minute_slots(now_jst.hour))
    return now_jst.hour in REGULAR_FIRE_HOURS and now_jst.minute < SLOT_MINUTE_WINDOW


def is_sns_only_game_dense_slot(now: Optional[datetime] = None) -> bool:
    """試合中 15分更新のうち、重い RSS 記事生成を走らせない SNS 専用 slot。

    :00 は従来の fetcher 本線に残す。:15/:30/:45 は SNS ページ更新だけにして、
    Cloud Run fire は維持しつつ Gemini / article draft path を避ける。
    """
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    extra_slots = _extra_game_fire_minute_slots(now)
    if extra_slots:
        if any(_minute_in_slot_window(now_jst.minute, start) for start in extra_slots if start > 0):
            return True
    if now_jst.hour not in GAME_FIRE_HOURS:
        return False
    return any(_minute_in_slot_window(now_jst.minute, start) for start in _game_fire_minute_slots(now_jst.hour) if start > 0)


def is_redundant_after_game_dense_slot(now: Optional[datetime] = None) -> bool:
    """Scheduler が残っていても 21:15 後の dense fire は何もしない。"""
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    if now_jst.hour != 21:
        return False
    return any(_minute_in_slot_window(now_jst.minute, start) for start in (30, 45))


def _strip_feed_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def _merge_entry_text(title: str, summary: str) -> str:
    """RSSHub の title/summary 重複を軽く除去して、独自まとめ/JSON-LDを汚さない。"""
    title_text = _strip_feed_text(title)
    summary_text = _strip_feed_text(summary)
    if title_text and summary_text:
        if title_text == summary_text:
            return title_text
        if summary_text.startswith(title_text) or title_text in summary_text:
            return summary_text
        if title_text.startswith(summary_text):
            return title_text
        return f"{title_text} {summary_text}"
    return title_text or summary_text


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
        text = _merge_entry_text(title, summary)
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


def collect_all_posts(handles: List[str] = SOURCE_HANDLES, roster_aliases=None) -> List[Dict]:
    if roster_aliases is None:
        roster_aliases = load_roster_aliases()
    seen_urls = set()
    all_posts: List[Dict] = []
    for h in handles:
        needs_filter = h in GIANTS_FILTER_HANDLES
        for p in fetch_handle_posts(h):
            url = p.get("url", "")
            if not url or url in seen_urls:
                continue
            if needs_filter and not is_giants_relevant(p.get("text", ""), roster_aliases):
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


def _fetch_data_page_slugs(wp_client) -> set:
    """data-site page (parent=/data/) の slug set を返す。 process-local cache。

    (C) 内部リンク enrichment: トレンド chip 先を /data/{slug}/ に切替判定で使う。
    """
    if wp_client is None:
        return set()
    api = wp_client.api
    if api in DATA_PAGES_CACHE:
        return DATA_PAGES_CACHE[api]
    try:
        # data parent page id を slug=data で取得
        r = requests.get(
            f"{api}/pages",
            params={"slug": "data", "_fields": "id", "status": "any"},
            auth=wp_client.auth,
            timeout=WP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        items = r.json() or []
        if not items:
            DATA_PAGES_CACHE[api] = set()
            return set()
        parent_id = int(items[0]["id"])
        r2 = requests.get(
            f"{api}/pages",
            params={"parent": parent_id, "per_page": 100, "_fields": "slug"},
            auth=wp_client.auth,
            timeout=WP_TIMEOUT_SECONDS,
        )
        r2.raise_for_status()
        slugs = {p.get("slug", "") for p in (r2.json() or []) if p.get("slug")}
        DATA_PAGES_CACHE[api] = slugs
        return slugs
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sns_realtime _fetch_data_page_slugs failed: %s", exc)
        DATA_PAGES_CACHE[api] = set()
        return set()


def make_tag_url_resolver(data_slugs_available: set):
    """tag URL resolver factory。 /data/ に該当 player page があれば /data/{slug}/、
    なければ /tag/{name}/ にフォールバック (C 内部リンク enrichment)。"""
    try:
        from data_site_slug import player_slug  # type: ignore
    except Exception:
        player_slug = None  # type: ignore

    def resolve(name: str) -> str:
        if player_slug and data_slugs_available:
            slug = player_slug(name)
            if slug and slug in data_slugs_available:
                return f"{WP_DATA_PAGE_URL_BASE}/{slug}/"
        return wp_tag_url_for(name)

    return resolve


def _resolve_insight_db_path() -> Optional[str]:
    """insight.db (read-only) の local path を返す。不在/失敗時は None (成績は空表示)。

    445 enhancement (個人): 注目選手カードの今季成績充填用。GCS から read-only で
    download (free tier、 1 fire 4 回/日)。失敗しても page 生成は止めない (graceful)。
    """
    try:
        from src.manual_intake_insight_query import ensure_local_db
        info = ensure_local_db()
        if info and info.get("ok"):
            return info.get("path")
    except Exception as exc:  # noqa: BLE001
        _logger.info("sns_realtime insight.db unavailable (stats skipped): %r", exc)
    return None


def _player_stat_line(db_path: Optional[str], player: str) -> str:
    """選手の今季成績 1 行 (打者優先、 投手は登板/防御率/K)。取得不可なら空。"""
    if not db_path or not player:
        return ""
    try:
        from src.sns_topic_cards import _player_batting, _player_pitching
        bat = _player_batting(db_path, player)
        if bat and bat.get("avg") is not None:
            avg = f"{bat['avg']:.3f}".lstrip("0")
            return f"今季 打率{avg}・{bat['h']}安打{bat['rbi']}打点"
        pit = _player_pitching(db_path, player)
        if pit and pit.get("games"):
            era = f"・防御率{pit['era']:.2f}" if pit.get("era") is not None else ""
            return f"今季 {pit['games']}登板{era}・{pit['k']}K"
    except Exception as exc:  # noqa: BLE001
        _logger.info("sns_realtime stat_line skip player=%s: %r", player, exc)
    return ""


def build_featured_players(
    page_counts: Dict[str, int],
    prev_counts: Dict[str, int],
    tag_resolver,
    db_path: Optional[str],
    top_n: int = 8,
    min_count: int = 2,
) -> str:
    """445 enhancement (個人): 急上昇順の注目選手カード HTML (今季成績 1 行 + 内部リンク)。

    急上昇 / 内部リンクは既存 trend chips と同じ算出 (count diff + tag_resolver) で整合。
    db_path 不在時は成績空 (graceful、 page は出る)。Gemini 不使用 (¥0)。
    """
    from src.sns_realtime_topic_template import render_featured_players, _delta_badge
    items = [(n, c) for n, c in (page_counts or {}).items() if c >= min_count]
    items.sort(key=lambda t: (-t[1], t[0]))
    items = items[:top_n]
    if not items:
        return ""
    suppress_badge = not prev_counts
    players: List[Dict] = []
    for name, count in items:
        badge = "" if suppress_badge else _delta_badge(count - int((prev_counts or {}).get(name, 0)))
        players.append({
            "name": name,
            "count": count,
            "badge": badge,
            "stat_line": _player_stat_line(db_path, name),
            "url": tag_resolver(name) if tag_resolver else "",
        })
    return render_featured_players(players)


def _top_mention_items(page_counts: Dict[str, int], limit: int = 3) -> List[Tuple[str, int]]:
    items = [(n, c) for n, c in (page_counts or {}).items() if c >= 2]
    items.sort(key=lambda t: (-t[1], t[0]))
    return items[:limit]


def _join_names(names: List[str]) -> str:
    if not names:
        return ""
    return "、".join(names)


def build_editor_summary(
    page_label: str,
    page_posts: List[Dict],
    page_counts: Dict[str, int],
    prev_counts: Dict[str, int],
) -> Dict:
    """X 埋め込み一覧を独自コンテンツ化する deterministic summary。

    LLM/API なし。トレンド count と前日差分だけで、検索にも人間にも読める導入文を作る。
    """
    label_text = (page_label or "").strip("()") or "巨人"
    top_items = _top_mention_items(page_counts, limit=3)
    top_names = [name for name, _count in top_items]
    if top_names:
        lead = (
            f"今日の{label_text}SNSは{_join_names(top_names)}を中心に動いています。"
            f"{SOURCE_LABEL}の過去24時間投稿から、試合前後に追うべき話題をヨシラバーが整理します。"
        )
    else:
        lead = (
            f"今日の{label_text}SNSは投稿量が少なめです。"
            f"{SOURCE_LABEL}の過去24時間投稿から、更新が入り次第このページで整理します。"
        )

    bullets: List[str] = [
        f"{len(page_posts)}件の投稿を確認。ページは10時・13時・17時・21時に自動更新します。"
    ]

    spike_items: List[Tuple[str, int]] = []
    if prev_counts:
        for name, count in top_items:
            delta = count - int(prev_counts.get(name, 0))
            if delta >= 2:
                spike_items.append((name, delta))
    if spike_items:
        spike_text = " / ".join(f"{name} +{delta}" for name, delta in spike_items[:3])
        bullets.append(f"前日比で伸びた話題は {spike_text}。急に増えた選手名から流れを追えます。")
    elif top_names:
        bullets.append(f"言及が多い選手は {_join_names(top_names)}。各チップから選手データや関連記事へ移動できます。")
    else:
        bullets.append("トレンドが出た選手は上部のチップに自動表示し、選手データや関連記事へつなぎます。")

    bullets.append("X埋め込みは出典確認用として下部にまとめ、上部では話題の流れを先に読める構成にしています。")
    return {"lead": lead, "bullets": bullets}


def build_seo_excerpt(
    page_label: str,
    page_posts: List[Dict],
    page_counts: Dict[str, int],
) -> str:
    top_names = [name for name, _count in _top_mention_items(page_counts, limit=3)]
    label_text = (page_label or "").strip("()") or "巨人"
    topic = f"注目: {_join_names(top_names)}。" if top_names else "注目選手が出次第、上部に自動表示。"
    return (
        f"巨人{label_text}のSNSリアルタイム速報。{SOURCE_LABEL}の過去24時間投稿から、"
        f"今日の話題と注目選手をヨシラバーが整理。{topic}"
        f"現在{len(page_posts)}件、10/13/17/21時更新。"
    )


def build_seo_title(page_label: str) -> str:
    label_text = f" {page_label}" if page_label else ""
    return f"巨人 SNSリアルタイム速報{label_text} | 今日のX話題まとめ"


def build_pages(
    now: Optional[datetime] = None,
    prev_counts_by_page: Optional[PageCounts] = None,
    wp_client=None,
) -> Tuple[List[Dict], PageCounts]:
    """Return (list of page dicts, counts_by_page).

    page dict: {title, html, slug, page_key, meta}
    counts_by_page: GCS 保存用の {page_key: {name: count}}
    wp_client: 省略可、 渡されれば (C) 内部リンク enrichment 用に /data/ slug を fetch
    """
    now = now or datetime.now(JST)
    roster = load_roster_aliases()
    posts = collect_all_posts(roster_aliases=roster)
    posts = filter_recent_24h(posts, now)
    by_level = split_by_level(posts, roster)
    prev_by_page = prev_counts_by_page or {}
    updated_at = now.strftime("%Y-%m-%d %H:%M")
    data_slugs = _fetch_data_page_slugs(wp_client) if wp_client else set()
    tag_resolver = make_tag_url_resolver(data_slugs)
    # 445 (個人): 注目選手カードの今季成績充填用 (read-only、無ければ成績空)。
    insight_db_path = _resolve_insight_db_path()

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
            tag_url_for=tag_resolver,
        )
        # 445 (個人): 注目選手カード (急上昇順 + 今季成績 + 内部リンク)
        featured_html = build_featured_players(
            page_counts, prev, tag_resolver, insight_db_path,
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
        editor_summary = build_editor_summary(page_label, page_posts, page_counts, prev)
        try:
            from src.sns_realtime_topic_template import render_editor_summary
        except Exception:
            from sns_realtime_topic_template import render_editor_summary  # type: ignore
        editor_html = render_editor_summary(editor_summary)
        # JSON-LD LiveBlogPosting 用に published_iso を付与 (post の published_parsed → ISO 8601)
        for p in posts_for_listing:
            pub = p.get("published")
            if pub and isinstance(pub, tuple):
                try:
                    p["published_iso"] = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(JST).strftime("%Y-%m-%dT%H:%M:00+09:00")
                except Exception:  # noqa: BLE001
                    pass
        coverage_start_iso = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:00+09:00")
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
            coverage_start_iso=coverage_start_iso,
            editor_html=editor_html,
            featured_html=featured_html,
        )
        title = build_seo_title(page["title_suffix"])
        # (B) OGP / Twitter Card description 用 excerpt。計測断片でなく人間向け要約に固定。
        excerpt = build_seo_excerpt(page["title_suffix"], page_posts, page_counts)
        pages.append(
            {
                "title": title,
                "html": html,
                "slug": page["slug"],
                "page_key": page["key"],
                "excerpt": excerpt,
                "meta": {
                    "post_count": len(page_posts),
                    "trend_player_count": len(page_counts),
                    "prev_count_loaded": bool(prev),
                    "section_counts": {lvl: len(by_level.get(lvl, [])) for lvl in page["levels"]},
                    "data_slugs_available": len(data_slugs),
                },
            }
        )
    return pages, counts_by_page


def wp_upsert(title: str, content: str, slug: str, wp_client, excerpt: str = "") -> Tuple[str, int]:
    """page (post type=page) に upsert。 post type を page にすることで
    yoshilover-post-noindex plugin + SEO SIMPLE PACK の noindex 対象外 → 自動 index。

    excerpt: (B) OGP / Twitter Card description として WP/SEO PACK が拾う。
    """
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
    payload: Dict = {"title": title, "content": content}
    if excerpt:
        payload["excerpt"] = excerpt
    if items:
        page_id = int(items[0]["id"])
        upd = requests.post(
            f"{api}/{WP_POST_TYPE}/{page_id}",
            auth=auth,
            json=payload,
            timeout=WP_TIMEOUT_SECONDS,
        )
        upd.raise_for_status()
        return "updated", page_id
    create_payload = {**payload, "slug": slug, "status": "draft"}
    cr = requests.post(
        f"{api}/{WP_POST_TYPE}",
        auth=auth,
        json=create_payload,
        timeout=WP_TIMEOUT_SECONDS,
    )
    cr.raise_for_status()
    return "created", int(cr.json()["id"])


def run(wp_client=None, now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now(JST)
    if not should_run_now(now):
        return {"ran": False, "reason": "outside_fire_slot", "hour": now.hour, "minute": now.minute}
    prev_by_page = load_previous_counts(now)
    pages, counts_by_page = build_pages(now, prev_counts_by_page=prev_by_page, wp_client=wp_client)
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
            op, post_id = wp_upsert(
                page["title"], page["html"], page["slug"], wp_client,
                excerpt=page.get("excerpt", ""),
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("sns_realtime wp_upsert failed slug=%s: %s", page["slug"], exc)
            results.append({"slug": page["slug"], "error": str(exc)})
            continue
        results.append({"slug": page["slug"], "op": op, "post_id": post_id, "meta": page["meta"]})
    save_ok = save_counts(counts_by_page, now)
    _logger.info("sns_realtime done save_ok=%s results=%s", save_ok, results)
    return {"ran": True, "results": results, "save_counts_ok": save_ok}
