"""event_key_ledger.py — Read-only audit ledger for grouping same-event articles.

Phase 0 of the parent-article system. Mutation-free.

Given a date range, fetch published WP posts, group them by event_key
``(game_date, opponent, hero_player, event_type)`` and classify each
member as parent / child_update / standalone.

For each game_result group we additionally compute:

* ``enrichment_role`` for every child (which axis the child extends
  on top of the parent: 監督コメント / 本人コメント / YouTube動画 /
  Instagram / ポスト=ファンの声 / 順位影響 / 場面詳細 / 翌朝刊コラム)
* ``axis_coverage`` — which of the 7 completeness axes have at least
  one supporting article
* ``window`` — start = parent published_at, close = next JST 10:00 (翌朝刊
  サイクル終了), ``status`` = open | closed based on ``--now``

Output: ``logs/event_key_observation/<label>.jsonl`` (one group per line)

Usage::

    python3 -m src.event_key_ledger --date 2026-05-12
    python3 -m src.event_key_ledger --since 2026-05-10 --until 2026-05-14
    python3 -m src.event_key_ledger --date 2026-05-12 --preview-hero 佐々木俊輔
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.player_eyecatch_resolver import detect_person  # noqa: E402

logger = logging.getLogger(__name__)

JST = dt.timezone(dt.timedelta(hours=9))

# 翌朝刊サイクルの終了 = 翌日 JST 10:00。これを超えた group は closed 扱い。
MORNING_CUTOFF_HOUR = 10

# ─── opponent dictionary ─────────────────────────────────────────────────────

OPPONENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hiroshima", ("広島", "カープ")),
    ("chunichi", ("中日", "ドラゴンズ")),
    ("hanshin", ("阪神", "タイガース")),
    ("yakult", ("ヤクルト", "スワローズ")),
    ("dena", ("DeNA", "横浜")),
    ("lotte", ("ロッテ", "マリーンズ")),
    ("rakuten", ("楽天", "イーグルス")),
    ("softbank", ("ソフトバンク", "ホークス")),
    ("seibu", ("西武", "ライオンズ")),
    ("orix", ("オリックス", "バファローズ")),
    ("nipponham", ("日本ハム", "ファイターズ")),
)


def detect_opponent(title: str) -> str:
    for key, kws in OPPONENTS:
        for kw in kws:
            if kw in title:
                return key
    return ""


# ─── event_type classification ───────────────────────────────────────────────

WALK_OFF_KWS = ("サヨナラ",)
HOMERUN_KWS = ("ホームラン", "本塁打", "弾", "アーチ", "HR", "ソロ")
HOMERUN_NRAN_RE = re.compile(r"[0-9０-９]ラン")  # サヨナラ2ラン / ３ランHR 等
# 被弾系 = 投手目線でHRを「浴びる」記事。Giants HR result の anchor にしない。
HOMERUN_GIVEN_UP_KWS = ("浴び", "被弾", "被本塁打", "被ホームラン", "被弾")
VIDEO_KWS = ("【動画】", "【YouTube】", "📺YouTube", "YouTube公開", "動画公開")
INSTAGRAM_KWS = ("Instagram", "インスタ", "🐵")  # 🐵 = 佐々木のニックネーム派生 etc.は別ロジック向け
FAN_VOICE_KWS = ("ファンの声", "ファン反応", "X反応", "SNSの声", "ポストまとめ", "反響")
COLUMN_KWS = ("番記者", "G戦記", "コラム", "解説", "記者の目")
MANAGER_TOKEN = "監督"
LINEUP_PRE_KWS = ("試合前情報", "当日カード", "本日のスタメン", "試合開始", "1番ライト", "1番センター")
LINEUP_POST_KWS = ("試合終", "試合終了")
STANDINGS_KWS = ("位後退", "位浮上", "貯金", "借金", "首位", "最下位", "後退", "浮上")
RECORD_COMPARE_KWS = ("記録室", "以来", "年ぶり", "試合連続", "通算", "達成", "ぶり")
# 起用意図 / 復帰 / 二軍 等は独立 search intent として standalone 維持
STANDALONE_LANE_KWS = (
    "起用",
    "課題",
    "復帰",
    "二軍",
    "若手",
    "育成",
    "引退",
    "故障",
    "離脱",
)
SCENE_DETAIL_KWS = ("半袖", "練習", "撮影", "🏟️", "🔥📷", "📷")
QUOTE_BRACKET_RE = re.compile(r"「[^」]+」")

# 「サヨナラ HR」「決勝弾」「初本塁打」など、その日の主役級イベント
CORE_EVENT_TYPES = {
    "walk_off_hr_result",
    "walk_off_result",
    "homerun_result",
    "decisive_hit",
}
LINEUP_EVENT_TYPES = {"lineup_pre", "lineup_post"}
STANDALONE_INTENT_EVENT_TYPES = {"standalone_lane", "record_compare"}

# event_types that can be joined as a child of a game_result group.
# 場面詳細 (scene_detail) は練習/不関連を巻き込みやすいので保留。
JOINABLE_AS_CHILD_EVENT_TYPES = {
    "manager_quote",
    "player_quote",
    "video_link",
    "instagram_post",
    "fan_voice",
    "standings_impact",
    "morning_column",
}

# Opponent inference targets: 同日記事から opponent を補填してよい event_type。
# 不関連 (other / scene_detail) は inference 対象外。
OPPONENT_INFERENCE_TARGET_EVENT_TYPES = (
    CORE_EVENT_TYPES
    | JOINABLE_AS_CHILD_EVENT_TYPES
    | STANDALONE_INTENT_EVENT_TYPES
    | LINEUP_EVENT_TYPES
)

# Hard exclusions for "1軍試合の game_result group に joinable か" の判定。
# 二軍/三軍記事、OB追悼、永久欠番話題は混入させない。
OB_OR_OFFGAME_EXCLUSION_KWS = (
    "二軍", "２軍", "三軍", "３軍", "2軍", "3軍",
    "終身名誉監督", "追悼", "長嶋茂雄", "永久欠番",
    "OB", "氏が",  # 「中田翔氏が…」など OB suffix
)

GIANTS_POSITIVE_SIGNAL_KWS = ("巨人", "ジャイアンツ")


def has_giants_game_context(rec: PostRecord) -> bool:
    """Return True if the record is plausibly about the 1軍 Giants game
    being grouped. Excludes 二軍/OB/追悼 articles even when they share an
    opponent or trigger a game-related event_type keyword."""
    t = rec.title
    if any(k in t for k in OB_OR_OFFGAME_EXCLUSION_KWS):
        return False
    if rec.player:
        return True
    return any(k in t for k in GIANTS_POSITIVE_SIGNAL_KWS)


def derive_enrichment_role(rec: PostRecord) -> str:
    """Pick the most informative enrichment_role for a child record.
    Media/SNS/standings/quote signals override the generic
    ``duplicate_or_paraphrase`` that core event types map to, so the
    axis_coverage report can credit those axes properly even when the
    article also contains a result keyword."""
    t = rec.title
    if any(k in t for k in VIDEO_KWS):
        return "youtube_video"
    if "Instagram" in t or "インスタ" in t:
        return "instagram_post"
    if any(k in t for k in FAN_VOICE_KWS):
        return "fan_voice_x_post"
    if any(k in t for k in STANDINGS_KWS):
        return "standings_impact"
    if MANAGER_TOKEN in t and QUOTE_BRACKET_RE.search(t):
        return "manager_quote"
    if QUOTE_BRACKET_RE.search(t) and rec.player:
        return "player_quote"
    if any(k in t for k in COLUMN_KWS):
        return "morning_column"
    return ENRICHMENT_ROLE_BY_EVENT.get(rec.event_type, rec.event_type)


def classify_event_type(title: str) -> str:
    """Return a single event_type tag for the title.

    Order matters — earlier matches win. Standalone-intent (起用意図 / 課題 /
    復帰 / 二軍 / 育成 etc.) is checked first so column articles that happen
    to mention スタメン are not misclassified as lineup_pre.
    """
    t = title

    # Standalone-intent wins (起用意図 / 課題 / 復帰 / 二軍 ...)
    if any(k in t for k in STANDALONE_LANE_KWS):
        return "standalone_lane"

    # Lineup detection — "スタメン" prefix indicates a lineup speedrun
    # regardless of result keywords. lineup_post if 試合終, else lineup_pre.
    if any(k in t for k in LINEUP_POST_KWS):
        return "lineup_post"
    if "スタメン" in t:
        return "lineup_pre"
    if any(k in t for k in LINEUP_PRE_KWS):
        return "lineup_pre"

    # Game-result core
    has_walk_off = any(k in t for k in WALK_OFF_KWS)
    has_homerun = any(k in t for k in HOMERUN_KWS) or bool(HOMERUN_NRAN_RE.search(t))
    has_given_up = any(k in t for k in HOMERUN_GIVEN_UP_KWS)
    if has_walk_off and has_homerun:
        return "walk_off_hr_result"
    if has_walk_off:
        return "walk_off_result"

    # Record compare (記録室 / 〇年ぶり / 通算 ...)
    if any(k in t for k in RECORD_COMPARE_KWS):
        return "record_compare"

    # Media / SNS
    if any(k in t for k in FAN_VOICE_KWS):
        return "fan_voice"
    if any(k in t for k in VIDEO_KWS):
        return "video_link"
    if "Instagram" in t or "インスタ" in t:
        return "instagram_post"

    # Standings impact (順位後退 / 浮上)
    if any(k in t for k in STANDINGS_KWS):
        return "standings_impact"

    # Quote-style
    if MANAGER_TOKEN in t and QUOTE_BRACKET_RE.search(t):
        return "manager_quote"
    if detect_person(t) and QUOTE_BRACKET_RE.search(t):
        return "player_quote"

    # 番記者コラム (column without standalone intent already returned)
    if any(k in t for k in COLUMN_KWS):
        return "morning_column"

    # Scene / photo
    if any(k in t for k in SCENE_DETAIL_KWS):
        return "scene_detail"

    # Generic HR result (only when the article frames it as a Giants HR;
    # 被弾 / 浴びる は Giants 投手目線の被弾なので除外)
    if has_homerun and not has_given_up:
        return "homerun_result"

    return "other"


# event_type → enrichment_role (when joined as child to a game_result parent)
ENRICHMENT_ROLE_BY_EVENT = {
    "manager_quote": "manager_quote",
    "player_quote": "player_quote",
    "video_link": "youtube_video",
    "instagram_post": "instagram_post",
    "fan_voice": "fan_voice_x_post",
    "standings_impact": "standings_impact",
    "scene_detail": "scene_detail",
    "morning_column": "morning_column",
    "walk_off_hr_result": "duplicate_or_paraphrase",
    "walk_off_result": "duplicate_or_paraphrase",
    "homerun_result": "duplicate_or_paraphrase",
    "decisive_hit": "duplicate_or_paraphrase",
    "other": "other",
}

# 7 axis completeness checklist
COMPLETENESS_AXES = (
    "result_summary",
    "manager_quote",
    "player_quote",
    "youtube_video",
    "instagram_post",
    "fan_voice_x_post",
    "standings_impact",
    "morning_column",
)


# ─── game-date attribution ──────────────────────────────────────────────────


def attribute_game_date(published_at: str) -> str:
    """Map a publish ISO timestamp (JST naive) to the corresponding game date.

    JST 0:00–9:59 articles are attributed to the **previous** day's game
    (morning-after roundup convention). JST 10:00 onward = same day.
    """
    try:
        d = dt.datetime.fromisoformat(published_at.replace("Z", ""))
    except Exception:
        return ""
    if d.hour < MORNING_CUTOFF_HOUR:
        d -= dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def window_close_for(game_date: str) -> dt.datetime:
    """Return the JST datetime at which the event_key window closes
    (= next JST 10:00 after the game date)."""
    base = dt.date.fromisoformat(game_date)
    return dt.datetime.combine(
        base + dt.timedelta(days=1),
        dt.time(hour=MORNING_CUTOFF_HOUR),
        tzinfo=JST,
    )


# ─── WP REST fetcher (read-only, no auth required for publish status) ────────


def fetch_published_posts(
    *,
    since: dt.date,
    until: dt.date,
    base_url: Optional[str] = None,
    per_page: int = 50,
    http_get=None,
) -> list[dict]:
    """Fetch published posts in ``[since, until)`` via the public REST API.

    Paginated GET to ``/wp-json/wp/v2/posts``. ``http_get`` is injectable
    for tests.
    """
    if http_get is None:
        import requests  # local import keeps the module test-friendly

        http_get = requests.get

    url_base = (base_url or os.getenv("WP_URL", "https://yoshilover.com")).rstrip("/")
    api = f"{url_base}/wp-json/wp/v2/posts"
    out: list[dict] = []
    page = 1
    while True:
        params = {
            "per_page": per_page,
            "page": page,
            "after": f"{since.isoformat()}T00:00:00",
            "before": f"{until.isoformat()}T00:00:00",
            "_fields": "id,date,title,categories,link",
            "orderby": "date",
            "order": "asc",
        }
        resp = http_get(api, params=params, timeout=20)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json() or []
        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
        if page > 20:
            break
    return out


# ─── core grouping logic ─────────────────────────────────────────────────────


@dataclasses.dataclass
class PostRecord:
    post_id: int
    published_at: str
    game_date: str
    title: str
    player: str
    opponent: str
    event_type: str
    link: str
    categories: tuple[int, ...]


def post_to_record(post: dict) -> PostRecord:
    pid = int(post.get("id") or 0)
    pub = str(post.get("date") or "")
    title_raw = (post.get("title") or {}).get("rendered") or ""
    title = html.unescape(title_raw).replace(" ", " ").strip()
    cats_raw = post.get("categories") or []
    cats = tuple(int(c) for c in cats_raw if isinstance(c, (int, str)) and str(c).isdigit())
    return PostRecord(
        post_id=pid,
        published_at=pub,
        game_date=attribute_game_date(pub),
        title=title,
        player=detect_person(title) or "",
        opponent=detect_opponent(title),
        event_type=classify_event_type(title),
        link=str(post.get("link") or ""),
        categories=cats,
    )


def _record_summary(rec: PostRecord) -> dict:
    return {
        "post_id": rec.post_id,
        "title": rec.title,
        "event_type": rec.event_type,
        "player": rec.player,
        "published_at": rec.published_at,
        "link": rec.link,
    }


def infer_per_day_opponent(records: list[PostRecord]) -> dict[str, str]:
    """Build a ``game_date → opponent`` map from any record that explicitly
    names an opponent. Result articles often omit the opponent name (e.g.
    「巨人が今季初のサヨナラ勝ち」) — we recover it from same-day lineup
    or pre-game articles. The first non-empty opponent seen for a date
    wins (records are processed in chronological order)."""
    out: dict[str, str] = {}
    for rec in records:
        if not rec.game_date or not rec.opponent:
            continue
        out.setdefault(rec.game_date, rec.opponent)
    return out


def fill_inferred_opponents(records: list[PostRecord]) -> list[PostRecord]:
    """Return records with empty ``opponent`` filled from
    :func:`infer_per_day_opponent`. Only event_types in
    :data:`OPPONENT_INFERENCE_TARGET_EVENT_TYPES` *and* records with
    :func:`has_giants_game_context` are eligible — we don't broadcast
    opponent to 二軍/OB/追悼 articles."""
    opp_map = infer_per_day_opponent(records)
    out = []
    for rec in records:
        if rec.opponent or not rec.game_date:
            out.append(rec)
            continue
        if rec.event_type not in OPPONENT_INFERENCE_TARGET_EVENT_TYPES:
            out.append(rec)
            continue
        if not has_giants_game_context(rec):
            out.append(rec)
            continue
        inferred = opp_map.get(rec.game_date, "")
        if inferred:
            out.append(dataclasses.replace(rec, opponent=inferred))
        else:
            out.append(rec)
    return out


def _find_anchors(records: list[PostRecord]) -> dict[tuple[str, str], PostRecord]:
    """For each ``(game_date, opponent)`` pick the anchor (= parent of the
    game_result group) as the **earliest core-event record with a non-empty
    player**. If no candidate has a player, fall back to the earliest core
    record regardless of player."""
    by_key_with_player: dict[tuple[str, str], PostRecord] = {}
    by_key_fallback: dict[tuple[str, str], PostRecord] = {}
    for rec in records:
        if rec.event_type not in CORE_EVENT_TYPES:
            continue
        if not rec.opponent:
            continue
        key = (rec.game_date, rec.opponent)
        if rec.player and key not in by_key_with_player:
            by_key_with_player[key] = rec
        if key not in by_key_fallback:
            by_key_fallback[key] = rec
    return {**by_key_fallback, **by_key_with_player}


def _make_game_result_key(game_date: str, opponent: str, hero: str) -> str:
    return f"{game_date}|giants_vs_{opponent}|{hero or 'team'}|game_result"


def group_records(
    records: list[PostRecord],
    *,
    now: Optional[dt.datetime] = None,
) -> list[dict]:
    """Group records into event_key buckets and compute classification.

    Algorithm
    ---------
    1. Find anchors per ``(game_date, opponent)`` via core event_types.
    2. For each record:
       a. If event_type ∈ LINEUP → own event_key (lineup is a separate
          search intent from game result).
       b. Else if same ``(game_date, opponent)`` matches an anchor:
          - If record == anchor → parent
          - Else if event_type ∈ STANDALONE_INTENT_EVENT_TYPES → join
            the game_result group's ``standalone`` array (kept publish-
            worthy on its own).
          - Else → join ``children`` with an ``enrichment_role``.
       c. Else → standalone group of its own.
    3. Compute axis_coverage and window.open/close per group.
    """
    records_sorted = sorted(records, key=lambda r: r.published_at)
    records_sorted = fill_inferred_opponents(records_sorted)
    anchors = _find_anchors(records_sorted)
    groups: dict[str, dict] = {}
    now = now or dt.datetime.now(JST)

    def _ensure_game_result_group(rec: PostRecord) -> dict:
        anchor = anchors[(rec.game_date, rec.opponent)]
        hero = anchor.player or rec.player
        key = _make_game_result_key(rec.game_date, rec.opponent, hero)
        if key in groups:
            return groups[key]
        close_at = window_close_for(rec.game_date)
        groups[key] = {
            "event_key": key,
            "kind": "game_result",
            "game_date": rec.game_date,
            "opponent": rec.opponent,
            "hero_player": hero,
            "parent_id": None,
            "parent": None,
            "children": [],
            "standalone": [],
            "all_ids": [],
            "window": {
                "open_at": anchor.published_at,
                "close_at": close_at.isoformat(),
                "status": "closed" if now >= close_at else "open",
            },
        }
        return groups[key]

    def _make_solo_group(rec: PostRecord, *, kind: str) -> None:
        ek = f"{rec.game_date or 'undated'}|giants_vs_{rec.opponent or 'none'}|{rec.player or 'team'}|{rec.event_type}|{rec.post_id}"
        groups[ek] = {
            "event_key": ek,
            "kind": kind,
            "game_date": rec.game_date,
            "opponent": rec.opponent,
            "hero_player": rec.player,
            "parent_id": rec.post_id,
            "parent": _record_summary(rec),
            "children": [],
            "standalone": [],
            "all_ids": [rec.post_id],
            "window": {"open_at": rec.published_at, "close_at": None, "status": "n/a"},
        }

    for rec in records_sorted:
        # Lineup → own group (not joined into game_result enrichment)
        if rec.event_type in LINEUP_EVENT_TYPES:
            _make_solo_group(rec, kind="lineup")
            continue

        joins_game_result = (
            rec.opponent
            and (rec.game_date, rec.opponent) in anchors
            and rec.event_type in (
                CORE_EVENT_TYPES
                | JOINABLE_AS_CHILD_EVENT_TYPES
                | STANDALONE_INTENT_EVENT_TYPES
            )
            and has_giants_game_context(rec)
        )

        if joins_game_result:
            grp = _ensure_game_result_group(rec)
            grp["all_ids"].append(rec.post_id)
            anchor = anchors[(rec.game_date, rec.opponent)]

            if rec.post_id == anchor.post_id:
                grp["parent_id"] = rec.post_id
                grp["parent"] = _record_summary(rec)
                continue

            if rec.event_type in STANDALONE_INTENT_EVENT_TYPES:
                grp["standalone"].append({
                    **_record_summary(rec),
                    "reason": rec.event_type,
                })
                continue

            grp["children"].append({
                **_record_summary(rec),
                "enrichment_role": derive_enrichment_role(rec),
            })
        else:
            _make_solo_group(rec, kind="standalone")

    # Compute axis_coverage for game_result groups
    for grp in groups.values():
        if grp["kind"] != "game_result":
            continue
        covered: dict[str, int] = {axis: 0 for axis in COMPLETENESS_AXES}
        if grp.get("parent"):
            covered["result_summary"] = 1
        for ch in grp["children"]:
            role = ch.get("enrichment_role")
            if role in covered:
                covered[role] += 1
        # morning_column may also appear in standalone (番記者 + 起用意図)
        # which already lives in `standalone`. Detect if standalone hits column
        # keywords too so the report shows column presence.
        for st in grp["standalone"]:
            if any(k in (st.get("title") or "") for k in COLUMN_KWS):
                covered["morning_column"] += 1
        grp["axis_coverage"] = covered
        grp["axes_covered"] = sum(1 for v in covered.values() if v > 0)
        grp["axes_total"] = len(COMPLETENESS_AXES)
        grp["completeness_pct"] = round(100 * grp["axes_covered"] / grp["axes_total"], 1)

    return list(groups.values())


# ─── output ─────────────────────────────────────────────────────────────────


def write_ledger(groups: Iterable[dict], out_dir: Path, label: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for g in groups:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return path


def render_enriched_preview(group: dict) -> str:
    """Render a markdown preview of the enriched parent article — read-only.
    Uses titles/links only; full body merge requires fetching content
    (out of scope for the audit ledger)."""
    if group.get("kind") != "game_result":
        return f"# event_key {group['event_key']} は game_result ではありません (kind={group['kind']})\n"

    lines: list[str] = []
    parent = group.get("parent") or {}
    lines.append(f"# Enriched parent preview")
    lines.append("")
    lines.append(f"- **event_key**: `{group['event_key']}`")
    lines.append(f"- **game_date**: {group['game_date']}  / opponent: {group['opponent']}  / hero: {group['hero_player']}")
    lines.append(f"- **window**: open_at={group['window']['open_at']}, close_at={group['window']['close_at']}, status={group['window']['status']}")
    lines.append(f"- **completeness**: {group['axes_covered']}/{group['axes_total']} axes covered ({group['completeness_pct']}%)")
    lines.append("")
    lines.append(f"## Parent (代表記事 = 1本に集約する宛先)")
    lines.append(f"- [{parent.get('post_id')}]({parent.get('link')}) — {parent.get('title')}")
    lines.append("")

    by_role: dict[str, list[dict]] = {}
    for ch in group.get("children", []):
        by_role.setdefault(ch.get("enrichment_role") or "other", []).append(ch)

    role_labels = [
        ("manager_quote", "## 監督コメント（追記候補）"),
        ("player_quote", "## 本人 / 関係者コメント（追記候補）"),
        ("youtube_video", "## YouTube動画（埋め込み候補）"),
        ("instagram_post", "## Instagram（埋め込み候補）"),
        ("fan_voice_x_post", "## X ポスト = ファンの声（引用候補）"),
        ("standings_impact", "## 順位への影響（追記候補）"),
        ("scene_detail", "## 場面詳細 / 写真"),
        ("morning_column", "## 翌朝刊コラム（番記者・解説）"),
        ("duplicate_or_paraphrase", "## 結果言い換え（吸収すれば parent に統合可能）"),
    ]
    for role_key, label in role_labels:
        items = by_role.get(role_key, [])
        if not items:
            continue
        lines.append(label)
        for it in items:
            lines.append(f"- [{it['post_id']}]({it['link']}) {it['title']}")
        lines.append("")

    standalone = group.get("standalone", [])
    if standalone:
        lines.append("## 別 event_key（独立 publish 維持＝起用意図・記録比較など）")
        for it in standalone:
            lines.append(f"- [{it['post_id']}]({it['link']}) ({it['reason']}) — {it['title']}")
        lines.append("")

    cov = group.get("axis_coverage", {})
    lines.append("## 完成チェックリスト（翌朝刊で揃ったか）")
    for axis in COMPLETENESS_AXES:
        mark = "✅" if cov.get(axis, 0) > 0 else "❌"
        lines.append(f"- {mark} {axis} (count={cov.get(axis, 0)})")
    lines.append("")

    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only event_key audit ledger for WP posts.")
    p.add_argument("--date", help="single date YYYY-MM-DD")
    p.add_argument("--since", help="start date inclusive YYYY-MM-DD")
    p.add_argument("--until", help="end date exclusive YYYY-MM-DD (default = since+1)")
    p.add_argument("--out", default=None, help="output dir (default logs/event_key_observation)")
    p.add_argument("--preview-hero", default=None, help="hero player name to render markdown preview for")
    p.add_argument("--print", action="store_true", help="also print groups to stdout as JSONL")
    return p.parse_args(argv)


def _resolve_dates(args: argparse.Namespace) -> tuple[dt.date, dt.date, str]:
    if args.date:
        since = dt.date.fromisoformat(args.date)
        until = since + dt.timedelta(days=1)
    elif args.since:
        since = dt.date.fromisoformat(args.since)
        until = dt.date.fromisoformat(args.until) if args.until else since + dt.timedelta(days=1)
    else:
        until = dt.date.today()
        since = until - dt.timedelta(days=1)
    label = since.isoformat() if (until - since) == dt.timedelta(days=1) else f"{since.isoformat()}_to_{until.isoformat()}"
    return since, until, label


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    since, until, label = _resolve_dates(args)

    # For groups dated within "until" the 翌朝刊 cycle may still be open
    # → fetch one extra day so the morning-after roundup is included.
    fetch_until = until + dt.timedelta(days=1)
    posts = fetch_published_posts(since=since, until=fetch_until)
    records = [post_to_record(p) for p in posts]
    groups = group_records(records)

    # Filter to groups whose game_date is in [since, until)
    filtered = [
        g for g in groups
        if g.get("game_date") and since.isoformat() <= g["game_date"] < until.isoformat()
    ]

    out_dir = Path(args.out) if args.out else ROOT / "logs" / "event_key_observation"
    path = write_ledger(filtered, out_dir, label)

    summary = {
        "posts_fetched": len(posts),
        "groups_total": len(filtered),
        "game_result_groups": sum(1 for g in filtered if g["kind"] == "game_result"),
        "standalone_groups": sum(1 for g in filtered if g["kind"] == "standalone"),
        "lineup_groups": sum(1 for g in filtered if g["kind"] == "lineup"),
        "child_updates_total": sum(len(g.get("children", [])) for g in filtered),
        "ledger_path": str(path),
    }
    print(json.dumps(summary, ensure_ascii=False))

    if args.preview_hero:
        target = next(
            (g for g in filtered if g["kind"] == "game_result" and g.get("hero_player") == args.preview_hero),
            None,
        )
        if target is None:
            print(f"preview: no game_result group with hero='{args.preview_hero}'", file=sys.stderr)
            return 2
        md_path = out_dir / f"{label}_preview_{args.preview_hero}.md"
        md_path.write_text(render_enriched_preview(target), encoding="utf-8")
        print(json.dumps({"preview_path": str(md_path)}, ensure_ascii=False))

    if args.print:
        for g in filtered:
            print(json.dumps(g, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
