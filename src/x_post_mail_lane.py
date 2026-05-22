"""347 — セ・リーグ ranking X post candidate mail lane.

Generates 6-team (セ・リーグ) ranking X post candidates with multiple
metrics / period slices, composes HTML mail with X intent URLs (1-tap
to X app), sends via :mod:`src.mail_delivery_bridge`.

LLM-free, ``insight.db`` read-only.

Hard constraints (mirrors ticket 347):
    - LLM API never called.
    - ``insight.db``: read-only via :mod:`src.manual_intake_insight_query`.
    - ``article_candidates`` table: never read or written (348 owns it).
    - パ・リーグ 6 teams: filtered out, only セ 6 teams allowed.
    - Source numbers / names / ranks copied verbatim from rank result.
    - X intent URL: client-side handling (X app or twitter.com web),
      never call X API from this lane.
    - 346 ``format_as_x_post`` is imported read-only; never modified.
"""

from __future__ import annotations

import html as _html
import hashlib as _hashlib
import json as _json
import logging
import math as _math
from pathlib import Path as _Path
import random as _random
import re as _re
import sqlite3 as _sqlite3
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta, timezone as _tz
from typing import Callable, Optional
from urllib.parse import quote as _url_quote
from zoneinfo import ZoneInfo

from src.format_as_x_post import format_as_x_post as _format_as_x_post

LOG = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")

# Central League team-name aliases. Mirrors the rank result's
# ``team_code`` column (= ``team_name`` per insight_rank_query.py).
# Source: 6 セ・リーグ teams. パ・リーグ aliases are intentionally
# excluded so they get dropped at the filter step.
CENTRAL_LEAGUE_TEAM_ALIASES = frozenset(
    {
        # 巨人
        "巨人",
        "読売",
        "読売ジャイアンツ",
        "ジャイアンツ",
        "Giants",
        "GIANTS",
        "G",
        "g",
        # 阪神
        "阪神",
        "Tigers",
        "阪神タイガース",
        "T",
        # DeNA
        "DeNA",
        "横浜",
        "横浜DeNA",
        "横浜DeNAベイスターズ",
        "ベイスターズ",
        "DB",
        # ヤクルト
        "ヤクルト",
        "東京ヤクルト",
        "東京ヤクルトスワローズ",
        "Swallows",
        "S",
        # 中日
        "中日",
        "中日ドラゴンズ",
        "ドラゴンズ",
        "D",
        # 広島
        "広島",
        "広島東洋",
        "広島東洋カープ",
        "カープ",
        "C",
    }
)

# Safe ◯ metric whitelist mirrors the 348 spec (サバメトリクス系 ×
# are filtered out so this lane never proposes ISO/wOBA/FIP/etc.).
# Restricted to ``insight_rank_query.KNOWN_METRICS`` intersection so
# ``miq.query_rank`` accepts the name.
#
# 2026-05-17 OBP/SLG/OPS 復活: batting metrics (AVG/OBP/SLG/OPS) は
# `advanced_metric_snapshots` 経由で query する dispatch を追加した。
# 旧 `_aggregate_batting` が 2B/3B/HR/BB/HBP/SF を batting_logs から
# 読まず TB=0 / SLG=0 / OBP=AVG / OPS=AVG という broken 値を返して
# いた問題を、 snapshot table の事前計算 値で回避する (浦田俊輔
# 5/17 14:00 事例)。 守備位置別 と pitching metric は legacy path 維持。
SAFE_METRICS = (
    "AVG", "OBP", "SLG", "OPS",
    "ERA", "K_per_9", "BB_per_9", "HR_per_9",
)

# Batting metrics that go through the snapshot table (correct values).
# Pitching metrics keep using the legacy `query_rank_fn` path because
# `_aggregate_pitching` correctly reads `pitching_logs` columns.
_BATTING_SNAPSHOT_METRICS = frozenset({"AVG", "OBP", "SLG", "OPS"})
_PITCHING_SNAPSHOT_METRICS = frozenset({"ERA", "K_per_9", "BB_per_9", "HR_per_9"})
_SNAPSHOT_METRICS = _BATTING_SNAPSHOT_METRICS | _PITCHING_SNAPSHOT_METRICS

# period_label → snapshot scope mapping. period_label not in this map
# falls back to the legacy `query_rank_fn` path.
# 2026-05-20: 直近 N 試合 のみが新規 publish / mail combo の本流。
# calendar scope (直近1週間 / 今週 / 今月) は legacy 互換のため map 残置。
_PERIOD_LABEL_TO_SNAPSHOT_SCOPE: dict[str, str] = {
    "直近3試合": "last_3_games",
    "直近5試合": "last_5_games",
    "直近10試合": "last_10_games",
    "直近20試合": "last_20_games",
    "直近1週間": "last_7d",
    "今週": "weekly",
    "今月": "monthly",
}

# Friendly Japanese label per metric (mirrors 346 format_as_x_post
# helper but inline here to avoid coupling to a private constant).
_METRIC_LABELS_JP: dict[str, str] = {
    "AVG": "打率",
    "OBP": "出塁率",
    "SLG": "長打率",
    "OPS": "OPS",
    "ERA": "防御率",
    "K_per_9": "奪三振率",
    "BB_per_9": "与四球率",
    "HR_per_9": "被本塁打率",
}
_BATTING_METRICS = frozenset({"AVG", "OBP", "SLG", "OPS"})
_PITCHING_METRICS = frozenset({"ERA", "K_per_9", "BB_per_9", "HR_per_9"})
_FIELDING_METRICS = frozenset({"FldPct", "UZR"})
_TOPIC_FAMILY_LABELS = {
    "batting": "打撃",
    "pitching": "投球",
    "fielding": "守備",
}

# 353: metric 別 header 絵文字。 batting (AVG/OBP/SLG/OPS) = ⚾、 pitching
# (ERA / K_per_9 / BB_per_9 / HR_per_9) = ⚡、 守備 (将来拡張時) = 🛡️。
# fallback は 📊。
_METRIC_HEADER_EMOJI: dict[str, str] = {
    "AVG": "⚾",
    "OBP": "⚾",
    "SLG": "⚾",
    "OPS": "⚾",
    "ERA": "⚡",
    "K_per_9": "⚡",
    "BB_per_9": "⚡",
    "HR_per_9": "⚡",
    "FldPct": "🛡️",
}

# 353: format_as_x_post の ranking 行を post-process するための正規表現。
# 1 行 = `{rank}. {name}（{team}）{value}{marker}` を分解する。
# value は metric_jp 前置前の生数値 (.945 / 2.85 / .315 等)。
# marker = ` ← 巨人` (半角空白付き) または空。
_RANKING_ROW_PATTERN = _re.compile(
    r"^(?P<rank>\d+)\.\s+"
    r"(?P<name>[^（]+)"
    r"（(?P<team>[^）]+)）"
    r"(?P<value>\S+?)"
    r"(?P<marker>\s+←\s+巨人)?$"
)

# 351: 守備位置 single-kanji code → readable header label. Mirrors
# insight_rank_query's POSITION_ALIASES canonical kanji.
_POSITION_DISPLAY_JP: dict[str, str] = {
    "投": "投手",
    "捕": "捕手",
    "一": "一塁",
    "二": "二塁",
    "三": "三塁",
    "遊": "遊撃",
    "左": "左翼",
    "中": "中堅",
    "右": "右翼",
    "外": "外野",
    "指": "DH",
}

# X 280-char limit (we copy 346's constant intentionally — duplicating
# rather than importing keeps coupling minimal).
X_CHAR_LIMIT = 280

# X intent URL base. Use the modern canonical endpoint `x.com/intent/post`.
# The legacy `twitter.com/intent/tweet` redirects to x.com but the redirect
# can drop the `?text=` query param on some clients (observed 2026-05-21).
_X_INTENT_URL_BASE = "https://x.com/intent/post"

# Time-band label per hour for the mail subject. Picked to match the
# schedule the ticket locks (7/12/15/17:30/22:30 JST).
_TIME_BANDS = (
    (range(0, 11), "朝"),
    (range(11, 14), "昼"),
    (range(14, 17), "午後"),
    (range(17, 21), "夕方"),
    (range(21, 24), "試合後"),
)

# Time-band emoji prefixed to the mail subject so the message stands out
# among other automatic notifications in the inbox.
_TIME_BAND_EMOJI = {
    "朝": "🌅",
    "昼": "🌞",
    "午後": "☀️",
    "夕方": "🌆",
    "試合後": "🌙",
}

_TIME_BAND_PURPOSE = {
    "朝": "直近データ",
    "昼": "直近数字",
    "午後": "直近変化",
    "夕方": "試合前データ",
    "試合後": "見返したい数字",
}

_FORBIDDEN_POST_TERMS = (
    "昇格候補",
    "昇格待ったなし",
    "起用理由",
    "阿部監督",
    "首脳陣",
    "監督評価",
    "評価している",
    "ファンの反応",
    "期待が高ま",
    "注目している",
    "ブレイク確定",
    "覚醒",
)

_ROSTER_PATH = _Path(__file__).resolve().parents[1] / "config" / "giants_roster.json"
_PLAYER_NAME_CLEAN_RE = _re.compile(r"[\s　*・.．。,\-_/／（）()【】「」『』\[\]]+")


# ---------------------------------------------------------------------------
# Filter & candidate selection
# ---------------------------------------------------------------------------


def is_central_league(team_code: Optional[str]) -> bool:
    if not team_code:
        return False
    return team_code.strip() in CENTRAL_LEAGUE_TEAM_ALIASES


# 351: 巨人 alias subset (CENTRAL_LEAGUE_TEAM_ALIASES の中の Giants 限定 set)
_GIANTS_ALIASES = frozenset(
    {"巨人", "読売", "読売ジャイアンツ", "ジャイアンツ", "Giants", "GIANTS", "G", "g"}
)
_GIANTS_SQL_ALIASES = tuple(sorted(_GIANTS_ALIASES))


def _is_giants(team_code: Optional[str]) -> bool:
    if not team_code:
        return False
    return team_code.strip() in _GIANTS_ALIASES


def _normalize_player_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _PLAYER_NAME_CLEAN_RE.sub("", text)


def _load_giants_player_aliases(
    roster_path: _Path = _ROSTER_PATH,
) -> dict[str, str]:
    """Return normalized active Giants player aliases -> canonical name.

    This is intentionally local to the X mail lane so lineup focus can
    resolve names without importing the heavier RSS pipeline. Coaches /
    manager entries are excluded because lineup focus must be players
    only.
    """
    if not roster_path.exists():
        return {}
    try:
        roster = _json.loads(roster_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("failed to load Giants roster aliases: %r", exc)
        return {}

    out: dict[str, str] = {}
    prefix_buckets: dict[str, set[str]] = {}
    for row in roster:
        if not row.get("active"):
            continue
        if row.get("role") != "player":
            continue
        canonical = str(row.get("name") or "").strip()
        if not canonical:
            continue
        aliases = [canonical, *(row.get("aliases") or [])]
        for alias in aliases:
            key = _normalize_player_name(alias)
            if key:
                out.setdefault(key, canonical)
        # Yahoo lineup cells can be surname-only. Use unique short
        # prefixes defensively, including one-char names such as 丸.
        for n in (1, 2):
            prefix = _normalize_player_name(canonical)[:n]
            if prefix:
                prefix_buckets.setdefault(prefix, set()).add(canonical)
    for prefix, candidates in prefix_buckets.items():
        if len(candidates) == 1:
            out.setdefault(prefix, next(iter(candidates)))
    return out


def _active_giants_canonical_player_keys() -> set[str]:
    return {
        _normalize_player_name(canonical)
        for canonical in _load_giants_player_aliases().values()
        if _normalize_player_name(canonical)
    }


def _is_verified_full_giants_player_name(player_name: object) -> bool:
    key = _normalize_player_name(player_name)
    if not key:
        return False
    canonical_keys = _active_giants_canonical_player_keys()
    if canonical_keys:
        return key in canonical_keys
    return len(key) >= 3


def normalize_focus_player_names(
    names: Optional[list[str] | tuple[str, ...] | set[str]],
    *,
    alias_map: Optional[dict[str, str]] = None,
) -> set[str]:
    """Normalize lineup/focus names into canonical-ish match keys.

    ``names`` normally comes from Yahoo lineup rows. The return set
    contains canonical names plus raw normalized keys so matching still
    works when the roster file is unavailable.
    """
    if not names:
        return set()
    aliases = alias_map if alias_map is not None else _load_giants_player_aliases()
    out: set[str] = set()
    for name in names:
        key = _normalize_player_name(name)
        if not key:
            continue
        canonical = aliases.get(key)
        if canonical:
            out.add(_normalize_player_name(canonical))
        out.add(key)
    return out


def focus_player_names_from_lineup_rows(rows: list[dict]) -> list[str]:
    """Return canonical active Giants player names from lineup row dicts."""
    if not rows:
        return []
    aliases = _load_giants_player_aliases()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = str(row.get("name") or "").strip()
        key = _normalize_player_name(raw)
        if not key:
            continue
        canonical = aliases.get(key) or raw
        canonical_key = _normalize_player_name(canonical)
        if canonical_key and canonical_key not in seen:
            seen.add(canonical_key)
            out.append(canonical)
    return out


def _row_matches_focus_player(row: dict, focus_names: set[str]) -> bool:
    if not focus_names:
        return False
    player_key = _normalize_player_name(row.get("player_canonical"))
    if not player_key:
        return False
    if player_key in focus_names:
        return True
    for focus_key in focus_names:
        # Keep substring matching conservative. It mainly covers
        # surname-only lineup cells after roster fallback misses.
        if len(focus_key) >= 2 and (
            player_key.startswith(focus_key) or focus_key.startswith(player_key)
        ):
            return True
    return False


def filter_central_league(rows: list[dict]) -> list[dict]:
    """Keep only the rows whose ``team_code`` is one of the 6 セ teams.

    Crucial branding gate: パ・リーグ data must never reach the mail.
    """
    return [r for r in rows if is_central_league(r.get("team_code"))]


@dataclass(frozen=True)
class _MetricCombo:
    """Description of one X post candidate to attempt.

    Extended in 351 with optional ``until`` and ``position`` (守備位置 single
    kanji). ``giants_only`` remains only as a legacy signature dimension;
    new mail candidates keep the セ・リーグ field and highlight the top Giants
    row instead of re-ranking only Giants players.

    353: ``novelty`` tag drives the weighted shuffle in
    :func:`_select_with_diversity`. ``"high"`` = yoshilover 独自
    (大手新聞が出さない slice、 直近 5/10 試合 / 直近 7 日 /
    守備位置別 / 巨人最上位の短期変化 等)、 ``"mid"`` = 中間、
    ``"low"`` = 大手定番 (削除 — pool に入れない前提だが
    将来再導入時の dial として残す)。

    354: ``min_sample_override`` allows recent-N-games combos to lower
    the AB / IP threshold (e.g. 5 for 直近 5 試合) since players have
    only N appearances in that window. ``None`` keeps the caller's
    default (``pick_candidates(..., min_sample=...)``).
    """

    metric: str
    since: Optional[str]
    period_label: str
    until: Optional[str] = None
    position: Optional[str] = None
    giants_only: bool = False
    novelty: str = "mid"
    min_sample_override: Optional[int] = None


def _prev_month_range(now: datetime) -> tuple[str, str]:
    """Return (since, until) for the previous calendar month as ISO dates."""
    first_of_this = now.replace(day=1)
    last_of_prev = first_of_this - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return (
        first_of_prev.strftime("%Y-%m-%d"),
        last_of_prev.strftime("%Y-%m-%d"),
    )


def _query_recent_n_games_date_range(
    n: int, db_path: str
) -> Optional[tuple[str, str]]:
    """354: read-only SELECT from ``insight.db`` for the most recent
    ``n`` distinct giants ``game_date`` values. Returns
    ``(since_iso, until_iso)`` or ``None`` when fewer than ``n``
    games exist.

    Production DB is now all-NPB. Therefore the window must be limited
    to games whose logs actually contain a Giants team row; otherwise
    Pacific / non-Giants dates would shrink or distort the "直近 N
    試合" period used by the Giants-game-window ranking combos.
    """
    if n <= 0:
        return None
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("_query_recent_n_games_date_range: open failed: %r", exc)
        return None
    try:
        placeholders = ",".join("?" for _ in _GIANTS_SQL_ALIASES)
        cur = conn.execute(
            "SELECT DISTINCT g.game_date FROM games g "
            "WHERE g.game_date IS NOT NULL "
            "AND EXISTS ("
            "  SELECT 1 FROM batting_logs b "
            "  WHERE b.game_id = g.game_id "
            f"  AND b.team_name IN ({placeholders})"
            ") "
            "ORDER BY g.game_date DESC LIMIT ?",
            (*_GIANTS_SQL_ALIASES, n),
        )
        dates = [row[0] for row in cur if row and row[0]]
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("_query_recent_n_games_date_range: query failed: %r", exc)
        return None
    finally:
        conn.close()
    if len(dates) < n:
        return None
    # dates is sorted DESC, so dates[0] = newest, dates[-1] = oldest.
    return (dates[-1], dates[0])


def query_db_latest_game_date(db_path: str) -> Optional[str]:
    """Return the newest ``games.game_date`` from a read-only insight DB."""
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("query_db_latest_game_date: open failed: %r", exc)
        return None
    try:
        cur = conn.execute(
            "SELECT MAX(game_date) FROM games WHERE game_date IS NOT NULL"
        )
        row = cur.fetchone()
        value = row[0] if row else None
        return str(value) if value else None
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("query_db_latest_game_date: query failed: %r", exc)
        return None
    finally:
        conn.close()


def _query_rank_from_snapshots(
    db_path: str,
    *,
    metric_name: str,
    snapshot_scope: str,
    min_sample: int = 1,
    limit: int = 200,
) -> dict:
    """Query ``advanced_metric_snapshots`` for a metric ranking.

    Returns rows shaped like
    :func:`src.manual_intake_insight_query.query_rank`'s output so
    callers can use either path without branching the consumer.

    Used for batting metrics (AVG / OBP / SLG / OPS) where the legacy
    `_aggregate_batting` is broken (only reads AB / H from
    `batting_logs`, leaving 2B/3B/HR/BB/HBP/SF at 0 and producing
    SLG=0 / OBP=AVG / OPS=AVG misleadingly). The snapshot table has
    correct pre-computed values across all 7 scopes (last_7d /
    last_30d / last_5_games / last_10_games / weekly / monthly /
    season), populated by `insight_nightly`.

    `team_code` is normalised to the team's Japanese display name
    (via the `teams` table) so existing
    :data:`CENTRAL_LEAGUE_TEAM_ALIASES` filter and the
    `format_as_x_post` body composer accept it unchanged. Position
    filter is not supported (snapshot's `position` column is always
    NULL on production).
    """
    try:
        from src.analysis import insight_rank_query as rq  # local import
    except ImportError as exc:  # noqa: BLE001
        LOG.warning("_query_rank_from_snapshots: import failed: %r", exc)
        return {
            "ok": False,
            "reason": "import_failed",
            "rows": [],
            "count": 0,
            "total": 0,
            "focus_player": None,
        }
    if metric_name not in rq.KNOWN_METRICS:
        return {
            "ok": False,
            "reason": f"invalid_metric:{metric_name}",
            "rows": [],
            "count": 0,
            "total": 0,
            "focus_player": None,
        }
    _kind, higher_is_better = rq.KNOWN_METRICS[metric_name]
    order_dir = "DESC" if higher_is_better else "ASC"
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("_query_rank_from_snapshots: open failed: %r", exc)
        return {
            "ok": False,
            "reason": "db_open_failed",
            "rows": [],
            "count": 0,
            "total": 0,
            "focus_player": None,
        }
    sql = (
        "WITH latest AS ( "
        "  SELECT MAX(snapshot_date) AS d "
        "  FROM advanced_metric_snapshots "
        "  WHERE metric_name = ? AND scope = ? "
        ") "
        "SELECT s.player_canonical, "
        "       COALESCE(t.team_name, s.team_code) AS team_name, "
        "       s.metric_value, "
        "       s.sample_size "
        "FROM advanced_metric_snapshots s "
        "JOIN latest l ON 1=1 "
        "LEFT JOIN teams t ON t.team_code = s.team_code "
        "WHERE s.metric_name = ? "
        "  AND s.scope = ? "
        "  AND s.snapshot_date = l.d "
        "  AND s.player_canonical IS NOT NULL "
        "  AND s.sample_size >= ? "
        f"ORDER BY s.metric_value {order_dir} "
        "LIMIT ?"
    )
    try:
        rows = conn.execute(
            sql,
            (metric_name, snapshot_scope, metric_name, snapshot_scope,
             min_sample, limit),
        ).fetchall()
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("_query_rank_from_snapshots: query failed: %r", exc)
        return {
            "ok": False,
            "reason": "query_failed",
            "rows": [],
            "count": 0,
            "total": 0,
            "focus_player": None,
        }
    finally:
        conn.close()
    total = len(rows)
    rows_out = [
        {
            "player_canonical": r[0],
            "team_code": r[1],
            "metric_value": float(r[2]) if r[2] is not None else 0.0,
            "sample_size": int(r[3] or 0),
            "rank": i + 1,
            "total": total,
        }
        for i, r in enumerate(rows)
    ]
    return {
        "ok": True,
        "rows": rows_out,
        "count": len(rows_out),
        "total": total,
        "focus_player": None,
    }


def db_staleness_days(
    latest_game_date: Optional[str], now: Optional[datetime] = None
) -> Optional[int]:
    """Return JST date difference from ``latest_game_date``.

    ``None`` means the date is missing or malformed, so callers should
    avoid treating the DB as fresh.
    """
    if not latest_game_date:
        return None
    try:
        latest = _date.fromisoformat(latest_game_date)
    except ValueError:
        return None
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    today = now.astimezone(JST).date()
    return (today - latest).days


def _build_combos(
    now: datetime, db_path: Optional[str] = None
) -> list[_MetricCombo]:
    """Compose the metric × period × position combo pool for one mail.

    353/356: 大手新聞が出しやすい「シーズン累積 / 直近30日」
    combo を pool から除外し、 yoshilover 独自度の高い slice
    (直近1週間 / 直近5試合 / 直近10試合 / 今週 / 今月 / 守備位置別
    / 巨人最上位の短期変化) を novelty_high として扱う。

    STEP1 (2026-05-17): metric pool を 3 → 8 に拡張 (OPS/AVG/ERA +
    OBP/SLG/K_per_9/BB_per_9/HR_per_9)、 period pool を 直近1週間
    のみ → 直近1週間 + 直近5試合 + 直近10試合 + 今週 + 今月 + 前月
    に拡張。 24h dedup の signature が ``(metric, period_label, position)``
    だから combo pool が広いほど starvation 解消、 連日同じ ranking が
    出にくくなる。 1 mail 中の `_period_family_key` ({metric}|{position})
    で同一 metric 多窓の重複は防止される。

    2026-05-20 user 方針 (additive 段階): 直近 3 試合 / 直近 20 試合 を
    追加 (combo pool 拡張)。 計算は per-player rolling (snapshot 経由)。
    将来 commit で calendar scope (直近1週間 / 今週 / 今月 / 前月) を
    削除し、 直近 3/5/10/20 試合のみに統一する予定。
    """
    combos: list[_MetricCombo] = []

    # 1. 直近1週間 — short-term league slice (打撃 only).
    # 先発投手は週 1 回しか投げないため、 直近1週間で投手指標を取ると
    # 1 登板分に依存する不安定な数値になる。 投手は今月 / シーズン /
    # 前月 等の長窓のみで集計する (394 fix)。
    last7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    for m in SAFE_METRICS:
        if m in _PITCHING_METRICS:
            continue
        combos.append(_MetricCombo(m, last7, "直近1週間", novelty="high"))
    # 2. 守備位置別 AVG (直近1週間) — niche slice。
    # snapshot path は position 列が常に NULL なので、 守備位置別は
    # legacy `_aggregate_batting` を使う必要がある。 そちらは AVG が
    # 正しく計算されるが OBP/SLG/OPS は broken なので AVG のみ採用。
    # 守備位置 single-kanji codes match insight_rank_query expectations.
    for pos in ("捕", "二", "遊", "三"):
        combos.append(
            _MetricCombo("AVG", last7, "直近1週間", position=pos, novelty="high")
        )
    # 3. 354+STEP1+397: 直近 3/5/10/20 巨人試合 × 8 metric — yoshilover
    # 独自の試合数 base ranking。 games table が読めて且つ N 試合分の
    # row があれば追加 (case-by-case fallback、 取得失敗時は skip)。
    # 397 (2026-05-20): 投手も snapshot per-player rolling 経由で含める。
    # 旧 (5/10 試合のみ batter) → 新 (3/5/10/20 試合 batter+pitcher)。
    if db_path:
        for n_games, label in (
            (3, "直近3試合"),
            (5, "直近5試合"),
            (10, "直近10試合"),
            (20, "直近20試合"),
        ):
            window = _query_recent_n_games_date_range(n_games, db_path)
            if window is None:
                continue
            since, until = window
            for m in SAFE_METRICS:
                combos.append(
                    _MetricCombo(
                        m,
                        since,
                        label,
                        until=until,
                        novelty="high",
                        min_sample_override=max(1, n_games // 2)
                            if m in _PITCHING_METRICS
                            else n_games,
                    )
                )
    # 4. STEP1: 今週 — current ISO week Monday to today × 8 metric.
    # 直近1週間 と微妙に窓が違う (週初始まり) ことで day-over-day variety を増やす。
    week_since = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    if week_since != last7:
        for m in SAFE_METRICS:
            # 394 fix: 今週 (Mon-today) も短窓のため投手指標は除外
            if m in _PITCHING_METRICS:
                continue
            combos.append(
                _MetricCombo(m, week_since, "今週", novelty="high")
            )
    # 5. STEP1: 今月 — current month 1st to today × 8 metric (年通開放).
    month_first = now.replace(day=1).strftime("%Y-%m-%d")
    for m in SAFE_METRICS:
        combos.append(
            _MetricCombo(m, month_first, "今月", novelty="high")
        )
    # 6. 357: 前月成績 — 「N月成績」 表記、 月初 3 日だけ追加 (毎日出すと
    # 今月 combo と重複過剰になるため期間限定)。
    if 1 <= now.day <= 3:
        month_since, month_until = _prev_month_range(now)
        month_label = _month_period_label(month_since, month_until) or "前月成績"
        for m in SAFE_METRICS:
            min_sample_override = (
                10 if m in ("ERA", "K_per_9", "BB_per_9", "HR_per_9") else 30
            )
            combos.append(
                _MetricCombo(
                    m,
                    month_since,
                    month_label,
                    until=month_until,
                    novelty="high",
                    min_sample_override=min_sample_override,
                )
            )
    return combos


# 353: novelty tag → sampling weight。 high が 70% / mid 30% / low 10%
# (low は本 pool に存在しないが将来再導入時の dial として残す)。
_NOVELTY_WEIGHTS: dict[str, float] = {
    "high": 70.0,
    "mid": 30.0,
    "low": 10.0,
}


def _select_with_diversity(
    combos: list[_MetricCombo],
    *,
    max_candidates: int,
    now: datetime,
) -> list[_MetricCombo]:
    """Weighted-shuffle ``combos`` deterministically per (date, hour)
    seed and return up to ``max_candidates``.

    353: shuffle is now **weighted by novelty tag** so 「大手にない」
    combo (novelty="high") get sampled first more often than 中間
    (novelty="mid"). Implementation uses the classical exp-distributed
    key trick (a.k.a. weighted reservoir sampling via key
    ``-log(uniform()) / weight``) which yields a deterministic
    weighted permutation given a fixed RNG seed.

    Same hour on the same day yields the same order; day-over-day or
    band-over-band produces different orderings while keeping the
    high-novelty bias intact.
    """
    if not combos:
        return []
    seed = int(now.strftime("%Y%m%d")) * 100 + now.hour
    rng = _random.Random(seed)
    keyed: list[tuple[float, _MetricCombo]] = []
    for combo in combos:
        weight = _NOVELTY_WEIGHTS.get(combo.novelty, _NOVELTY_WEIGHTS["mid"])
        u = rng.random()
        if u <= 0.0:
            u = 1e-12
        # higher weight → smaller key → sorts first (= sampled first)
        key = -_math.log(u) / max(weight, 1e-9)
        keyed.append((key, combo))
    keyed.sort(key=lambda x: x[0])
    shuffled = [c for _, c in keyed]
    return shuffled[: max(1, max_candidates)]


@dataclass(frozen=True)
class Candidate:
    title: str
    metric: str
    period_label: str
    draft_text: str
    char_count: int
    # 355: combo signature for 24h dedup gate. ``""`` (default) keeps
    # backward compatibility with older tests that build Candidate
    # directly without going through ``pick_candidates``.
    signature: str = ""
    # Human-facing X post copy. ``draft_text`` keeps the detailed data
    # card / ranking proof; compose_mail uses this field for the actual
    # X intent URL when present.
    post_text: str = ""
    # Optional fact-locked context, e.g. "今日のスタメン". This changes
    # only the framing, not the numeric facts.
    context_label: str = ""
    # Player selected as the post focus. Used to spread one mail across
    # multiple lineup players before repeating the same name.
    focus_player: str = ""
    # Source-backed material classification for RSS/news candidates.
    source_material_type: str = ""
    # One DB-verified numeric fact line. Empty means no numeric fact is
    # safe to place in the public post text.
    db_fact_line: str = ""
    # Source-backed topic family for safe comment x DB merging.
    source_topic_family: str = ""


_DEFAULT_PLAYER_MAX_PER_MAIL = 1
_NEWS_OPINION_METRIC = "NEWS_OPINION"
_COMMENT_DB_METRIC = "COMMENT_DB"
_FAN_VOICE_METRIC = "FAN_VOICE"
_COMMENT_TERMS = (
    "コメント",
    "語った",
    "話した",
    "明かした",
    "強調",
    "振り返った",
    "意気込",
    "語気",
    "一問一答",
    "談話",
    "「",
    "」",
)
_RECORD_TERMS = (
    "記録",
    "達成",
    "節目",
    "通算",
    "連続",
    "初勝利",
    "初安打",
    "初本塁打",
    "初打点",
    "初登板",
    "初先発",
    "初出場",
    "最速",
    "最年少",
)
_FARM_TERMS = (
    "2軍",
    "二軍",
    "ファーム",
    "イースタン",
    "育成",
)
_BATTING_TOPIC_TERMS = (
    "打撃",
    "打席",
    "打率",
    "出塁",
    "長打",
    "OPS",
    "安打",
    "本塁打",
    "ホームラン",
    "打点",
    "打線",
    "バット",
    "打つ",
    "打った",
    "打ち",
    "猛打賞",
    "適時打",
    "タイムリー",
)
_PITCHING_TOPIC_TERMS = (
    "投球",
    "登板",
    "先発",
    "リリーフ",
    "救援",
    "マウンド",
    "投手",
    "防御率",
    "奪三振",
    "三振",
    "四球",
    "与四球",
    "被本塁打",
    "失点",
    "無失点",
    "完封",
    "好投",
)
_FIELDING_TOPIC_TERMS = (
    "守備",
    "捕球",
    "失策",
    "遊撃",
    "二塁",
    "三塁",
    "一塁",
    "外野",
    "中堅",
    "右翼",
    "左翼",
    "捕手",
    "送球",
)


def _truncate_text(value: object, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _classify_news_material(title: str, excerpt: str) -> tuple[str, str]:
    """Classify RSS/source material without inventing facts."""
    haystack = f"{title} {excerpt}"
    if any(term in haystack for term in _COMMENT_TERMS):
        return "comment", "コメント"
    if any(term in haystack for term in _RECORD_TERMS):
        return "record", "記録/節目"
    if any(term in haystack for term in _FARM_TERMS):
        return "farm", "ファーム"
    return "trend", "話題"


def _infer_source_topic_family(title: str, excerpt: str) -> str:
    haystack = f"{title} {excerpt}"
    hits = []
    if any(term in haystack for term in _BATTING_TOPIC_TERMS):
        hits.append("batting")
    if any(term in haystack for term in _PITCHING_TOPIC_TERMS):
        hits.append("pitching")
    if any(term in haystack for term in _FIELDING_TOPIC_TERMS):
        hits.append("fielding")
    return hits[0] if len(hits) == 1 else ""


def _metric_topic_family(metric: str) -> str:
    if metric in _BATTING_METRICS:
        return "batting"
    if metric in _PITCHING_METRICS:
        return "pitching"
    if metric in _FIELDING_METRICS:
        return "fielding"
    return ""


def _build_source_backed_post_text(player: str, material_type: str) -> str:
    """Build URL-free, hashtag-free copy from verified source presence only.

    RSS titles/summaries can contain unverified numbers, so the public
    post text only uses the detected player name and the source-backed
    material type. The URL/title stay in ``draft_text`` as evidence.
    """
    if material_type == "comment":
        body = (
            "コメントは、数字より先に空気が出る。\n\n"
            f"{player}の言葉は、今の状態を見直す材料になる。\n"
            "強気なのか、課題を見ているのか。\n\n"
            "巨人ファンとしては、次の出番で確かめたいところ。"
        )
    elif material_type == "record":
        body = (
            "記録は、数字そのものより積み重ねが出る。\n\n"
            f"{player}のこの話題は、あとで振り返る材料として残しておきたい。\n\n"
            "巨人の中でどんな意味を持つかまで見たい。"
        )
    elif material_type == "farm":
        body = (
            "ファームの話題は、今すぐの結論より次の準備として見たい。\n\n"
            f"{player}の名前が出ているなら、一軍の流れとつなげて追っておきたい。\n\n"
            "巨人の層を考える材料になる。"
        )
    else:
        body = (
            "名前が続けて出てくる時は、少し意味がある。\n\n"
            f"{player}の話題は、結果だけでなく起用や立ち位置まで見たくなる。\n\n"
            "今の巨人でどう扱われるか、次の流れを追いたい。"
        )
    return _finalize_post_text(body)


def build_comment_numeric_candidate(
    news_candidate: Candidate,
    data_candidate: Candidate,
) -> Optional[Candidate]:
    """Combine a source-backed comment hook with one DB-verified fact.

    The merge is intentionally narrow: the RSS side must be classified
    as a comment, both candidates must resolve to the same focus player,
    and the data side must carry a prebuilt ``db_fact_line`` copied from
    the ranking result.
    """
    player = str(news_candidate.focus_player or "").strip()
    player_key = _normalize_player_name(player)
    data_player_key = _normalize_player_name(data_candidate.focus_player)
    source_topic_family = str(news_candidate.source_topic_family or "").strip()
    data_topic_family = _metric_topic_family(data_candidate.metric)
    if (
        news_candidate.metric != _NEWS_OPINION_METRIC
        or news_candidate.source_material_type != "comment"
        or not player_key
        or player_key != data_player_key
        or not _is_verified_full_giants_player_name(player)
        or not source_topic_family
        or not data_topic_family
        or source_topic_family != data_topic_family
        or not str(data_candidate.db_fact_line or "").strip()
    ):
        return None
    fact_line = str(data_candidate.db_fact_line or "").strip().rstrip("。")
    body = (
        "コメントは、数字より先に空気が出る。\n\n"
        f"{player}の言葉を見たうえで、DBで確認できる数字も一つ。\n"
        f"{fact_line}。\n\n"
        "数字だけで決めず、次の出番でどう出るか見たい。"
    )
    post_text = _finalize_post_text(body)
    if not _is_safe_post_text(post_text):
        return None
    signature_hash = _hashlib.sha1(
        f"{news_candidate.signature}\n{data_candidate.signature}\n{player_key}".encode("utf-8")
    ).hexdigest()[:16]
    draft_text = "\n".join(
        [
            "【根拠: コメント×DB照合済み数値】",
            "DB数値照合: あり（同一フルネーム+論点一致）",
            "論点照合: あり（"
            f"コメント={_TOPIC_FAMILY_LABELS.get(source_topic_family, source_topic_family)} / "
            f"DB={_TOPIC_FAMILY_LABELS.get(data_topic_family, data_topic_family)}）",
            f"結合選手: {player}",
            "",
            "【コメント根拠】",
            news_candidate.draft_text,
            "",
            "【DB数値根拠】",
            data_candidate.draft_text,
        ]
    )
    metric_label = _METRIC_LABELS_JP.get(data_candidate.metric, data_candidate.metric)
    return Candidate(
        title=(
            f"DB照合済: フルネーム+論点一致｜コメント×DB｜"
            f"{player}｜{metric_label} {data_candidate.period_label}"
        ),
        metric=_COMMENT_DB_METRIC,
        period_label="コメント×DB",
        draft_text=draft_text,
        char_count=len(post_text),
        signature=f"comment_db|{signature_hash}|False|None",
        post_text=post_text,
        focus_player=player,
        source_material_type="comment_db",
        db_fact_line=fact_line,
        source_topic_family=source_topic_family,
    )


def detect_giants_player_name(
    text: object,
    *,
    alias_map: Optional[dict[str, str]] = None,
) -> str:
    """Return a source-evidence player name mentioned in ``text``.

    This is used only for news/opinion fallback candidates. It does not
    infer a player from context; it requires an active Giants roster
    alias to appear in the source title/summary text.
    """
    normalized_text = _normalize_player_name(text)
    if not normalized_text:
        return ""
    aliases = alias_map if alias_map is not None else _load_giants_player_aliases()
    if not aliases:
        return ""
    for key, canonical in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if len(key) < 2 and key != "丸":
            continue
        if len(key) < 2 and "巨人" not in str(text) and "ジャイアンツ" not in str(text):
            continue
        if key and key in normalized_text:
            return str(canonical or "").strip()
    return ""


def build_news_opinion_candidate(
    *,
    source_title: str,
    source_url: str,
    player_name: str,
    source_name: str = "",
    source_excerpt: str = "",
    now: Optional[datetime] = None,  # noqa: ARG001 - kept for caller symmetry/tests
) -> Optional[Candidate]:
    """Build a fallback X candidate from explicit source text only.

    The generated post avoids invented stats, quotes, and claims. It
    names the player only when the caller supplies a detected roster
    match from the source title/summary.
    """
    title = _truncate_text(source_title, 70)
    player = str(player_name or "").strip()
    url = str(source_url or "").strip()
    if not title or not url or not player:
        return None
    if not _is_verified_full_giants_player_name(player):
        return None
    source = _truncate_text(source_name, 28)
    excerpt = _truncate_text(source_excerpt, 120)
    material_type, material_label = _classify_news_material(title, excerpt)
    source_topic_family = _infer_source_topic_family(title, excerpt)
    post_text = _build_source_backed_post_text(player, material_type)
    proof_lines = [
        "【根拠: RSS/ニュース候補】",
        f"材料種別: {material_label} ({material_type})",
        "論点種別: "
        f"{_TOPIC_FAMILY_LABELS.get(source_topic_family, 'なし')}"
        "（DB結合は同一論点の時だけ）",
        f"元媒体: {source or 'unknown'}",
        f"元記事タイトル: {title}",
        f"元記事URL: {url}",
        f"検出選手: {player}",
        "DB数値照合: なし（未照合のため投稿本文には数値を入れない）",
    ]
    if excerpt:
        proof_lines.append(f"元記事抜粋: {excerpt}")
    signature_hash = _hashlib.sha1(f"{url}\n{player}".encode("utf-8")).hexdigest()[:16]
    return Candidate(
        title=f"要確認: 数値未照合｜{material_label}案｜{player}｜{title}",
        metric=_NEWS_OPINION_METRIC,
        period_label=material_label,
        draft_text="\n".join(proof_lines),
        char_count=len(post_text),
        signature=f"news_opinion|{signature_hash}|False|None",
        post_text=post_text,
        focus_player=player,
        source_material_type=material_type,
        source_topic_family=source_topic_family,
    )


def build_fan_voice_candidate(
    entry: dict,
    *,
    detected_player: str = "",
) -> Optional[Candidate]:
    """397: build a 「(参考) 巨人ファン X 投稿」 candidate from a fan_voice_pool
    GCS record (produced by ``record_fan_voice_pool_entries_to_gcs``).

    The candidate carries the raw tweet text (literal, attribution
    preserved), not a generated post. user uses this as voice reference
    to write their own X post manually.

    Returns ``None`` (silent skip) when:
    - URL or text empty
    - text length out of 20-280 chars
    - ``detected_player`` empty (= no Giants player NER hit in text)
    """
    if not isinstance(entry, dict):
        return None
    url = str(entry.get("url") or "").strip()
    text = str(entry.get("text") or "").strip()
    handle = str(entry.get("handle") or "").strip()
    source_name = str(entry.get("source_name") or "").strip()
    pub_iso = str(entry.get("pub_iso") or "").strip()
    if not url or not text:
        return None
    if len(text) < 20 or len(text) > 280:
        return None
    if not detected_player:
        return None
    title_preview = _truncate_text(text.replace("\n", " "), 40)
    title = f"(参考) ファン投稿｜{handle or '匿名'}｜{title_preview}"
    proof_lines = [
        "【根拠: 巨人ファン X 投稿 (参考)】",
        f"投稿者: @{handle}" if handle else "投稿者: (不明)",
        f"出典: {source_name}" if source_name else "",
        f"投稿日時: {pub_iso}" if pub_iso else "",
        f"投稿URL: {url}",
        f"検出選手: {detected_player}",
        "",
        "【元投稿本文】",
        text,
        "",
        "※ user メモ: この voice / 視点を参考に、 独自表現で post 案を書く。",
        "  literal コピーや過度な類似は避ける (引用元 @user 明示なら可)。",
    ]
    signature_hash = _hashlib.sha1(f"fan_voice|{url}".encode("utf-8")).hexdigest()[:16]
    return Candidate(
        title=title,
        metric=_FAN_VOICE_METRIC,
        period_label="(参考) ファン投稿",
        draft_text="\n".join(ln for ln in proof_lines if ln is not None),
        char_count=len(text),
        signature=f"fan_voice|{signature_hash}|False|None",
        post_text="",
        focus_player=detected_player,
        source_material_type="fan_voice",
    )


def _rebuild_ranks_within_central(rows: list[dict]) -> list[dict]:
    """After filtering to セ-only, rewrite ``rank`` so the column shows
    1..N within the 6-team scope (not the 12-team residual).
    """
    out = []
    for idx, r in enumerate(rows, start=1):
        # shallow copy keeps the original rank result intact for caller
        out.append({**r, "rank": idx, "total": len(rows)})
    return out


def _top_giants_row(
    rows: list[dict],
    *,
    focus_player_names: Optional[set[str]] = None,
    avoid_player_names: Optional[set[str]] = None,
) -> Optional[dict]:
    """Return the highest-ranked Giants row from already-ranked rows."""
    focus_names = focus_player_names or set()
    avoid_names = avoid_player_names or set()
    if focus_names:
        matches = [
            row for row in rows
            if _is_giants(row.get("team_code"))
            and _row_matches_focus_player(row, focus_names)
        ]
        if not matches:
            return None
        if avoid_names:
            for row in matches:
                player_key = _normalize_player_name(row.get("player_canonical"))
                if player_key and player_key not in avoid_names:
                    return row
        return matches[0]
    matches = [row for row in rows if _is_giants(row.get("team_code"))]
    if not matches:
        return None
    if avoid_names:
        for row in matches:
            player_key = _normalize_player_name(row.get("player_canonical"))
            if player_key and player_key not in avoid_names:
                return row
    return matches[0]


def _rows_with_giants_focus(
    rows: list[dict],
    *,
    max_rows: int = 10,
    focus_row: Optional[dict] = None,
) -> list[dict]:
    """Return display rows while guaranteeing the top Giants row is visible.

    The mail must answer "巨人の選手がセ・リーグで何位か". If the first
    Giants row falls outside the top-N display, replace the last display row
    with that Giants row rather than switching to a Giants-only ranking.
    """
    if max_rows <= 0:
        return []
    top_rows = list(rows[:max_rows])
    focus = focus_row if focus_row is not None else _top_giants_row(rows)
    if focus is None:
        return top_rows
    if any(r.get("player_canonical") == focus.get("player_canonical")
           and r.get("team_code") == focus.get("team_code") for r in top_rows):
        return top_rows
    if len(top_rows) >= max_rows:
        return top_rows[:-1] + [focus]
    return top_rows + [focus]


def _scope_label(combo: _MetricCombo) -> str:
    if combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        return f"セ・{position_jp}"
    return "セ・リーグ"


def _sample_label_for_metric(metric: str) -> str:
    """Return the Japanese unit label used in the 規定打席 / 投球回 suffix.

    Batting metrics use 打席 (PA). Pitching (ERA) uses 投球回 (IP).
    """
    if metric == "ERA":
        return "投球回"
    return "打席"


def _format_period_range(combo: _MetricCombo, now: datetime) -> str:
    """Return a concrete date-range fallback label.

    357 keeps production X mail copy on human period labels such as
    ``直近5試合`` and ``7月成績``. This helper remains as a defensive
    fallback for malformed / future combos that have no period label.

    351: ``combo.until`` (e.g. 先月 = until=last day of prev month) is
    honoured when present so closed ranges show their explicit end.
    """
    today_md = f"{now.month}/{now.day}"
    if combo.since is None:
        return f"開幕〜{today_md} 累積"
    try:
        d_since = datetime.strptime(combo.since, "%Y-%m-%d")
        since_md = f"{d_since.month}/{d_since.day}"
        if combo.until:
            d_until = datetime.strptime(combo.until, "%Y-%m-%d")
            until_md = f"{d_until.month}/{d_until.day}"
            return f"{since_md}〜{until_md}"
        return f"{since_md}〜{today_md}"
    except (ValueError, TypeError):
        return combo.period_label


def _month_period_label(since: Optional[str], until: Optional[str]) -> Optional[str]:
    """Return ``N月成績`` when ``since`` / ``until`` are one calendar month."""
    if not since or not until:
        return None
    try:
        d_since = datetime.strptime(since, "%Y-%m-%d")
        d_until = datetime.strptime(until, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    if (
        d_since.year == d_until.year
        and d_since.month == d_until.month
        and d_since.day == 1
    ):
        return f"{d_since.month}月成績"
    return None


def _format_period_label(combo: _MetricCombo, now: datetime) -> str:
    """Human-first period label for X text.

    User-facing copy should lead with baseball terms such as
    ``直近5試合`` / ``直近10試合`` instead of raw date ranges. Closed
    calendar months use ``7月成績`` style labels.
    """
    month_label = _month_period_label(combo.since, combo.until)
    if month_label:
        return month_label
    if combo.period_label:
        return combo.period_label
    return _format_period_range(combo, now)


def _sample_threshold_label(metric: str, min_sample: int) -> str:
    sample_label = _sample_label_for_metric(metric)
    return f"規定{sample_label}{min_sample}以上"


def _format_metric_value(metric: str, value: object) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if metric in {"AVG", "OBP", "SLG", "OPS"}:
        s = f"{v:.3f}"
        if s.startswith("0."):
            return s[1:]
        if s.startswith("-0."):
            return "-" + s[2:]
        return s
    if metric in {"ERA", "K_per_9", "BB_per_9", "HR_per_9"}:
        return f"{v:.2f}"
    return f"{v:g}"


def _rewrite_ranking_rows(
    lines: list[str],
    metric_jp: str,
) -> list[str]:
    """STEP1 (2026-05-17): post-process each ranking row to use a
    consistent numeric prefix (``N.``), a flush Giants marker
    (``  ⭐巨人`` with two half-width spaces, no left arrow), and a
    metric-label-prefixed value (``打率 .315`` / ``OPS .945``).

    Earlier 353 variant used medals 🥇🥈🥉 for ranks 1-3 + a blank
    separator line + ``←⭐巨人`` arrow marker. STEP1 unifies the rows
    so the entire ranking reads in a single block.
    """
    new_lines: list[str] = []
    for line in lines:
        m = _RANKING_ROW_PATTERN.match(line)
        if not m:
            new_lines.append(line)
            continue
        rank_num = int(m.group("rank"))
        name = m.group("name")
        team = m.group("team")
        value = m.group("value")
        marker = m.group("marker") or ""
        # Giants marker: ` ← 巨人` → `  ⭐巨人` (two half-width spaces,
        # no arrow). The double-space separates the marker visually
        # from the value while staying ASCII-aligned across rows.
        if marker.strip():
            new_marker = "  ⭐巨人"
        else:
            new_marker = ""
        # Numeric prefix for every rank (no medals).
        prefix = f"{rank_num}."
        # Metric label prefix on value (e.g. ``打率 .315`` / ``OPS .945``).
        new_value = f"{metric_jp} {value}"
        new_lines.append(f"{prefix} {name}（{team}）{new_value}{new_marker}")
    return new_lines


def _truncate_to_x_limit_top_n(text: str, top_n: int) -> str:
    """353: if ``text`` exceeds ``X_CHAR_LIMIT``, drop ranking rows
    beyond ``top_n`` while keeping header, blank separators, and the
    hashtag footer intact.

    Falls back to nothing if the trim is not enough — the caller's
    final ``[: X_CHAR_LIMIT - 1] + "…"`` safety net handles that.
    """
    lines = text.split("\n")
    kept: list[str] = []
    rank_seen = 0
    for line in lines:
        is_ranking = bool(_re.match(r"^\d+\.\s", line))
        if is_ranking:
            rank_seen += 1
            if rank_seen > top_n and "⭐巨人" not in line:
                continue  # drop rows beyond top_n
        kept.append(line)
    return "\n".join(kept)


def _angle_for_combo(combo: _MetricCombo) -> tuple[str, str]:
    """Return the visible brand angle for the mail card title.

    This is a deterministic label, not an LLM judgement. It only
    describes the already-selected data slice.
    """
    if combo.position:
        return ("🆚", "比較")
    if combo.metric in {"ERA", "K_per_9", "BB_per_9", "HR_per_9"}:
        return ("⚡", "投手")
    if combo.period_label in {"直近5試合", "直近10試合", "直近1週間", "今週"}:
        return ("📊", "短期変化")
    if combo.period_label.endswith("月成績") or combo.period_label == "今月":
        return ("🗓️", "月別メモ")
    return ("📌", "巨人データメモ")


def _stable_variant_index(combo: _MetricCombo, focus_name: str) -> int:
    seed = f"{combo.metric}|{combo.period_label}|{combo.position or ''}|{focus_name}"
    return sum(ord(ch) for ch in seed) % 3


def _finalize_post_text(body: str) -> str:
    text = body.strip()
    if len(text) <= X_CHAR_LIMIT:
        return text
    return text[: X_CHAR_LIMIT - 1].rstrip("、。 \n") + "…"


def _build_branded_post_text(
    combo: _MetricCombo,
    focus_row: dict,
    *,
    metric_jp: str,
    period_label: str,
    threshold_label: str,
    scope_label: str,
    rank: object,
    total: object,
    context_label: str = "",
) -> str:
    """Build the actual X post copy shown in the button.

    The copy is fact-locked: player, metric, rank, value, period and
    sample threshold come from the ranking row / combo only. The rest is
    generic framing, not baseball judgement.
    """
    focus_name = str(focus_row.get("player_canonical") or "巨人選手").strip()
    value = _format_metric_value(combo.metric, focus_row.get("metric_value"))
    rank_text = f"{scope_label} {rank}/{total}位"
    value_text = f"{metric_jp} {value}"
    _, angle = _angle_for_combo(combo)
    variant = _stable_variant_index(combo, focus_name)

    if context_label == "今日のスタメン":
        body = (
            "今日のスタメンから、数字を一つ。\n\n"
            f"{focus_name}は{period_label}の{metric_jp}で{rank_text}。\n"
            f"数字は{value_text}、{threshold_label}の条件です。\n\n"
            "試合前に見ておくと、打席や登板の見え方が少し変わる数字。\n\n"
            "この数字、どう見ますか？"
        )
    elif combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        body = (
            "同じ条件で並べると、見え方が変わる。\n\n"
            f"{focus_name}は{period_label}の{position_jp}{metric_jp}で{rank_text}。\n"
            f"数字は{value_text}、{threshold_label}の条件です。\n\n"
            "数字だけで決める話ではないけど、比較材料として一度拾っておきたい。\n\n"
            "どう見ますか？"
        )
    elif variant == 0:
        body = (
            "今日の巨人データメモ。\n\n"
            f"{focus_name}、{period_label}の{metric_jp}は{rank_text}。\n"
            f"数字は{value_text}、{threshold_label}の条件です。\n\n"
            "結果や印象だけでは流れやすいので、あとで見返したい数字。\n\n"
            "この数字、どう見ますか？"
        )
    elif variant == 1:
        body = (
            "直近だけで見ると、少し印象が変わる。\n\n"
            f"{focus_name}の{metric_jp}は{period_label}で{rank_text}。\n"
            f"{threshold_label}で見ると、{value_text}です。\n\n"
            "大きく騒ぐ話ではなくても、議論の材料にはなりそう。\n\n"
            "今の状態、どう見えてますか？"
        )
    else:
        body = (
            f"{angle}として拾っておきたい数字。\n\n"
            f"{focus_name}は{period_label}の{metric_jp}で{rank_text}。\n"
            f"{value_text}、{threshold_label}。\n\n"
            "数字だけで語り切る話ではないけど、一度見ておきたいところ。\n\n"
            "どう見ますか？"
        )
    return _finalize_post_text(body)


def _is_safe_post_text(text: str) -> bool:
    if not text.strip():
        return False
    return not any(term in text for term in _FORBIDDEN_POST_TERMS)


def _candidate_post_text(candidate: Candidate) -> str:
    return candidate.post_text or candidate.draft_text


def _candidate_char_count(candidate: Candidate) -> int:
    return len(_candidate_post_text(candidate))


# ---------------------------------------------------------------------------
# 355: 24h dedup (GCS-backed) — prevents the same combo signature from
# appearing repeatedly in mails sent within the past 24 hours.
# ---------------------------------------------------------------------------


def _combo_signature(combo: _MetricCombo) -> str:
    """355: combo identity for dedup. Same ``(metric, period_label,
    legacy ``giants_only`` flag, position)`` tuple == "same ranking" — minor differences
    like ``since`` drift across days do not count as a different
    ranking for user perception.
    """
    pos = combo.position or "None"
    return f"{combo.metric}|{combo.period_label}|{combo.giants_only}|{pos}"


def _period_family_key(combo: _MetricCombo) -> str:
    """Identity used to avoid sending multiple time windows of the same
    ranking in one mail.

    Example: OPS 直近5試合 / 直近10試合 / 直近7日 are distinct dedup
    signatures for 24h history, but they are the same user-facing
    ranking family inside a single mail. Keep only one per mail.
    """
    pos = combo.position or "None"
    return f"{combo.metric}|{combo.giants_only}|{pos}"


def _get_storage_client():
    """Lazy-imported GCS client builder. Wrapped as a module-level
    function so tests can patch it via
    :func:`unittest.mock.patch` without touching ``google.cloud``.
    """
    from google.cloud import storage  # noqa: WPS433
    return storage.Client()


def _dedup_blob_path(date_str: str) -> str:
    return f"x_post_mail/dedup/{date_str}.jsonl"


def _load_recent_dedup_records(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 24,
) -> list[dict]:
    """355: read JSONL files in ``gs://{bucket_name}/x_post_mail/dedup/``
    for today + yesterday and filter to records with ``ts >= now -
    lookback_hours``.

    Returns an empty list on any GCS error after logging the failure.
    The mail send must never block on dedup infrastructure problems.
    """
    if not bucket_name:
        return []
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_load_recent_dedup_records: client init failed: %r", exc)
        return []
    cutoff = now - timedelta(hours=lookback_hours)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    out: list[dict] = []
    for date_str in (today, yesterday):
        blob = bucket.blob(_dedup_blob_path(date_str))
        try:
            if not blob.exists():
                continue
            content = blob.download_as_text()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("_load_recent_dedup_records: read %s failed: %r",
                        date_str, exc)
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = _json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            ts_str = rec.get("ts") or ""
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if ts.tzinfo is None:
                # Treat naive timestamps as JST per project convention.
                ts = ts.replace(tzinfo=JST)
            if ts >= cutoff:
                out.append(rec)
    return out


def _load_recent_dedup_signatures(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 24,
) -> set[str]:
    """Return recent combo signatures from the GCS-backed dedup JSONL."""
    records = _load_recent_dedup_records(
        bucket_name,
        now,
        lookback_hours=lookback_hours,
    )
    return {
        str(rec.get("signature") or "")
        for rec in records
        if str(rec.get("signature") or "")
    }


def _player_counts_from_dedup_records(records: list[dict]) -> dict[str, int]:
    """Return normalized focus-player counts from recent dedup records."""
    counts: dict[str, int] = {}
    for rec in records:
        player_key = _normalize_player_name(rec.get("focus_player"))
        if not player_key:
            continue
        counts[player_key] = counts.get(player_key, 0) + 1
    return counts


def _load_recent_player_counts(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 24,
) -> dict[str, int]:
    """Return recent focus-player counts from the GCS-backed dedup JSONL."""
    records = _load_recent_dedup_records(
        bucket_name,
        now,
        lookback_hours=lookback_hours,
    )
    return _player_counts_from_dedup_records(records)


def _fan_voice_pool_blob_path(date_str: str) -> str:
    """397: GCS path for fan_voice_pool cache JSONL (per-day)."""
    return f"fan_voice/pool_{date_str}.jsonl"


def _coerce_struct_time_to_iso(value) -> str:
    """Convert feedparser ``published_parsed`` (``time.struct_time``) or any
    iso-able value into an ISO 8601 string. Returns ``""`` on best-effort
    failure (silent skip)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # feedparser published_parsed: time.struct_time
    try:
        import time as _time
        if hasattr(value, "tm_year"):
            return datetime.fromtimestamp(_time.mktime(value), tz=JST).isoformat()
    except Exception:  # noqa: BLE001
        return ""
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:  # noqa: BLE001
        return ""
    return str(value)


def record_fan_voice_pool_entries_to_gcs(
    bucket_name: str,
    now: datetime,
    entries: list[dict],
) -> bool:
    """397: Append in-process fan_voice_pool cache entries to today's
    GCS JSONL so x-post-mail-lane Job (separate process) can read them.

    Each input ``entry`` is the dict produced by
    ``rss_fetcher._record_fan_voice_pool_entries`` (keys: ``source_name``,
    ``handle``, ``text``, ``url``, ``created_at``).  Missing / unserializable
    fields are silently dropped from the record (best-effort).

    Returns ``True`` on upload success, ``False`` on any error. The caller
    must never abort on a GCS failure: fan_voice is a soft add-on.
    """
    if not entries or not bucket_name:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("record_fan_voice_pool_entries_to_gcs: client init failed: %r", exc)
        return False
    date_str = now.strftime("%Y-%m-%d")
    blob = bucket.blob(_fan_voice_pool_blob_path(date_str))
    if now.tzinfo is None:
        ts_iso = now.replace(tzinfo=JST).isoformat()
    else:
        ts_iso = now.isoformat()
    new_records: list[dict] = []
    seen_urls: set[str] = set()
    try:
        existing = blob.download_as_text() if blob.exists() else ""
    except Exception as exc:  # noqa: BLE001
        LOG.warning("record_fan_voice_pool_entries_to_gcs: read existing failed: %r", exc)
        existing = ""
    # gather already-recorded URLs to avoid duplicate appends across fetcher runs
    for line in existing.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        url = str(rec.get("url") or "")
        if url:
            seen_urls.add(url)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        text = str(entry.get("text") or "").strip()
        if not text or not url:
            continue
        if url in seen_urls:
            continue
        rec = {
            "ts": ts_iso,
            "source_name": str(entry.get("source_name") or ""),
            "handle": str(entry.get("handle") or ""),
            "text": text,
            "url": url,
            "pub_iso": _coerce_struct_time_to_iso(entry.get("created_at")),
        }
        new_records.append(rec)
        seen_urls.add(url)
    if not new_records:
        return True  # nothing new but not an error
    new_lines = [_json.dumps(rec, ensure_ascii=False) for rec in new_records]
    new_block = "\n".join(new_lines) + "\n"
    try:
        blob.upload_from_string(
            existing + new_block,
            content_type="application/x-jsonlines",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("record_fan_voice_pool_entries_to_gcs: upload failed: %r", exc)
        return False


def load_recent_fan_voice_pool_entries(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 24,
) -> list[dict]:
    """397: read recent fan_voice_pool entries from GCS for x-post-mail
    consumption. Returns an empty list on any GCS error (silent skip).

    Filter: returns records whose ``ts`` (upload time) falls within the
    last ``lookback_hours``. Caller can further filter by ``pub_iso``
    if it wants real-tweet recency (vs upload recency).
    """
    if not bucket_name:
        return []
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("load_recent_fan_voice_pool_entries: client init failed: %r", exc)
        return []
    cutoff = now - timedelta(hours=lookback_hours)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    out: list[dict] = []
    seen_urls: set[str] = set()
    for date_str in (today, yesterday):
        blob = bucket.blob(_fan_voice_pool_blob_path(date_str))
        try:
            if not blob.exists():
                continue
            content = blob.download_as_text()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("load_recent_fan_voice_pool_entries: read %s failed: %r",
                        date_str, exc)
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = _json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            ts_str = rec.get("ts") or ""
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=JST)
            if ts < cutoff:
                continue
            url = str(rec.get("url") or "")
            if url and url in seen_urls:
                continue
            out.append(rec)
            if url:
                seen_urls.add(url)
    return out


def _record_dedup_signatures(
    bucket_name: str,
    signatures: list[str],
    now: datetime,
    *,
    focus_players: Optional[list[str]] = None,
    metrics: Optional[list[str]] = None,
    period_labels: Optional[list[str]] = None,
) -> bool:
    """355: append signatures to today's JSONL on GCS. Returns ``True``
    on success, ``False`` on any error. Failures are logged and never
    abort the calling flow.

    GCS objects are immutable so we read + concat + re-upload. The
    Schedulers' staggered fire times (07/12/15/17:30/22:30 JST) keep
    write contention low; on manual co-fire there is a small race
    window but it would only drop one batch of signatures, not break
    the mail send.
    """
    if not signatures or not bucket_name:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_record_dedup_signatures: client init failed: %r", exc)
        return False
    date_str = now.strftime("%Y-%m-%d")
    blob = bucket.blob(_dedup_blob_path(date_str))
    if now.tzinfo is None:
        ts_iso = now.replace(tzinfo=JST).isoformat()
    else:
        ts_iso = now.isoformat()
    new_records: list[dict] = []
    for idx, signature in enumerate(signatures):
        rec = {"ts": ts_iso, "signature": signature}
        if focus_players is not None and idx < len(focus_players):
            player = str(focus_players[idx] or "").strip()
            if player:
                rec["focus_player"] = player
        if metrics is not None and idx < len(metrics):
            metric = str(metrics[idx] or "").strip()
            if metric:
                rec["metric"] = metric
        if period_labels is not None and idx < len(period_labels):
            period = str(period_labels[idx] or "").strip()
            if period:
                rec["period_label"] = period
        new_records.append(rec)
    new_lines = [_json.dumps(rec, ensure_ascii=False) for rec in new_records]
    new_block = "\n".join(new_lines) + "\n"
    try:
        existing = blob.download_as_text() if blob.exists() else ""
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_record_dedup_signatures: read existing failed: %r", exc)
        existing = ""
    try:
        blob.upload_from_string(
            existing + new_block,
            content_type="application/x-jsonlines",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_record_dedup_signatures: upload failed: %r", exc)
        return False


def _format_one(
    combo: _MetricCombo,
    rows: list[dict],
    *,
    min_sample: int,
    now: datetime,
    focus_player_names: Optional[set[str]] = None,
    avoid_player_names: Optional[set[str]] = None,
    context_label: str = "",
) -> Optional[Candidate]:
    focus_row = _top_giants_row(
        rows,
        focus_player_names=focus_player_names,
        avoid_player_names=avoid_player_names,
    )
    if focus_row is None:
        LOG.info("No Giants row for %s/%s — skip", combo.metric, combo.period_label)
        return None
    display_rows = _rows_with_giants_focus(rows, max_rows=10, focus_row=focus_row)
    parsed = {
        "metric": combo.metric,
        "position": None,
        "top_n": min(10, len(display_rows)),
        "league": "セ",
        "focus_player": None,
    }
    rank_result = {
        "ok": True,
        "rows": display_rows,
        "count": len(display_rows),
        "total": len(rows),
        "focus_player": None,
    }
    formatted = _format_as_x_post(parsed, rank_result, top_n=10)
    if not formatted.get("ok"):
        LOG.warning("format_as_x_post failed for %s (%s): %s",
                    combo.metric, combo.period_label, formatted.get("reason"))
        return None
    # 350+351+353+357: header に 人間が読める period label + 規定 sample
    # 閾値 + 状況 slice を明示。日付範囲だけの表示は避ける。
    # 353: header 絵文字は metric 別 (⚾打撃 / ⚡投手 / 🛡️守備、 fallback 📊)、
    # period_suffix は header line[0] には連結せず line[1] に挿入する。
    text = formatted["draft_text"]
    lines = text.split("\n")
    period_label = _format_period_label(combo, now)
    threshold_label = _sample_threshold_label(combo.metric, min_sample)
    period_suffix = f"（{period_label}・{threshold_label}）"
    metric_jp = _METRIC_LABELS_JP.get(combo.metric, combo.metric)
    header_emoji = _METRIC_HEADER_EMOJI.get(combo.metric, "📊")
    focus_rank = focus_row.get("rank")
    focus_total = focus_row.get("total") or len(rows)
    focus_name = focus_row.get("player_canonical") or "巨人選手"
    scope_label = _scope_label(combo)
    fact_metric_label = metric_jp

    # 351+353 follow-up: 守備位置別 / セ・リーグ ranking で header の prefix を切替。
    # 346 format_as_x_post の output 1 行目は「セ・{metric_jp} ランキング 📊」固定
    # なので、 1 行目を新 prefix + metric 別絵文字で置換する。
    if combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        fact_metric_label = f"{position_jp}{metric_jp}"
        if lines and "ランキング" in lines[0]:
            lines[0] = f"セ・{position_jp} {metric_jp} ランキング {header_emoji}"
    else:
        if lines and "ランキング" in lines[0]:
            lines[0] = f"セ・リーグ {metric_jp} ランキング {header_emoji}"
    context_prefix = f"{context_label} " if context_label else ""
    title = (
        f"{_angle_for_combo(combo)[0]} Xポスト案｜"
        f"{context_prefix}{focus_name} {metric_jp} {scope_label} {focus_rank}/{focus_total}位 "
        f"({period_label}・{threshold_label})"
    )
    # 353: period_suffix を 1 行目 append から 2 行目挿入に変更。
    lines.insert(1, period_suffix)
    focus_line_prefix = context_label or "巨人最上位"
    lines.insert(2, f"{focus_line_prefix}: {focus_name} {scope_label} {focus_rank}/{focus_total}位")

    # 353: ranking rows に medal / metric label / strong Giants marker を post-process。
    lines = _rewrite_ranking_rows(lines, metric_jp)

    draft_text = "\n".join(lines)
    # 353: 280 字 cap を超えたら top 5 まで cut (rows-only trim)、 それでも
    # 超過なら最終手段として末尾 truncation + … で安全網。
    if len(draft_text) > X_CHAR_LIMIT:
        draft_text = _truncate_to_x_limit_top_n(draft_text, top_n=5)
        if len(draft_text) > X_CHAR_LIMIT:
            draft_text = draft_text[: X_CHAR_LIMIT - 1] + "…"
    post_text = _build_branded_post_text(
        combo,
        focus_row,
        metric_jp=metric_jp,
        period_label=period_label,
        threshold_label=threshold_label,
        scope_label=scope_label,
        rank=focus_rank,
        total=focus_total,
        context_label=context_label,
    )
    if not _is_safe_post_text(post_text):
        LOG.warning(
            "unsafe branded X post text skipped for %s/%s",
            combo.metric,
            combo.period_label,
        )
        post_text = ""
    value_text = f"{metric_jp} {_format_metric_value(combo.metric, focus_row.get('metric_value'))}"
    db_fact_line = (
        f"{focus_name}は{period_label}の{fact_metric_label}で"
        f"{scope_label} {focus_rank}/{focus_total}位"
        f"（{value_text}、{threshold_label}）"
    )
    return Candidate(
        title=title,
        metric=combo.metric,
        period_label=combo.period_label,
        draft_text=draft_text,
        char_count=len(post_text or draft_text),
        signature=_combo_signature(combo),
        post_text=post_text,
        context_label=context_label,
        focus_player=str(focus_name or ""),
        db_fact_line=db_fact_line,
    )


def pick_candidates(
    query_rank_fn: Callable[..., dict],
    *,
    now: Optional[datetime] = None,
    max_candidates: int = 10,
    min_sample: int = 30,
    min_central_rows: int = 5,
    db_path: Optional[str] = None,
    dedup_set: Optional[set[str]] = None,
    focus_player_names: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    context_label: str = "",
    max_per_player: int = _DEFAULT_PLAYER_MAX_PER_MAIL,
    recent_player_counts: Optional[dict[str, int]] = None,
) -> list[Candidate]:
    """Build up to ``max_candidates`` セ-only X post candidates.

    Parameters
    ----------
    query_rank_fn:
        Callable matching :func:`src.manual_intake_insight_query.query_rank`
        (kwargs: ``metric_name``, ``since``, ``until``, ``min_sample``,
        ``limit``). Injected for test mocking; production passes the
        real ``miq.query_rank``.
    now:
        Reference timestamp. Defaults to ``datetime.now(JST)``.
    min_sample:
        Minimum AB/IP/opps sample to count for rank — keeps trivial
        small samples out. Combos with ``min_sample_override`` set
        (354: 直近 5/10 試合) bypass this default.
    min_central_rows:
        Minimum number of セ teams that must appear in a query result
        for the candidate to be emitted. If fewer than this number of
        セ rows show up, that combo is skipped (silent fallback to the
        next combo).
    db_path:
        354: optional path to a read-only ``insight.db`` SQLite file.
        When provided and the table has ≥10 distinct game dates,
        adds 直近 5 試合 / 直近 10 試合 × OPS/AVG/ERA
        combos (6 combos). ``None`` keeps the base 10-combo pool.
    dedup_set:
        355: optional set of combo signatures already sent within
        the past 24 hours. Combos whose signature is present are
        skipped during selection. ``None`` (default) disables the
        dedup gate (legacy behaviour).
    focus_player_names:
        Optional player-name gate, normally today's Giants lineup. When
        provided, a candidate is emitted only if the highest available
        Giants row for that ranking belongs to one of these players.
    max_per_player:
        380: upper bound for the same focused player inside one mail.
        Distinct players are preferred first; duplicates are kept only
        as a fallback so the mail does not disappear.
    recent_player_counts:
        380 follow-up: normalized focus-player counts from recent
        mails. Players that already appeared in the lookback window are
        avoided before news/opinion fallback is needed.
    """
    if now is None:
        now = datetime.now(JST)
    player_cap = max(1, int(max_per_player or _DEFAULT_PLAYER_MAX_PER_MAIL))
    out: list[Candidate] = []
    used_player_counts: dict[str, int] = {}
    history_player_counts = {
        _normalize_player_name(name): int(count or 0)
        for name, count in (recent_player_counts or {}).items()
        if _normalize_player_name(name) and int(count or 0) > 0
    }
    history_avoid_names = set(history_player_counts)
    focus_names = normalize_focus_player_names(focus_player_names)
    focus_input_count = len(
        {
            _normalize_player_name(name)
            for name in (focus_player_names or [])
            if _normalize_player_name(name)
        }
    )
    used_focus_player_keys: set[str] = set()
    repeat_backlog: list[tuple[str, Candidate]] = []
    repeat_backlog_families: set[str] = set()
    # 351+354: shuffle the combo pool with a (date, hour) seed so each
    # trigger picks a different variety slice while staying reproducible
    # inside a single run. 354 adds 直近 N 試合 combos when db_path given.
    combos = _build_combos(now, db_path=db_path)
    shuffled = _select_with_diversity(
        combos,
        max_candidates=len(combos),
        now=now,
    )
    seen_period_families: set[str] = set()
    for combo in shuffled:
        if len(out) >= max_candidates:
            break
        # 355: skip combo if its signature appears in recent 24h dedup
        # set. Logged at INFO so production observability sees why a
        # combo went unused.
        signature = _combo_signature(combo)
        if dedup_set is not None and signature in dedup_set:
            LOG.info("dedup skip combo %s/%s (signature=%s)",
                     combo.metric, combo.period_label, signature)
            continue
        family_key = _period_family_key(combo)
        if family_key in seen_period_families:
            LOG.info("period-family skip combo %s/%s (family=%s)",
                     combo.metric, combo.period_label, family_key)
            continue
        effective_min_sample = (
            combo.min_sample_override
            if combo.min_sample_override is not None
            else min_sample
        )
        # 2026-05-17 dispatch: batting metrics without position are
        # answered by the snapshot table (correct OPS/OBP/SLG values).
        # 2026-05-20: 投手 metric (ERA / K_per_9 / BB_per_9 / HR_per_9) も
        # snapshot 経由 per-player rolling で扱う (直近 N 試合 が starter
        # 1 登板に依存しない正しい値になる)。 守備位置別 (position != None)
        # は snapshot に position 列が無いので legacy path 維持。
        use_snapshot = (
            db_path is not None
            and combo.metric in _SNAPSHOT_METRICS
            and combo.position is None
            and combo.period_label in _PERIOD_LABEL_TO_SNAPSHOT_SCOPE
        )
        try:
            if use_snapshot:
                snapshot_scope = _PERIOD_LABEL_TO_SNAPSHOT_SCOPE[combo.period_label]
                result = _query_rank_from_snapshots(
                    db_path,
                    metric_name=combo.metric,
                    snapshot_scope=snapshot_scope,
                    min_sample=effective_min_sample,
                    limit=60,
                )
            else:
                result = query_rank_fn(
                    metric_name=combo.metric,
                    since=combo.since,
                    until=combo.until,
                    position_filter=combo.position,
                    min_sample=effective_min_sample,
                    limit=60,  # enough to capture all 12 teams' top players
                )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("query_rank failed for %s/%s: %r",
                        combo.metric, combo.period_label, exc)
            continue
        if not result.get("ok"):
            LOG.info("query_rank not ok for %s/%s: %s",
                     combo.metric, combo.period_label, result.get("reason"))
            continue
        rows = filter_central_league(result.get("rows") or [])
        # 414 axis C8 (2026-05-20): 巨人 rows のうち 1軍 active でない player を排除
        # (user 報告 「山瀬 (2軍中心) が 1軍 ranking に出る」 fix)。 直近 14 日で 3 試合
        # 未満出場の player は filter out。 db_path 不在 / 例外時は silent fallback で
        # filter で消さない (既存挙動維持)。
        if db_path:
            try:
                from src.analysis.active_roster_filter import is_first_team_active
                _active_filtered: list[dict] = []
                for _r in rows:
                    _team_name = str(_r.get("team_name") or "").strip()
                    _player = str(_r.get("player_canonical") or "").strip()
                    if _team_name == "巨人" and _player:
                        if not is_first_team_active(_player, db_path, now_jst=now):
                            LOG.info(
                                "active_roster_filter_skip player=%s metric=%s period=%s",
                                _player, combo.metric, combo.period_label,
                            )
                            continue
                    _active_filtered.append(_r)
                rows = _active_filtered
            except Exception as _exc:  # noqa: BLE001
                LOG.info("active_roster_filter_skip_exception err=%r", _exc)
        min_rows_required = min_central_rows
        if len(rows) < min_rows_required:
            LOG.info("Too few rows (%d < %d) for %s/%s (position=%s) — skip",
                     len(rows), min_rows_required, combo.metric,
                     combo.period_label, combo.position)
            continue
        rows = _rebuild_ranks_within_central(rows)
        diversity_avoid_names = set(used_player_counts) | history_avoid_names
        focus_avoid_names = (
            used_focus_player_keys
            if focus_names and len(used_focus_player_keys) < focus_input_count
            else set()
        )
        avoid_names = diversity_avoid_names | focus_avoid_names
        top_without_avoid = _top_giants_row(
            rows,
            focus_player_names=focus_names,
        )
        top_with_avoid = _top_giants_row(
            rows,
            focus_player_names=focus_names,
            avoid_player_names=avoid_names,
        )
        if top_with_avoid is None:
            top_player_key = (
                _normalize_player_name(top_without_avoid.get("player_canonical"))
                if top_without_avoid
                else ""
            )
            if top_player_key and top_player_key in history_avoid_names:
                LOG.info(
                    "player_history_skip metric=%s period=%s player=%s "
                    "previous_count=%d reason=no_alternative",
                    combo.metric,
                    combo.period_label,
                    top_without_avoid.get("player_canonical"),
                    history_player_counts.get(top_player_key, 0),
                )
            else:
                LOG.info("No Giants row in central ranking for %s/%s (position=%s) — skip",
                         combo.metric, combo.period_label, combo.position)
            continue
        candidate = _format_one(
            combo,
            rows,
            min_sample=effective_min_sample,
            now=now,
            focus_player_names=focus_names,
            avoid_player_names=avoid_names,
            context_label=context_label if focus_names else "",
        )
        if candidate:
            focus_player_key = _normalize_player_name(candidate.focus_player)
            is_focus_repeat = (
                bool(focus_names)
                and bool(focus_player_key)
                and focus_player_key in used_focus_player_keys
                and len(used_focus_player_keys) < focus_input_count
            )
            player_count = (
                used_player_counts.get(focus_player_key, 0)
                if focus_player_key
                else 0
            )
            is_player_repeat = bool(focus_player_key) and player_count > 0
            top_player_key = (
                _normalize_player_name(top_without_avoid.get("player_canonical"))
                if top_without_avoid
                else ""
            )
            if (
                focus_player_key
                and top_player_key
                and focus_player_key != top_player_key
                and top_player_key in diversity_avoid_names
            ):
                if top_player_key in history_avoid_names:
                    LOG.info(
                        "player_history_alternate_selected metric=%s period=%s "
                        "skipped_player=%s previous_count=%d selected_player=%s",
                        combo.metric,
                        combo.period_label,
                        top_without_avoid.get("player_canonical"),
                        history_player_counts.get(top_player_key, 0),
                        candidate.focus_player,
                    )
                LOG.info(
                    "player_diversity_alternate_selected metric=%s period=%s "
                    "skipped_player=%s selected_player=%s",
                    combo.metric,
                    combo.period_label,
                    top_without_avoid.get("player_canonical"),
                    candidate.focus_player,
                )
            if is_focus_repeat or is_player_repeat:
                if focus_player_key and player_count >= player_cap:
                    LOG.info(
                        "player_diversity_cap_skip metric=%s period=%s "
                        "player=%s count=%d cap=%d",
                        combo.metric,
                        combo.period_label,
                        candidate.focus_player,
                        player_count,
                        player_cap,
                    )
                    continue
                if family_key not in repeat_backlog_families:
                    repeat_backlog.append((family_key, candidate))
                    repeat_backlog_families.add(family_key)
                continue
            out.append(candidate)
            seen_period_families.add(family_key)
            if focus_player_key:
                used_player_counts[focus_player_key] = player_count + 1
                used_focus_player_keys.add(focus_player_key)
    for family_key, candidate in repeat_backlog:
        if len(out) >= max_candidates:
            break
        if family_key in seen_period_families:
            continue
        focus_player_key = _normalize_player_name(candidate.focus_player)
        player_count = (
            used_player_counts.get(focus_player_key, 0)
            if focus_player_key
            else 0
        )
        if focus_player_key and player_count >= player_cap:
            LOG.info(
                "player_diversity_backlog_cap_skip metric=%s period=%s "
                "player=%s count=%d cap=%d",
                candidate.metric,
                candidate.period_label,
                candidate.focus_player,
                player_count,
                player_cap,
            )
            continue
        if focus_player_key:
            LOG.info(
                "player_diversity_duplicate_fallback metric=%s period=%s "
                "player=%s count_before=%d cap=%d",
                candidate.metric,
                candidate.period_label,
                candidate.focus_player,
                player_count,
                player_cap,
            )
        out.append(candidate)
        seen_period_families.add(family_key)
        if focus_player_key:
            used_player_counts[focus_player_key] = player_count + 1
            used_focus_player_keys.add(focus_player_key)
    return out[:max_candidates]


# ---------------------------------------------------------------------------
# X intent URL encoding
# ---------------------------------------------------------------------------


def encode_x_intent_url(text: str) -> str:
    """Return an X Web Intent URL with ``text`` percent-encoded.

    The Web Intent spec accepts both ``%0A`` for newlines and `+` for
    spaces. We use :func:`urllib.parse.quote` with ``safe=""`` so every
    non-RFC3986-unreserved char gets encoded — including `#` (which
    would otherwise be parsed as a fragment) and `&` (which would
    truncate query parameters).

    ``&url=https://yoshilover.com/`` is appended unconditionally. Other
    mail lanes (publish_notice / publish_button_handler) include this
    parameter and reliably route X composer to @yoshilover6760; this
    lane historically omitted it and intermittently opened composer
    under the user's other personal X account.
    """
    encoded = _url_quote(text or "", safe="")
    site_url = _url_quote("https://yoshilover.com/", safe="")
    return f"{_X_INTENT_URL_BASE}?text={encoded}&url={site_url}"


# ---------------------------------------------------------------------------
# Mail composition
# ---------------------------------------------------------------------------


def time_band_label(hour: int) -> str:
    for hr_range, label in _TIME_BANDS:
        if hour in hr_range:
            return label
    return "夜"  # fall-through (should not happen with TIME_BANDS coverage)


def build_subject(
    now: datetime,
    n_candidates: int,
    *,
    context_label: str = "",
) -> str:
    band = time_band_label(now.hour)
    band_emoji = _TIME_BAND_EMOJI.get(band, "")
    purpose = context_label or _TIME_BAND_PURPOSE.get(band, "Xポスト案")
    return (
        f"🟠🐦📮【Xポスト案 {n_candidates}件】"
        f"{band_emoji}{band}｜{purpose} {now.strftime('%H:%M')} JST"
    )


def _has_news_opinion_candidate(candidates: list[Candidate]) -> bool:
    return any(c.metric in {_NEWS_OPINION_METRIC, _COMMENT_DB_METRIC} for c in candidates)


def _mail_header_label(candidates: list[Candidate]) -> str:
    if _has_news_opinion_candidate(candidates):
        return "巨人Xポスト案"
    return "巨人データXポスト案"


def _compose_text_body(
    candidates: list[Candidate],
    now: datetime,
    *,
    context_note: str = "",
) -> str:
    band = time_band_label(now.hour)
    header_label = _mail_header_label(candidates)
    parts = [
        f"📮 {header_label} — {band} / {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "公開通知ではありません。X に手動投稿するための候補メールです。",
        "各候補のテキストをコピーして X アプリに貼り付けて投稿してください。",
        "(HTML mail を表示できる client なら 🐦 ボタンで X アプリが直接開きます)",
        "",
    ]
    if context_note:
        parts.extend([context_note, ""])
    for idx, cand in enumerate(candidates, start=1):
        post_text = _candidate_post_text(cand)
        parts.append("━" * 40)
        parts.append(f"■ 候補 {idx}: {cand.title}")
        parts.append("━" * 40)
        parts.append("")
        parts.append(post_text)
        parts.append("")
        parts.append(f"【文字数】{_candidate_char_count(cand)} / {X_CHAR_LIMIT}")
        if cand.post_text and cand.draft_text and cand.post_text != cand.draft_text:
            parts.append("")
            parts.append("【根拠データ】")
            parts.append(cand.draft_text)
        parts.append("")
        parts.append("🐦 X 投稿 URL:")
        parts.append(encode_x_intent_url(post_text))
        parts.append("")
    return "\n".join(parts)


def _compose_html_body(
    candidates: list[Candidate],
    now: datetime,
    *,
    context_note: str = "",
) -> str:
    band = time_band_label(now.hour)
    header_label = _mail_header_label(candidates)
    rows_html: list[str] = []
    for idx, cand in enumerate(candidates, start=1):
        post_text = _candidate_post_text(cand)
        intent_url = encode_x_intent_url(post_text)
        char_count = _candidate_char_count(cand)
        over = char_count > X_CHAR_LIMIT
        counter_color = "#b71c1c" if over else "#666"
        counter_suffix = " ⚠️ 超過" if over else ""
        proof_html = ""
        if cand.post_text and cand.draft_text and cand.post_text != cand.draft_text:
            proof_html = (
                "<details style=\"margin-top:8px;font-size:12px;color:#444;\">"
                "<summary style=\"cursor:pointer;\">根拠データを開く</summary>"
                "<pre style=\"white-space:pre-wrap;word-break:keep-all;"
                "font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',"
                "'Yu Gothic',monospace;font-size:12px;line-height:1.45;"
                "background:#fffef7;padding:8px;border:1px solid #eadca6;"
                f"border-radius:4px;margin:6px 0 0;\">{_html.escape(cand.draft_text)}</pre>"
                "</details>"
            )
        rows_html.append(
            "<div style=\"border-left:3px solid #f57f17;"
            "padding:10px 14px;margin:14px 0;background:#fff8e1;"
            "border-radius:4px;\">"
            f"<div style=\"font-weight:600;font-size:14px;color:#5d4037;"
            f"margin:0 0 8px;\">■ 候補 {idx}: {_html.escape(cand.title)}</div>"
            "<pre style=\"white-space:pre-wrap;word-break:keep-all;"
            "font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',"
            "'Yu Gothic',monospace;font-size:13px;line-height:1.5;"
            "background:#fff;padding:10px;border:1px solid #ddd;"
            f"border-radius:4px;margin:0;\">{_html.escape(post_text)}</pre>"
            f"{proof_html}"
            "<div style=\"display:flex;gap:10px;align-items:center;"
            "margin-top:8px;flex-wrap:wrap;\">"
            f"<a href=\"{_html.escape(intent_url)}\" "
            "style=\"display:inline-block;padding:8px 14px;background:#000;"
            "color:#fff;text-decoration:none;border-radius:6px;font-size:13px;"
            "font-weight:600;\">🐦 X で投稿</a>"
            f"<div style=\"font-size:11px;color:{counter_color};\">"
            f"{char_count} / {X_CHAR_LIMIT} 字{counter_suffix}</div>"
            "</div>"
            "</div>"
        )
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\"><head><meta charset=\"utf-8\">"
        f"<title>{_html.escape(header_label)}</title></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,"
        "'Hiragino Sans','Yu Gothic',sans-serif;color:#222;"
        "max-width:680px;margin:0 auto;padding:18px;\">"
        f"<h2 style=\"font-size:17px;margin:0 0 8px;\">📮 {_html.escape(header_label)} — {band} / "
        f"{now.strftime('%Y-%m-%d %H:%M')} JST</h2>"
        "<p style=\"font-size:13px;color:#555;margin:0 0 14px;\">"
        "公開通知ではなく、X に手動投稿するための候補メールです。"
        "各候補の <strong>🐦 X で投稿</strong> ボタンを押すと X アプリ "
        "(または x.com) が本文プリフィル済で開きます。タップして "
        "「ポスト」だけ押せば投稿完了です。テキスト編集も可能。</p>"
        + (
            "<p style=\"font-size:12px;color:#5d4037;background:#fff8e1;"
            "border-left:3px solid #f57f17;padding:8px 10px;margin:0 0 12px;\">"
            f"{_html.escape(context_note)}</p>"
            if context_note else ""
        )
        + "\n".join(rows_html)
        + "</body></html>"
    )


@dataclass(frozen=True)
class ComposedMail:
    subject: str
    text_body: str
    html_body: str
    candidate_count: int


def compose_mail(
    candidates: list[Candidate],
    *,
    now: Optional[datetime] = None,
    context_label: str = "",
    context_note: str = "",
) -> ComposedMail:
    if now is None:
        now = datetime.now(JST)
    if not context_label and _has_news_opinion_candidate(candidates):
        context_label = "データ+ニュース意見"
    subject = build_subject(now, len(candidates), context_label=context_label)
    text_body = _compose_text_body(candidates, now, context_note=context_note)
    html_body = _compose_html_body(candidates, now, context_note=context_note)
    return ComposedMail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        candidate_count=len(candidates),
    )
