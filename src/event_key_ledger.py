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

# 朝の自動補強 (morning_event_key_enricher) を回す時刻 = 翌日 JST 07:00。
# この時刻を境に、game_date 帰属 / window close / 自動補強 cron が揃う。
# - JST 07:00 より前 = 前日試合の朝刊サイクル中 → 前日の game_date に帰属
# - JST 07:00 以降 = 当日扱い → window=closed → 自動補強 trigger
MORNING_CUTOFF_HOUR = 7

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

# ─── event_subtype keyword sets (v2 — player × subtype event_key) ───────────
HOME_VISIT_KWS = ("故郷", "凱旋", "出身校", "出身地", "地元")
DEBUT_KWS = ("デビュー", "プロ初", "初出場", "初安打", "初本塁打", "初登板", "初猛打賞", "初勝利", "初セーブ")
RELIEF_KWS = ("救援", "抑え", "セーブ", "クローザー", "降臨")
STARTING_PITCHER_KWS = ("先発", "完封", "完投")
DECISIVE_KWS = ("決勝打", "決勝", "勝ち越し")
PITCHING_INNINGS_RE = re.compile(r"[0-9０-９]+回")
SUBJECT_MARKER_LOOKAHEAD = 2  # name の直後 N chars 以内に "が" → subject marker

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
    opponent or trigger a game-related event_type keyword.

    Since yoshilover is a Giants-only blog, any CORE event (サヨナラ /
    HR / etc.) is by definition Giants context — even if the title omits
    『巨人』 (e.g. 公式 YouTube タイトルで 🐵ジョージが…)."""
    t = rec.title
    if any(k in t for k in OB_OR_OFFGAME_EXCLUSION_KWS):
        return False
    if rec.event_type in CORE_EVENT_TYPES:
        return True
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


# ─── event_subtype + event_player helpers (v2) ──────────────────────────────


def derive_event_subtype(title: str) -> str:
    """Map ``title`` to a player-level event_subtype.

    Order is significant — more specific subtypes win over fall-throughs.
    The categories below correspond to topics that a single player can
    have multiple of on the same day; we keep them as **separate**
    event_keys so 「佐々木サヨナラHR」 and 「佐々木の故郷話」 do not merge.
    """
    t = title

    # Hardest signals first.
    if any(k in t for k in WALK_OFF_KWS):
        return "walk_off"
    if any(k in t for k in RECORD_COMPARE_KWS):
        return "record_milestone"
    if any(k in t for k in DECISIVE_KWS):
        return "decisive_hit"
    has_homerun_kw = any(k in t for k in HOMERUN_KWS) or bool(HOMERUN_NRAN_RE.search(t))
    has_given_up = any(k in t for k in HOMERUN_GIVEN_UP_KWS)
    if has_homerun_kw and not has_given_up:
        return "homerun"
    if any(k in t for k in HOME_VISIT_KWS):
        return "home_visit"
    if any(k in t for k in DEBUT_KWS):
        return "debut_milestone"
    if any(k in t for k in STANDALONE_LANE_KWS):
        return "lineup_role"
    if any(k in t for k in STARTING_PITCHER_KWS) and PITCHING_INNINGS_RE.search(t):
        return "starting_pitcher"
    if any(k in t for k in RELIEF_KWS):
        return "relief"
    return "generic"


# Subtypes that absorb generic-subtype articles for the same player.
# Generic articles attach to the player's "primary subtype event" of the
# day if one exists; otherwise generic forms its own event_key.
PRIMARY_SUBTYPES_FOR_GENERIC_MERGE = (
    "walk_off",
    "homerun",
    "decisive_hit",
    "home_visit",
    "debut_milestone",
    "starting_pitcher",
    "relief",
    "record_milestone",
    "lineup_role",
)


def _allowlist_pool() -> tuple[str, ...]:
    """Return the Giants player allowlist (longest first) reused from
    :mod:`player_eyecatch_resolver`."""
    from src.player_eyecatch_resolver import _load_giants_name_pool  # noqa: WPS433

    pool, _ = _load_giants_name_pool()
    return pool


def find_all_allowlist_players(title: str) -> list[str]:
    """All Giants allowlist players in title, longest-first dedup.

    Detection order:

    1. Full-name substring match for every name in the pool (longest
       first).
    2. Unique 2-char surname fallback — when a 2-char prefix maps to
       exactly one allowlist name and that prefix is present, add the
       full name. Recovers cases like 「佐々木の長打力」 where the title
       only contains the surname; this mirrors :func:`detect_person`'s
       own surname fallback so the resulting set is consistent with the
       primary-player path."""
    if not title:
        return []
    pool = _allowlist_pool()
    found: list[str] = []
    for name in pool:
        if name in title and name not in found:
            found.append(name)
    surname_index: dict[str, list[str]] = {}
    for name in pool:
        if len(name) >= 2:
            surname_index.setdefault(name[:2], []).append(name)
    for surname, cands in surname_index.items():
        if len(cands) == 1 and surname in title and cands[0] not in found:
            found.append(cands[0])
    return found


def has_subject_marker(title: str, name: str) -> bool:
    """True if ``name`` is followed within :data:`SUBJECT_MARKER_LOOKAHEAD`
    chars by the Japanese subject marker ``が``. This is a crude but
    effective signal for "who performed the action" in a multi-name
    title like 「戸郷翔征に今季初勝利を！女房・大城卓三**が**先制４号ソロ」
    (subject = 大城卓三)."""
    if not title or not name:
        return False
    idx = title.find(name)
    if idx < 0:
        return False
    tail = title[idx + len(name): idx + len(name) + SUBJECT_MARKER_LOOKAHEAD]
    return "が" in tail


def derive_event_player(rec: PostRecord) -> str:
    """Pick the player whose **story** this article tells.

    Heuristics, in order:

    1. If :func:`detect_person` returned the manager (阿部慎之助) and a
       different allowlist player appears in the title, prefer that
       other player (監督 が選手を語る → その選手の event)。
    2. If multiple allowlist players appear and the primary one has no
       subject marker (``が``) but another does, prefer the が-marked
       one (the actor) over the merely-mentioned name.
    3. Otherwise the primary :func:`detect_person` result wins.
    """
    primary = rec.player or ""
    if not primary:
        return ""
    others = [n for n in find_all_allowlist_players(rec.title) if n != primary]

    # Heuristic 1: manager + other → other
    if primary == "阿部慎之助" and others:
        return others[0]

    # Heuristic 2: が-subject marker outranks first-mention
    if others and not has_subject_marker(rec.title, primary):
        for other in others:
            if has_subject_marker(rec.title, other):
                return other

    return primary


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


def _make_event_key(game_date: str, opponent: str, player: str, subtype: str) -> str:
    return f"{game_date or 'undated'}|giants_vs_{opponent or 'none'}|{player or 'team'}|{subtype}"


def _kind_for(player: str, subtype: str) -> str:
    """Coarse-grained 'kind' tag for downstream filtering (the enricher,
    summary reports, etc.). Backward-compat: ``game_result`` is still
    emitted for the major in-game subtypes so the enricher and existing
    tests can pivot on it."""
    if player == "team":
        return "lineup"
    if subtype in {"walk_off", "homerun", "decisive_hit", "starting_pitcher", "relief"}:
        return "game_result"
    if subtype in {"home_visit", "debut_milestone", "record_milestone", "lineup_role"}:
        return "player_topic"
    if subtype == "generic":
        return "player_quote"
    return "other"


def group_records(
    records: list[PostRecord],
    *,
    now: Optional[dt.datetime] = None,
) -> list[dict]:
    """Group records into ``(game_date, opponent, event_player, subtype)``
    event_keys (v2 player × subtype design).

    Algorithm
    ---------
    1. Annotate every record with ``event_player`` (via
       :func:`derive_event_player`) and ``event_subtype`` (via
       :func:`derive_event_subtype`).
    2. ``lineup_pre`` / ``lineup_post`` event_types are *team-level* — they
       get ``event_player="team"`` and form their own one-record groups
       (lineup is a distinct search intent from anything a single
       player did).
    3. Records lacking Giants context (二軍/OB/追悼 etc.) form orphan
       solo groups so they appear in the ledger but never join a
       game-result event.
    4. Per-day generic-subtype articles for a player attach to that
       player's strongest non-generic subtype event of the day (if
       any), so 「大城卓三「風に乗ってくれました」」 (generic) gets
       absorbed into 「大城 + homerun」.
    5. For each surviving bucket, the earliest record is the parent and
       the rest are children. Children carry an :func:`derive_enrichment_role`
       tag for the morning enricher.
    """
    records_sorted = sorted(records, key=lambda r: r.published_at)
    records_sorted = fill_inferred_opponents(records_sorted)
    now = now or dt.datetime.now(JST)

    # Pass 1: annotate
    annotated: list[tuple[PostRecord, str, str]] = []
    deferred_no_player_core: list[tuple[PostRecord, str]] = []
    # annotation_map[post_id] = the event_player attributed in Pass 1.
    # Used during group construction so that deferred (no-player) records
    # never become parents of a player-named event_key.
    annotation_map: dict[int, str] = {}
    for rec in records_sorted:
        # OB / 二軍 / 追悼 → orphan solo group
        if not has_giants_game_context(rec):
            annotated.append((rec, "", "orphan"))
            continue
        # Team-level lineup → its own group
        if rec.event_type in LINEUP_EVENT_TYPES:
            annotated.append((rec, "team", rec.event_type))
            annotation_map[rec.post_id] = "team"
            continue
        ep = derive_event_player(rec)
        sub = derive_event_subtype(rec.title)
        if not ep:
            # No allowlist player. If the article carries a strong day-event
            # signal (walk_off / homerun / standings / video of the result /
            # etc.), defer it for attachment to the day's dominant player
            # event of the same subtype (e.g., 📺YouTube公開「ジョージが…」
            # → 佐々木 walk_off).
            if sub in PRIMARY_SUBTYPES_FOR_GENERIC_MERGE:
                deferred_no_player_core.append((rec, sub))
            else:
                annotated.append((rec, "", "orphan"))
            continue
        annotated.append((rec, ep, sub))
        annotation_map[rec.post_id] = ep

    # Pass 2: bucket by (date, opp, player, subtype)
    buckets: dict[tuple[str, str, str, str], list[PostRecord]] = {}
    orphans: list[PostRecord] = []
    for rec, ep, sub in annotated:
        if ep == "":
            orphans.append(rec)
            continue
        key = (rec.game_date or "undated", rec.opponent or "none", ep, sub)
        buckets.setdefault(key, []).append(rec)

    # Pass 2.5: attach deferred no-player CORE-subtype records to the
    # dominant player event for (date, opponent, subtype).
    dominant_by_subtype: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
    for key, recs in buckets.items():
        date, opp, player, sub = key
        if player == "team" or sub not in PRIMARY_SUBTYPES_FOR_GENERIC_MERGE:
            continue
        skey = (date, opp, sub)
        current = dominant_by_subtype.get(skey)
        if current is None or len(recs) > len(buckets[current]):
            dominant_by_subtype[skey] = key
    for rec, sub in deferred_no_player_core:
        skey = (rec.game_date or "undated", rec.opponent or "none", sub)
        target = dominant_by_subtype.get(skey)
        if target is not None:
            buckets[target].append(rec)
        else:
            orphans.append(rec)

    # Pass 3: find each player's primary non-generic subtype event of the
    # day so generic articles can attach to it.
    primary_by_player: dict[tuple[str, str, str], tuple[str, str, str, str]] = {}
    # Iterate in event-priority order so the strongest subtype wins.
    for priority_sub in PRIMARY_SUBTYPES_FOR_GENERIC_MERGE:
        for key in buckets:
            date, opp, player, sub = key
            if sub != priority_sub or player == "team":
                continue
            primary_by_player.setdefault((date, opp, player), key)

    merged: dict[tuple[str, str, str, str], list[PostRecord]] = {}
    for key, recs in buckets.items():
        date, opp, player, sub = key
        if sub == "generic" and player != "team":
            primary_key = primary_by_player.get((date, opp, player))
            if primary_key:
                merged.setdefault(primary_key, []).extend(recs)
                continue
        merged.setdefault(key, []).extend(recs)

    # Pass 4: build groups
    groups: list[dict] = []
    for key, recs in merged.items():
        date, opp, player, sub = key
        recs_in_order = sorted(recs, key=lambda r: r.published_at)
        # Parent = earliest record that was originally annotated with this
        # bucket's player. Deferred no-player records can be children but
        # never the headline parent (we don't want a relief-pitcher
        # support article to displace 佐々木's HR as the サヨナラ event
        # parent).
        native_recs = [r for r in recs_in_order if annotation_map.get(r.post_id) == player]
        parent_rec = native_recs[0] if native_recs else recs_in_order[0]
        child_recs = [r for r in recs_in_order if r.post_id != parent_rec.post_id]
        close_dt = window_close_for(date) if date != "undated" else None
        window_status: str
        close_iso: Optional[str]
        open_iso = parent_rec.published_at
        if close_dt is not None:
            close_iso = close_dt.isoformat()
            window_status = "closed" if now >= close_dt else "open"
        else:
            close_iso = None
            window_status = "n/a"
        groups.append({
            "event_key": _make_event_key(date, opp, player, sub),
            "kind": _kind_for(player, sub),
            "game_date": "" if date == "undated" else date,
            "opponent": "" if opp == "none" else opp,
            "event_player": player,
            "event_subtype": sub,
            # Backward-compat alias for the enricher and existing
            # ``--preview-hero`` CLI; matches event_player except for the
            # team-lineup case where we expose an empty hero.
            "hero_player": player if player != "team" else "",
            "parent_id": parent_rec.post_id,
            "parent": _record_summary(parent_rec),
            "children": [
                {**_record_summary(c), "enrichment_role": derive_enrichment_role(c)}
                for c in child_recs
            ],
            "standalone": [],
            "all_ids": [r.post_id for r in recs_in_order],
            "window": {
                "open_at": open_iso,
                "close_at": close_iso,
                "status": window_status,
            },
        })

    # Orphan groups for OB / 二軍 / 追悼 / no-player records
    for rec in orphans:
        ek = f"{rec.game_date or 'undated'}|giants_vs_{rec.opponent or 'none'}|orphan|{rec.event_type}|{rec.post_id}"
        groups.append({
            "event_key": ek,
            "kind": "orphan",
            "game_date": rec.game_date,
            "opponent": rec.opponent,
            "event_player": "",
            "event_subtype": "orphan",
            "hero_player": rec.player,
            "parent_id": rec.post_id,
            "parent": _record_summary(rec),
            "children": [],
            "standalone": [],
            "all_ids": [rec.post_id],
            "window": {"open_at": rec.published_at, "close_at": None, "status": "n/a"},
        })

    # axis_coverage per group (drives the morning enricher's completeness
    # checklist). Counts children by enrichment_role plus a +1 for
    # parent's "result_summary" presence.
    for grp in groups:
        if grp.get("kind") not in {"game_result", "player_topic", "player_quote"}:
            continue
        covered: dict[str, int] = {axis: 0 for axis in COMPLETENESS_AXES}
        if grp.get("parent"):
            covered["result_summary"] = 1
        for ch in grp["children"]:
            role = ch.get("enrichment_role")
            if role in covered:
                covered[role] += 1
        grp["axis_coverage"] = covered
        grp["axes_covered"] = sum(1 for v in covered.values() if v > 0)
        grp["axes_total"] = len(COMPLETENESS_AXES)
        grp["completeness_pct"] = round(100 * grp["axes_covered"] / grp["axes_total"], 1)

    return groups


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
