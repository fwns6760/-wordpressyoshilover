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
import os
from pathlib import Path as _Path
import random as _random
import re as _re
import sqlite3 as _sqlite3
from dataclasses import dataclass, field, replace
from datetime import date as _date, datetime, timedelta, timezone as _tz
from typing import Callable, Optional, Sequence
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

# 2026-06-10 鮮度ゲート: snapshot の 直近 N 試合 scope は **選手ごとの
# rolling** (本人の最後の N 試合) なので、 離脱中の選手は怪我前の古い
# 試合がいつまでも「直近」として ranking に載り続ける (平山功太 6/10
# 事例: 長期離脱中なのに OBP 直近10試合 Top10 に選出)。 最終出場が
# snapshot 日から下記日数より古い選手は X 向け ranking から除外する。
# 投手は先発間隔 (中 6 日 + 雨天順延) を考慮して打者より長め。
_SNAPSHOT_STALE_DAYS_BATTING = 10
_SNAPSHOT_STALE_DAYS_PITCHING = 14

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
    # 2026-07-06 実事故 (笹原操希 6/25 支配下昇格が静的 json 未反映 → alias 不在
    # → 記事内「中日金丸」の「丸」で丸佳浩を誤検出): 既定 path の時は NPB live
    # fetch つき loader (JSON fallback 内蔵) を正とし、roster の鮮度切れを防ぐ。
    roster = None
    if roster_path == _ROSTER_PATH:
        try:
            from src.giants_roster_loader import load_active_roster

            roster = load_active_roster() or None
        except Exception as exc:  # noqa: BLE001 - 静的 json fallback へ
            LOG.warning("giants roster live load failed (player aliases): %r", exc)
    if roster is None:
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
        if row.get("role") not in {"player", "shihaikako", "ikusei"}:
            # shihaikako/ikusei = NPB live 由来 label (2026-07-06 笹原操希 昇格漏れ対策)。
            # 手キュレーション json は育成も "player" 扱いで検出対象 (2026-06-01 拡張)。
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


# 2026-05-27: ヨシラバー風コメント (GEMMA_BRANDING) X-post 候補 gate を player
# だけでなく manager / coach にも開放するための member 版 loader。
# user 明示「監督やコーチもいれていいんだよ。 巨人なら」 2026-05-27。
# lineup focus 系 (試合 lineup matching) は player 限定のままにするため、
# _load_giants_player_aliases / _active_giants_canonical_player_keys には
# 触らず、 別関数として並列に置く。
def _load_giants_member_aliases(
    roster_path: _Path = _ROSTER_PATH,
) -> dict[str, str]:
    """Return normalized active Giants member aliases -> canonical name.

    Member = active roster の player + manager + coach。 ikusei (育成) /
    shihaikako (支配下) は除外 (ヨシラバー voice 候補は支配下登録選手 + コーチ陣
    に限定するため)。
    """
    roster = None
    if roster_path == _ROSTER_PATH:
        try:
            from src.giants_roster_loader import load_active_roster

            roster = load_active_roster() or None
        except Exception as exc:  # noqa: BLE001 - 静的 json fallback へ
            LOG.warning("giants roster live load failed (member aliases): %r", exc)
    if roster is None:
        if not roster_path.exists():
            return {}
        try:
            roster = _json.loads(roster_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("failed to load Giants roster aliases (member): %r", exc)
            return {}

    out: dict[str, str] = {}
    for row in roster:
        if not row.get("active"):
            continue
        if row.get("role") not in {"player", "shihaikako", "ikusei", "manager", "coach"}:
            continue
        canonical = str(row.get("name") or "").strip()
        if not canonical:
            continue
        aliases = [canonical, *(row.get("aliases") or [])]
        for alias in aliases:
            key = _normalize_player_name(alias)
            if key:
                out.setdefault(key, canonical)
    return out


def _load_giants_member_roles(
    roster_path: _Path = _ROSTER_PATH,
) -> dict[str, str]:
    """Return active Giants member canonical name -> role (player / manager / coach).

    見出し主役選定で「選手 > コーチ/監督」の役割優先付けに使う。 対象は
    `_load_giants_member_aliases` と同じ active な player + manager + coach。
    """
    if not roster_path.exists():
        return {}
    try:
        roster = _json.loads(roster_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("failed to load Giants roster roles (member): %r", exc)
        return {}

    out: dict[str, str] = {}
    for row in roster:
        if not row.get("active"):
            continue
        role = row.get("role")
        if role in {"shihaikako", "ikusei"}:
            role = "player"
        if role not in {"player", "manager", "coach"}:
            continue
        canonical = str(row.get("name") or "").strip()
        if canonical:
            out[canonical] = role
    return out


def _active_giants_canonical_member_keys() -> set[str]:
    return {
        _normalize_player_name(canonical)
        for canonical in _load_giants_member_aliases().values()
        if _normalize_player_name(canonical)
    }


def _is_verified_full_giants_member_name(member_name: object) -> bool:
    key = _normalize_player_name(member_name)
    if not key:
        return False
    canonical_keys = _active_giants_canonical_member_keys()
    if canonical_keys:
        return key in canonical_keys
    return len(key) >= 3


def _prepend_focus_player_tag(text: str, player: str) -> str:
    """投稿本文の先頭に 【選手名】 + 空行 を付ける (例: 【石塚裕惺】\\n\\n本文)。

    safety / 品質ゲートを通過した最終 text に対して呼ぶ (ゲート判定には影響させない)。
    branding 投稿 (x_post_branding_gen) と data 投稿 (_format_one) で共用。
    そのまま返す (タグを付けない) 条件:
    - player が空 / 「巨人選手」「(roundup)」 等の非単一選手 / 巨人 roster 未検証
    - text が既に 【player】 か player「 / player『 で始まる (Pattern B 等、 名前重複回避)
    - タグ付与で X 文字数上限 (X_CHAR_LIMIT) を超える
    """
    body = (text or "").strip()
    who = (player or "").strip()
    if not body or not who:
        return body
    if not _is_verified_full_giants_member_name(who):
        return body
    if body.startswith(f"【{who}】") or body.startswith(f"{who}「") or body.startswith(f"{who}『"):
        return body
    tagged = f"【{who}】\n\n{body}"
    if len(tagged) > X_CHAR_LIMIT:
        return body
    return tagged


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


def _snapshot_last_game_dates(conn: "_sqlite3.Connection") -> dict[str, str]:
    """player_canonical (空白除去) → 最終出場 game_date の map。

    batting_logs / pitching_logs の両方を見る。 logs table が無い古い
    DB やテスト fixture では空 dict を返し、 呼び出し側は鮮度ゲートを
    skip する (fail-open: 除外は確実に古いと分かる選手だけ)。
    """
    sql = (
        "SELECT REPLACE(player_canonical, ' ', '') AS pkey, MAX(game_date) "
        "FROM ( "
        "  SELECT b.player_canonical AS player_canonical, g.game_date AS game_date "
        "  FROM batting_logs b JOIN games g ON b.game_id = g.game_id "
        "  UNION ALL "
        "  SELECT p.player_canonical, g.game_date "
        "  FROM pitching_logs p JOIN games g ON p.game_id = g.game_id "
        ") GROUP BY pkey"
    )
    try:
        return {
            str(r[0]): str(r[1] or "")[:10]
            for r in conn.execute(sql).fetchall()
            if r[0] and r[1]
        }
    except _sqlite3.Error as exc:  # noqa: BLE001
        LOG.warning("_snapshot_last_game_dates: query failed: %r", exc)
        return {}


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
        snap_row = conn.execute(
            "SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
            "WHERE metric_name = ? AND scope = ?",
            (metric_name, snapshot_scope),
        ).fetchone()
        snapshot_date = str(snap_row[0])[:10] if snap_row and snap_row[0] else None
        last_game_map = _snapshot_last_game_dates(conn) if rows else {}
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
    # 2026-06-10 鮮度ゲート: 直近 N 試合 scope は per-player rolling のため
    # 離脱中の選手も snapshot に残る。 最終出場が snapshot 日から規定日数
    # より古い選手は X 向け Top10 から除外する (最終出場が不明な選手は
    # 誤除外を避けるため残す)。
    if snapshot_date and last_game_map:
        stale_days = (
            _SNAPSHOT_STALE_DAYS_PITCHING
            if _kind == "pitching"
            else _SNAPSHOT_STALE_DAYS_BATTING
        )
        try:
            cutoff = (
                _date.fromisoformat(snapshot_date) - timedelta(days=stale_days)
            ).isoformat()
        except ValueError:
            cutoff = None
        if cutoff:
            fresh_rows = []
            for r in rows:
                pkey = str(r[0] or "").replace(" ", "")
                last_d = last_game_map.get(pkey)
                if last_d and last_d < cutoff:
                    LOG.info(
                        "snapshot_rank_stale_drop metric=%s scope=%s player=%s "
                        "last_game=%s cutoff=%s",
                        metric_name, snapshot_scope, r[0], last_d, cutoff,
                    )
                    continue
                fresh_rows.append(r)
            rows = fresh_rows
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

_FAN_USEFUL_METRIC_WEIGHTS: dict[str, float] = {
    "OPS": 1.25,
    "OBP": 1.15,
    "SLG": 1.12,
    "AVG": 1.05,
    "ERA": 1.18,
    "K_per_9": 1.12,
    "BB_per_9": 1.08,
    "HR_per_9": 1.04,
}


def _combo_fan_usefulness_weight(combo: _MetricCombo) -> float:
    """Deterministic usefulness score for Source B candidate ordering.

    It is intentionally cheap and local: no LLM, no web, no extra DB
    query. The score only changes how equal novelty combos are ordered.
    """
    weight = _FAN_USEFUL_METRIC_WEIGHTS.get(combo.metric, 1.0)
    if combo.period_label in {"直近3試合", "直近5試合", "直近10試合", "直近20試合"}:
        weight *= 1.16
    elif combo.period_label in {"直近1週間", "今週"}:
        weight *= 1.10
    elif combo.period_label == "今月" or combo.period_label.endswith("月成績"):
        weight *= 1.02
    if combo.position:
        weight *= 1.05
    return max(weight, 0.1)


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
        weight = (
            _NOVELTY_WEIGHTS.get(combo.novelty, _NOVELTY_WEIGHTS["mid"])
            * _combo_fan_usefulness_weight(combo)
        )
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
    # 436: DB Top10 candidate metadata. These are deliberately optional
    # so older tests / callers that construct Candidate directly keep
    # working. Selection logic fills them when the DB row exposes facts.
    team_level: str = ""
    sample_size: int = 0
    sample_label: str = ""
    reason_tags: tuple[str, ...] = ()
    selected_reason: str = ""
    # X impression policy metadata. ``why_now`` is shown in the mail so
    # the operator can decide quickly whether this candidate fits the
    # current posting window. ``dedup_reason`` is mostly for tests/logging;
    # dropped candidates are not rendered in the mail.
    why_now: str = ""
    dedup_reason: str = ""
    # 451 (2026-06-01): 引用RT 候補 (x_buzz_post) の元ツイート URL。 空でなければ HTML mail の
    # X 投稿ボタンを quote intent (text=コメント&url=元ツイート) にして引用RTで開く (半自動)。
    quote_url: str = ""
    # 451 (2026-06-01): リプライ候補の対象 tweet id。 空でなければ HTML mail のボタンを
    # reply intent (in_reply_to) にして、 大手投稿への返信として開く (インプ近道)。
    reply_to_id: str = ""
    # 438 Phase 1 (2026-05-27): comment 系候補 (GEMMA_BRANDING) の og:image
    # 添付。 ``image_bytes`` が空でなければ既存 437 image gen path を bypass
    # して この bytes をそのまま GCS upload + share-x-cand に乗せる。
    # ``image_alt_text`` は X media_upload の alt 属性として渡す (出典担保)。
    # ``image_source_url`` は debug / log 用 (実 fetch した og:image の URL)。
    image_bytes: bytes = b""
    image_alt_text: str = ""
    image_source_url: str = ""
    # 2026-07-02 user 決定: 動画SNS (引用RT) はインプが取れるため、 同一選手でも
    # 発信メディア (@handle) が違えば別候補として残す。 dedup の (選手×媒体) 判定に
    # 使う元投稿アカウントの handle。 動画/引用RT lane 以外は空のまま。
    media_handle: str = ""
    # 2026-07-03 user 指摘「メジャー級の話題が player 履歴 dedup で出ない」:
    # 高ニュース価値 (メジャー/移籍/引退 等) の候補は recent-player cooldown を
    # 免除する。 news_opinion fallback 側 (runner) が判定して立てる。
    history_exempt: bool = False


_DEFAULT_PLAYER_MAX_PER_MAIL = 1
_NEWS_OPINION_METRIC = "NEWS_OPINION"
_COMMENT_DB_METRIC = "COMMENT_DB"
_FAN_VOICE_METRIC = "FAN_VOICE"
_GEMINI_BRANDING_METRIC = "GEMMA_BRANDING"
_HOCHI_REPLY_METRIC = "HOCHI_REPLY"
_REPLY_CANDIDATE_METRIC = "reply_candidate"
# @Tigers_140609 風の速報スクレイプ型 (重要コメント + 数字だけ抜いて速報)。
# 報知/サンスポ記事 facts を news_scrape_x_post で 280 字速報に整形した候補。
_NEWS_SCRAPE_METRIC = "news_scrape"
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
    "２軍",
    "二軍",
    "ファーム",
    "イースタン",
    "ウエスタン",
    "育成",
)
_THIRD_TEAM_TERMS = (
    "3軍",
    "３軍",
    "三軍",
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


def _ensure_player_name_leads_post_text(value: object, player: str) -> str:
    """Keep the target player visible at the start of the first line."""
    text = str(value or "").strip()
    name = str(player or "").strip()
    if not text or not name:
        return text
    first_line = text.splitlines()[0].lstrip()
    lead_window = first_line[: max(len(name) + 3, 14)]
    if (
        name in lead_window
        or first_line.startswith(f"【{name}】")
        or first_line.startswith(f"{name}：")
    ):
        return text
    prefixed = f"{name}、{text}"
    return prefixed if len(prefixed) <= X_CHAR_LIMIT else _finalize_post_text(prefixed)


def _cap_sentence(value: object, max_chars: int) -> str:
    """文末 (。！？!?) で自然に切って max_chars 以内に収める。

    動画ポスト対策 (user 2026-06-09): X は本文が長いと「動画＋テキスト」を一緒に
    投稿できない (短くすると動画が付く)。引用RT/動画候補のコメントを余裕を持って短く
    固定するために使う。文末が取れなければ … で切る。

    改行は保持する (2026-07-08 user「フーガは改行があるので読みやすい」)。従来は
    全空白を潰していたため、prompt の短文改行指示が投稿時に平文化されていた。
    """
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    text = "\n".join(line for line in lines if line)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    window = text[:max_chars]
    cut = max((window.rfind(c) for c in "。！？!?"), default=-1)
    if cut >= int(max_chars * 0.5):
        return window[: cut + 1]
    return window[: max(0, max_chars - 1)].rstrip() + "…"


def _video_post_char_cap() -> int:
    """動画ポストコメントの上限 (既定 110、env X_VIDEO_POST_MAX_CHARS で調整可)。"""
    try:
        return max(40, int(os.environ.get("X_VIDEO_POST_MAX_CHARS", "110")))
    except (TypeError, ValueError):
        return 110


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


# 2026-07-03: X 由来 RSS タイトルに混ざる URL (途中で切れた "https://hochi.n…" 含む) /
# "▼記事を読む▼" 系マーカー / ハッシュタグを投稿文へ持ち込まない。
# 2026-07-05: RSSHub summary の `<br />` や壊れた `https:…` 断片も
# X投稿案に出るとそのまま投稿不可になるため、source text の入口で潰す。
_SOURCE_NOISE_RE = _re.compile(r"https?:(?://)?\S*|www\.\S+|▼[^▼]{0,24}▼|[#＃]\S+")
_SOURCE_LABEL_NOISE_RE = _re.compile(r"(?:記事内容の|記事内容|続きを読む|全文はこちら)")
_SOURCE_BR_RE = _re.compile(r"(?is)<br\s*/?>")
_SOURCE_HTML_TAG_RE = _re.compile(r"(?is)<[^>]*>")


def _clean_source_text_for_post_material(value: object) -> str:
    """Normalize RSS title/summary text before it reaches X copy."""
    text = _html.unescape(str(value or ""))
    if not text:
        return ""
    text = _SOURCE_BR_RE.sub("。", text)
    text = _SOURCE_HTML_TAG_RE.sub(" ", text)
    text = _SOURCE_NOISE_RE.sub(" ", text)
    text = _SOURCE_LABEL_NOISE_RE.sub(" ", text)
    text = text.replace("/>", " ").replace("<", " ").replace(">", " ")
    text = _re.sub(r"\s+([。、！？!?])", r"\1", text)
    text = _re.sub(r"[。]{2,}", "。", text)
    text = _re.sub(r"\s+", " ", text)
    return text.strip(" 　。、")


def _player_core_name(player: str) -> str:
    """表示名から冠イニシャルを外した核名 (例 'Ｆ．ウィットリー' → 'ウィットリー')。"""
    return _re.sub(r"^[Ａ-ＺA-Z][．.]\s*", "", str(player or "").strip())


def _extract_source_record_phrase(title: str, excerpt: str, player: str) -> str:
    """Return a short record phrase copied from source title/excerpt."""
    clean_title = _clean_source_text_for_post_material(title)
    clean_excerpt = _clean_source_text_for_post_material(excerpt)
    parts = [clean_title]
    parts.extend(
        p.strip()
        for p in _re.split(r"[。\n\r]+", clean_excerpt)
        if p.strip()
    )
    core = _player_core_name(player)
    for part in parts:
        if not any(term in part for term in _RECORD_TERMS):
            continue
        phrase = _re.sub(r"【[^】]{1,40}】", "", part)
        phrase = _SOURCE_NOISE_RE.sub(" ", phrase)
        for name in {player, core} - {""}:
            phrase = phrase.replace(f"巨人・{name}", name)
            phrase = phrase.replace(f"巨人の{name}", name)
            phrase = phrase.replace(f"読売ジャイアンツ・{name}", name)
        phrase = phrase.strip(" 　。、")
        # 【選手名】ヘッダ形式 (2026-07-03) と重ならないよう、先頭の
        # 選手名 (表示名 / 核名どちらの表記でも) は落とす。
        stripped = False
        for name in (player, core):
            if stripped or not name:
                continue
            for suffix in ("が", "は", "、", " "):
                prefix = f"{name}{suffix}"
                if phrase.startswith(prefix):
                    phrase = phrase[len(prefix):].strip(" 　。、")
                    stripped = True
                    break
        # 2026-07-03 実事故「【Ｆ．ウィットリー】速いぞウィットリー 来日後最速
        # １５８キロ！…」: 見出し内の煽り節 (選手名入り) が残ると【選手名】ヘッダ
        # と名前二重の丸写しになる。空白区切りの節のうち選手名を含む節は落とす
        # (ヘッダで選手は既に立っている)。全節が落ちたら "" → 汎用文へ fallback。
        segments = [s for s in _re.split(r"[ 　]+", phrase) if s]
        name_terms = {n for n in (player, core) if n}
        kept = [
            s for s in segments
            if not any(n in s for n in name_terms)
        ]
        phrase = " ".join(kept)
        phrase = _re.sub(r"\s+", " ", phrase).strip(" 　。、")
        if phrase:
            return _truncate_text(phrase, 72).rstrip("。！？!?")
    return ""


def _build_source_backed_post_text(
    player: str,
    material_type: str,
    *,
    source_title: str = "",
    source_excerpt: str = "",
    source_topic_family: str = "",
) -> str:
    """Build URL-free, hashtag-free copy from verified source presence only.

    RSS titles/summaries can contain unverified numbers, so the public
    post text only uses the detected player name and the source-backed
    material type. The URL/title stay in ``draft_text`` as evidence.
    """
    if material_type == "comment":
        body = (
            f"{player}のコメントは、結果だけでは見えないベンチの空気や本人の温度を拾える材料になる。"
            "こういう言葉が出る時は、次の試合の見方も少し変わる。\n"
            "確定しているのは本人の言葉が記事で出ていることなので、数字は足さず、"
            "今の状態や準備の見方として受け止めたい。良し悪しを決めるより、材料として置く。\n"
            "巨人ファンとしては、次の出番でその言葉が配球や打席の落ち着きにどう出るかを見たい。"
        )
    elif material_type == "record":
        record_phrase = _extract_source_record_phrase(source_title, source_excerpt, player)
        if source_topic_family == "pitching":
            next_scene = "次のマウンド"
        elif source_topic_family == "batting":
            next_scene = "次の打席"
        else:
            next_scene = "次の出番"
        if record_phrase:
            # 2026-07-03 user 確定「【選手名】 内容 画像があるとよい」+
            # 「記事の数字ごと載せて出す」: 記録系は headline 型のたんぱく事実で
            # 出す。数字は元記事記載のものをそのまま使う (捏造なし)。
            body = f"【{player}】{record_phrase}"
        else:
            body = (
                f"{player}の記録・節目が記事で出ている。\n"
                "未確認の数字は足さず、出ている節目だけで押さえる。\n"
                f"{next_scene}でもう一つ積み上げられるか。"
            )
    elif material_type == "farm":
        body = (
            f"ファームで{player}の名前が出ている時は、今すぐの結論より一軍につながる準備として見たい。"
            "二軍の動きは、あとで起用の伏線になることもある。焦って持ち上げず、変化を追いたい。\n"
            "確定しているのは記事でその動きが扱われていることなので、数字は足さず、"
            "状態や役割の変化を見る材料にしたい。急がず、次の起用と合わせて見たい。\n"
            "巨人ファンとしては、次に一軍の流れとどこで重なるかを追いたい。"
        )
    else:
        body = (
            f"{player}の話題が続く時は、結果だけではなく起用や立ち位置まで含めて見たくなる。"
            "名前が出る理由を追うと、試合の見方も少し変わる。今の流れの中で見たい材料として残したい。\n"
            "確定しているのは記事で名前が出ていることなので、未確認の数字は足さず、"
            "今の文脈を整理しておきたい。印象だけで決めず、次の場面とつなげたい。\n"
            "巨人ファンとしては、次の出番で何が変わるかを見たい。"
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
        f"{player}のコメントは、結果だけでは見えない空気や本人の温度を拾える材料になる。"
        "言葉と数字を並べると、次の試合の見方も少し変わる。\n"
        f"DBで確認できる数字は{fact_line}。"
        "印象だけでなく、今の状態を見る根拠として置いておきたい。\n"
        "巨人ファンとしては、次の出番でその言葉と数字がプレーにどうつながるかを見たい。"
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


_KATAKANA_CHAR_RE = _re.compile(r"[ァ-ヶー]")
_KANJI_CHAR_RE = _re.compile(r"[\u4e00-\u9fff々]")


def _alias_hits_with_boundary(text: str, key: str, *, raw_text: str = "") -> bool:
    """短いカタカナ alias が長いカタカナ語の内部に埋まる誤爆を防ぐ一致判定。

    2026-07-03 実事故: alias「バル」(バルドナード略称) がサッカー記事の
    「オヤルサバル」に部分一致し、W杯記事から巨人ポストが生成された。
    全カタカナ 3 文字以下の alias は、一致位置の前後がカタカナでない時だけ
    有効とする。それ以外の alias は従来の部分一致のまま。
    """
    if len(key) <= 3 and all(_KATAKANA_CHAR_RE.match(ch) for ch in key):
        char_re = _KATAKANA_CHAR_RE
    elif len(key) <= 2 and all(_KANJI_CHAR_RE.match(ch) for ch in key):
        # 2026-07-06 実事故: alias「丸」が「中日金丸」の内部に一致し、笹原操希の
        # 記事から丸佳浩の候補が生成された。短い漢字姓 alias は前後が漢字でない
        # 一致だけ有効 (「巨人・丸」「丸が」 は通り、「金丸」「丸山」 は弾く)。
        # 判定は raw text 優先 (正規化は「・」等の区切りを落とし境界が消えるため)。
        char_re = _KANJI_CHAR_RE
        if raw_text:
            text = raw_text
    else:
        return key in text
    start = 0
    while True:
        i = text.find(key, start)
        if i < 0:
            return False
        before = text[i - 1] if i > 0 else ""
        after = text[i + len(key)] if i + len(key) < len(text) else ""
        if not (before and char_re.match(before)) and not (
            after and char_re.match(after)
        ):
            return True
        start = i + 1


_NPB12_ROSTER_PATH = _Path(__file__).resolve().parents[1] / "config" / "npb_12team_roster.json"
_NON_GIANTS_FULLNAMES_CACHE: Optional[tuple[str, ...]] = None


def _load_non_giants_fullnames() -> tuple[str, ...]:
    """npb_12team_roster.json の巨人以外の在籍者フルネーム (正規化済み)。

    2026-07-03 user 指摘「同じ苗字の他球団間違い多くない？」: 姓 alias
    (山﨑/鈴木 等) は 12 球団で大量に重複し、他球団選手のフルネームの一部に
    誤マッチする事故が続いた (DeNA・山﨑康晃 → 山﨑伊織 等)。alias 一致箇所が
    他球団フルネームの内側だけなら巨人選手の言及ではないと判定するための台帳。
    """
    global _NON_GIANTS_FULLNAMES_CACHE
    if _NON_GIANTS_FULLNAMES_CACHE is not None:
        return _NON_GIANTS_FULLNAMES_CACHE
    names: list[str] = []
    try:
        rows = _json.loads(_NPB12_ROSTER_PATH.read_text(encoding="utf-8"))
        for row in rows:
            if not row.get("active"):
                continue
            if str(row.get("team_code") or "").strip().lower() == "g":
                continue
            name = _normalize_player_name(row.get("name"))
            if name:
                names.append(name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("failed to load npb 12team roster for name guard: %r", exc)
    _NON_GIANTS_FULLNAMES_CACHE = tuple(names)
    return _NON_GIANTS_FULLNAMES_CACHE


def _alias_shadowed_by_other_team_fullname(normalized_text: str, key: str) -> bool:
    """alias 一致が他球団選手フルネームの内側にしか無い時 True (誤マッチ)。

    他球団フルネーム (alias より長いもの) を text から潰した後も alias が
    残れば、巨人側の言及が独立に存在する → False (通す)。
    例: 「DeNA・山﨑康晃、登録抹消」は「山﨑」が山﨑康晃の内側のみ → True。
    「巨人・山﨑とDeNA・山﨑康晃の投げ合い」は潰した後も「山﨑」が残る → False。
    """
    masked = normalized_text
    for full in _load_non_giants_fullnames():
        if len(full) > len(key) and key in full and full in masked:
            masked = masked.replace(full, "\x00" * len(full))
    if masked is normalized_text:
        return False
    return not _alias_hits_with_boundary(masked, key)


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
        if key and _alias_hits_with_boundary(normalized_text, key, raw_text=str(text or "")):
            # 2026-07-03: 同姓の他球団選手 (フルネームが text に居る) への
            # 誤マッチを検出の中央で遮断。全 lane (news / x_buzz / リプ /
            # 記録記事) に効く。
            if _alias_shadowed_by_other_team_fullname(normalized_text, key):
                LOG.info(
                    "giants_name_guard_skip alias=%s canonical=%s "
                    "(他球団フルネーム内の一致のみ)",
                    key,
                    canonical,
                )
                continue
            return str(canonical or "").strip()
    return ""


def news_opinion_signature(source_url: str, player_name: str) -> str:
    """news_opinion 候補の 24h/168h dedup signature (url×選手で一意)。

    build_news_opinion_candidate と record 優先レーンの事前 skip 判定で
    同一式を共有する (2026-07-07 記録/節目候補の毎便重複対策)。
    """
    url = str(source_url or "").strip()
    player = str(player_name or "").strip()
    signature_hash = _hashlib.sha1(f"{url}\n{player}".encode("utf-8")).hexdigest()[:16]
    return f"news_opinion|{signature_hash}|False|None"


def build_news_opinion_candidate(
    *,
    source_title: str,
    source_url: str,
    player_name: str,
    source_name: str = "",
    source_excerpt: str = "",
    now: Optional[datetime] = None,  # noqa: ARG001 - kept for caller symmetry/tests
    comment_fn=None,
    skip_on_empty_comment: bool = False,
    image_bytes: bytes = b"",
    image_source_url: str = "",
    image_alt_text: str = "",
    plain_rewrite_fn=None,
) -> Optional[Candidate]:
    """Build a fallback X candidate from explicit source text only.

    The generated post avoids invented stats, quotes, and claims. It
    names the player only when the caller supplies a detected roster
    match from the source title/summary.

    ``skip_on_empty_comment`` (2026-07-02 user 指摘「スクレイピングした
    ものだけのポストは余計」): comment_fn (voice) が空を返した時、記事
    タイトル貼り直しの安全テンプレで埋めず None を返す。 record 系 lane
    (2026-06-27「記事にあるものでよい」) は False のまま従来挙動。

    ``image_bytes`` / ``image_source_url`` (2026-07-03 user「【選手名】 内容
    画像があるとよい」): 元記事の画像を候補に添付し、mail 側の
    「画像つきで X に投稿」導線を有効にする (record 記事向け)。
    """
    title = _truncate_text(_clean_source_text_for_post_material(source_title), 70)
    player = str(player_name or "").strip()
    url = str(source_url or "").strip()
    if not title or not url or not player:
        return None
    # 2026-06-01 user「コーチ監督も全員名前を入れて」: player 限定 → 全員 (member=監督コーチ含む OR player=育成含む) に拡張。
    if not (_is_verified_full_giants_member_name(player) or _is_verified_full_giants_player_name(player)):
        return None
    source = _truncate_text(source_name, 28)
    excerpt = _truncate_text(_clean_source_text_for_post_material(source_excerpt), 120)
    material_type, material_label = _classify_news_material(title, excerpt)
    source_topic_family = _infer_source_topic_family(title, excerpt)
    # voice化 (A、 2026-06-01): comment_fn (フーガ+缶詰 LLM) があれば記事に反応する voice を生成。
    # 失敗 / 未設定 / 未検証数字混入は空 → 従来の安全テンプレに fallback (数値未照合の安全担保は維持)。
    post_text = ""
    if comment_fn:
        try:
            post_text = (comment_fn(f"{title}。{excerpt}", player) or "").strip()
        except Exception as exc:  # noqa: BLE001
            LOG.info("news_opinion comment_fn skip: %r", exc)
            post_text = ""
    if not post_text:
        if skip_on_empty_comment and comment_fn is not None:
            # voice が門番落ち / budget 枯渇した候補はテンプレで埋めない
            # (スクレイプ由来のタイトル貼り直しポストを user に出さない)。
            LOG.info(
                "news_opinion skip: voice empty and skip_on_empty_comment "
                "player=%s url=%s", player, url,
            )
            return None
        post_text = _build_source_backed_post_text(
            player,
            material_type,
            source_title=title,
            source_excerpt=excerpt,
            source_topic_family=source_topic_family,
        )
        # 2026-07-06 user「(記録/節目) ポストとして見づらい。相手にわかりやすい
        # ように変えて。LLMをつかってもいい」「相手につたわらない」: record は
        # headline 断片 / 定型文のままにせず、 plain_rewrite_fn (build_plain_data_post、
        # 記事記載の数字のみ許可) で読みやすい文へ書き換える。 失敗時は従来文で続行。
        if material_type == "record" and plain_rewrite_fn is not None:
            try:
                _rewritten = str(plain_rewrite_fn(f"{title}。{excerpt}", player) or "").strip()
            except Exception as exc:  # noqa: BLE001 - 従来文で続行
                LOG.info("news_opinion plain_rewrite skip player=%s: %r", player, exc)
                _rewritten = ""
            if _rewritten:
                post_text = _rewritten
    post_text = _ensure_player_name_leads_post_text(post_text, player)
    # 2026-07-03 user「記事の数字ごと載せて出す」: record は元記事記載の数字を
    # 出典付き事実としてそのまま掲載する (DB照合は別途)。他 material は従来通り。
    if material_type == "record":
        numeric_policy = "数値の扱い: 元記事記載の数字のみ掲載（出典=元記事URL）"
        title_prefix = "記事記載値"
    else:
        numeric_policy = "DB数値照合: なし（未照合のため投稿本文には数値を入れない）"
        title_prefix = "要確認: 数値未照合"
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
        numeric_policy,
    ]
    if excerpt:
        proof_lines.append(f"元記事抜粋: {excerpt}")
    if image_source_url:
        proof_lines.append(f"添付画像: {image_source_url}")
    return Candidate(
        title=f"{title_prefix}｜{material_label}案｜{player}｜{title}",
        metric=_NEWS_OPINION_METRIC,
        period_label=material_label,
        draft_text="\n".join(proof_lines),
        char_count=len(post_text),
        signature=news_opinion_signature(url, player),
        post_text=post_text,
        focus_player=player,
        source_material_type=material_type,
        source_topic_family=source_topic_family,
        image_bytes=image_bytes or b"",
        image_source_url=image_source_url or "",
        image_alt_text=(
            image_alt_text
            or (f"{source or '元記事'}掲載画像。{player}の記事" if image_source_url else "")
        ),
    )


_PLAYER_COMMENT_METRIC = "PLAYER_COMMENT"


def build_player_comment_candidate(
    *,
    member_name: str,
    source_title: str,
    source_url: str,
    html_text: str,
    source_name: str = "",
    image_bytes: bytes = b"",
    image_source_url: str = "",
    image_alt_text: str = "",
    now: Optional[datetime] = None,  # noqa: ARG001 - caller symmetry
    context_fn=None,
) -> Optional[Candidate]:
    """パターン①「選手コメント速報」(2026-06-01): 記事本文 html_text から member の本人発言を
    literal 抽出し、 たんぱく事実型で出す (mainportalhuge 式)。 セリフは LLM 不使用 = 捏造ゼロ。

    形式: `状況説明1行\n名前『発言』`。
    2026-07-06 user「これいいんだけど、なぜこのコメントをしているかも入れてほしい」
    「唐突」: ``context_fn(html_text, member, quote)`` (LLM、記事根拠+数字門番) が
    あれば状況説明1行をセリフの前に置く。無い/失敗時は従来の `名前『発言』` のみ。
    quote が取れない / member 未 verify → None (caller は別候補へ)。
    """
    member = str(member_name or "").strip()
    member_display = _normalize_player_name(member) or member
    url = str(source_url or "").strip()
    if not member or not url or not html_text:
        return None
    if not (_is_verified_full_giants_member_name(member) or _is_verified_full_giants_player_name(member)):
        return None
    try:
        from src.long_quote_extractor import extract_long_quote
        from src.x_post_branding_gen import _resolve_speaker_aliases
    except Exception as exc:  # noqa: BLE001
        LOG.info("player_comment import skip: %r", exc)
        return None
    try:
        aliases = _resolve_speaker_aliases(member)
        # テキストコメントは画像overlay(min100)より短くてよい(user「良いものはそれだけ書く」)。
        quote = extract_long_quote(html_text, speaker_aliases=aliases, min_chars=40)
    except Exception as exc:  # noqa: BLE001
        LOG.info("player_comment extract skip member=%s: %r", member, exc)
        quote = ""
    quote = (quote or "").strip()
    if not quote:
        return None
    context_line = ""
    if context_fn is not None:
        try:
            context_line = str(context_fn(html_text, member_display, quote) or "").strip()
        except Exception as exc:  # noqa: BLE001 - 文脈なしの従来形式で続行
            LOG.info("player_comment context skip member=%s: %r", member_display, exc)
            context_line = ""
    if context_line:
        post_text = f"{context_line}\n{member_display}『{quote}』"
    else:
        post_text = f"{member_display}『{quote}』"
    signature_hash = _hashlib.sha1(f"player_comment|{url}|{member_display}".encode("utf-8")).hexdigest()[:16]
    src = _truncate_text(source_name, 28)
    proof_lines = [
        "【根拠: 記事本文の本人発言 (literal)】",
        f"発言者: {member_display}",
        (f"状況説明1行: LLM生成 (記事lead根拠・数字門番済): {context_line}" if context_line else "状況説明1行: なし (セリフのみ)"),
        f"元媒体: {src or 'unknown'}",
        f"元記事: {_truncate_text(source_title, 60)}",
        f"元記事URL: {url}",
    ]
    if image_source_url:
        proof_lines.append(f"添付画像: {image_source_url}")
    proof_lines.extend([
        "",
        "【X 投稿案 (たんぱく・LLM不使用・literal)】",
        post_text,
    ])
    return Candidate(
        title=f"(コメント速報) {member_display}｜{_truncate_text(source_title, 40)}",
        metric=_PLAYER_COMMENT_METRIC,
        period_label="本人コメント",
        draft_text="\n".join(proof_lines),
        char_count=len(post_text),
        signature=f"player_comment|{signature_hash}|False|None",
        post_text=post_text,
        focus_player=member_display,
        source_material_type="player_comment",
        image_bytes=image_bytes or b"",
        image_alt_text=(
            image_alt_text
            or f"{src or '元記事'}掲載画像。{member_display}のコメント元記事"
        ),
        image_source_url=image_source_url or "",
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


_DATA_SPLIT_INNING_METRIC = "inning_split_surprise"
_DATA_SPLIT_VENUE_METRIC = "venue_split_surprise"


def _fmt_avg3(value: float) -> str:
    """打率を .296 形式 (1 未満は先頭 0 を落とす) で返す。"""
    s = f"{value:.3f}"
    return s.lstrip("0") if value < 1 else s


def build_data_split_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 2,
    min_season_ab: int = 80,
    min_gap: float = 0.120,
    min_phase_ab: int = 20,
    min_venue_ab: int = 30,
    dedup_set: Optional[set[str]] = None,
    comment_fn=None,
) -> list[Candidate]:
    """448: 巨人 regular の「序盤/中盤/終盤」「本拠地/ビジター」別打率の大きな差を
    検出し、 大手未掲載の差別化 X 投稿候補 (メール) を作る。

    insight.db read-only。 公開 X 自動投稿はしない (候補=メールまで)。 配列 index=
    イニングの 9 要素 atbats_json を 447 と同じ ``_classify_atbat`` で分類し、 venue は
    既存 ``giants_venue_from_game_id`` (game_id NPB code) で判定する。 player_canonical は
    フルネーム (例 吉川尚輝) なのでそのまま literal title に使う ([[feedback_x_post_player_naming_full_name]])。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    try:
        from src.data_site_query import _classify_atbat, giants_venue_from_game_id
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_data_split_candidates import failed: %r", exc)
        return []
    try:
        with _sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            players = cur.execute(
                "SELECT player_canonical, SUM(COALESCE(AB,0)) AS ab "
                "FROM batting_logs WHERE team_name='巨人' AND player_canonical IS NOT NULL "
                "GROUP BY player_canonical HAVING SUM(COALESCE(AB,0)) >= ? ORDER BY ab DESC",
                (int(min_season_ab),),
            ).fetchall()
            rows_by_player: dict[str, list[tuple]] = {}
            for (canon, _ab) in players:
                rows_by_player[canon] = cur.execute(
                    "SELECT game_id, COALESCE(AB,0), COALESCE(H,0), atbats_json "
                    "FROM batting_logs WHERE player_canonical=?",
                    (canon,),
                ).fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_data_split_candidates query failed: %r", exc)
        return []

    out: list[Candidate] = []
    for canon, season_rows in rows_by_player.items():
        if len(out) >= max_count:
            break
        # --- inning split (序盤 1-3 / 中盤 4-6 / 終盤 7-9) ---
        inn = {"序盤": [0, 0], "中盤": [0, 0], "終盤": [0, 0]}
        venue = {"本拠地": [0, 0], "ビジター": [0, 0]}
        for game_id, ab, h, aj in season_rows:
            v = giants_venue_from_game_id(str(game_id or ""))
            vlabel = {"home": "本拠地", "away": "ビジター"}.get(v or "")
            if vlabel:
                venue[vlabel][0] += int(ab or 0)
                venue[vlabel][1] += int(h or 0)
            try:
                cells = _json.loads(aj) if aj else []
            except Exception:  # noqa: BLE001
                cells = []
            if not isinstance(cells, list):
                continue
            for idx, cell in enumerate(cells):
                key = "序盤" if idx < 3 else ("中盤" if idx < 6 else ("終盤" if idx < 9 else None))
                if key is None:
                    continue
                is_ab, is_hit = _classify_atbat(str(cell))
                if is_ab:
                    inn[key][0] += 1
                if is_hit:
                    inn[key][1] += 1

        best: Optional[tuple] = None  # (gap, metric, signature, title, post_text, db_fact_line, sample, sample_label)
        # inning surprise
        if all(inn[k][0] >= min_phase_ab for k in inn):
            avgs = {k: inn[k][1] / inn[k][0] for k in inn}
            hi = max(avgs, key=avgs.get)
            lo = min(avgs, key=avgs.get)
            gap = avgs[hi] - avgs[lo]
            if gap >= min_gap:
                # たんぱく事実型 (chikupn2896 式): 【名前】front-load + split数字 + 客観の文脈。 主観感想なし。
                post = (
                    f"【{canon}】{hi}に強い\n"
                    f"序盤{_fmt_avg3(avgs['序盤'])} / 中盤{_fmt_avg3(avgs['中盤'])} / 終盤{_fmt_avg3(avgs['終盤'])}\n"
                    f"{inn[hi][0]}打数規模で時間帯差が大きい #巨人 #ジャイアンツ"
                )
                fact = (
                    f"{hi}打率 {_fmt_avg3(avgs[hi])} ({inn[hi][1]}安打/{inn[hi][0]}打数) "
                    f"｜序盤{_fmt_avg3(avgs['序盤'])}/中盤{_fmt_avg3(avgs['中盤'])}/終盤{_fmt_avg3(avgs['終盤'])}"
                )
                best = (gap, _DATA_SPLIT_INNING_METRIC, f"data_split|{canon}|inning",
                        f"{canon} {hi}に強い (打率{_fmt_avg3(avgs[hi])})", post, fact,
                        inn[hi][0], f"今季{hi} {inn[hi][0]}打数")
        # venue surprise (prefer the larger-gap split if both qualify)
        if all(venue[k][0] >= min_venue_ab for k in venue):
            havg = venue["本拠地"][1] / venue["本拠地"][0]
            aavg = venue["ビジター"][1] / venue["ビジター"][0]
            gap = abs(havg - aavg)
            if gap >= min_gap and (best is None or gap > best[0]):
                hi_label, hi_avg = ("本拠地", havg) if havg >= aavg else ("ビジター", aavg)
                lo_label, lo_avg = ("ビジター", aavg) if hi_label == "本拠地" else ("本拠地", havg)
                hi_ab, hi_h = venue[hi_label]
                # たんぱく事実型 (chikupn2896 式)。
                post = (
                    f"【{canon}】{hi_label}に強い\n"
                    f"本拠地{_fmt_avg3(havg)} / ビジター{_fmt_avg3(aavg)}\n"
                    f"{hi_ab}打数規模 大手未掲載の球場別split #巨人 #ジャイアンツ"
                )
                fact = (
                    f"{hi_label}打率 {_fmt_avg3(hi_avg)} ({hi_h}安打/{hi_ab}打数) "
                    f"｜本拠地{_fmt_avg3(havg)}/ビジター{_fmt_avg3(aavg)}"
                )
                best = (gap, _DATA_SPLIT_VENUE_METRIC, f"data_split|{canon}|venue",
                        f"{canon} {hi_label}に強い (打率{_fmt_avg3(hi_avg)})", post, fact,
                        hi_ab, f"今季{hi_label} {hi_ab}打数")

        if best is None:
            continue
        gap, metric, signature, title, post_text, db_fact_line, sample, sample_label = best
        if dedup_set is not None and signature in dedup_set:
            LOG.info("data_split dedup skip %s", signature)
            continue
        # 2026-06-01: データはたんぱく事実型 (パターン①、 chikupn2896 式)。 主観フーガ lead は付けない
        # (comment_fn は後方互換で受けるが未使用)。 主観の読みは パターン② フーガ系で別途出す。
        draft = "\n".join([
            "【根拠: 巨人選手データ (大手未掲載 split)】",
            db_fact_line,
            "出典: insight.db (NPB official box score 集計)",
            f"参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post_text,
            "",
            "※ 同一回 2 打席は box 1 セル圧縮で総打数が実数を僅かに下回る。安打数は一致。",
        ])
        out.append(Candidate(
            title=title,
            metric=metric,
            period_label="今シーズン",
            draft_text=draft,
            char_count=len(post_text),
            signature=signature,
            post_text=post_text,
            focus_player=canon,
            db_fact_line=db_fact_line,
            team_level="first",
            sample_size=int(sample),
            sample_label=sample_label,
            why_now="data-site 差別化 metric (大手未掲載)",
            source_material_type="data_split",
        ))
    LOG.info("data_split: built %d candidates (max=%d)", len(out), max_count)
    return out


_VIDEO_RADAR_METRIC = "x_buzz_post"


def _x_buzz_has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def _x_buzz_event_comment(text: str, player: str, phase: str = "") -> str:
    """451: 引用元 X 投稿の「出来事」に反応する引用RTコメントを返す (LLM 不使用)。

    元投稿に事実 (完投 / 特大HR / 奪三振数 等) が書いてあるので、 それを拾って
    ヨシラバー voice (ファン目線・フルネーム・敬称なし・hashtag 無し) で反応する。
    シーズン平均など出来事と無関係な数字は貼らない (矛盾を避ける)。
    ``phase`` (試合前/試合中/試合後) があれば、 出来事が拾えない時の汎用文をフェーズに合わせる。
    """
    t = text or ""
    who = (player or "巨人").strip()

    def _grab(pat: str) -> str:
        m = _re.search(pat, t)
        return m.group(0) if m else ""

    if "完封" in t:
        head = "プロ初完封" if ("初完封" in t) else "完封"
        return f"{who}、{head}。最後のアウトまで腕が振れてるのが画面で分かる。"
    if "完投" in t:
        if "初完投" in t or "プロ初" in t:
            return f"{who}、プロ初完投。終盤まで球威が落ちないのが動画で分かる。"
        return f"{who}、完投。最後まで押し込む球の強さが画面から伝わる。"
    if "サヨナラ" in t:
        if _x_buzz_has_any(t, ("ホームラン", "本塁打", "アーチ", "一発", "弾")):
            return f"{who}、サヨナラの打席でこの振り切り。ベンチの跳ね方まで何回でも見たい。"
        return f"{who}、サヨナラの瞬間の表情がいい。ベンチの空気まで一気に変わってる。"
    if _x_buzz_has_any(t, ("ホームラン", "本塁打", "アーチ", "一発", "弾")):
        adj = "特大の" if ("特大" in t or "場外" in t or "弾丸" in t) else ""
        farm = "二軍で" if any(f in t for f in ("二軍", "ファーム", "イースタン")) else ""
        if adj:
            return f"{who}、{farm}{adj}一発。このスイングと打球音だけでリプレー確定。"
        return f"{who}、{farm}このスイングで運べるのが強い。打球の伸び方が気持ちいい。"
    k = _grab(r"\d+奪三振")
    inn = _grab(r"\d+回")
    if k or _x_buzz_has_any(t, ("好投", "無失点", "粘投", "力投", "三者凡退", "奪三振", "三振")):
        detail = "・".join(x for x in (inn, k) if x)
        lead = f"{detail}の好投" if detail else "好投"
        return f"{who}、{lead}。球で押し込めてるのが動画だとはっきり分かる。"
    if _x_buzz_has_any(t, ("猛打賞", "マルチ", "固め打ち", "3安打", "４安打", "4安打")):
        return f"{who}、1打席ずつ振りが強い。固め打ちというより内容で乗ってきてる。"
    if _x_buzz_has_any(t, ("タイムリー", "適時", "決勝打", "勝ち越し", "値千金")):
        return f"{who}、この場面で振り切れるのが強い。ベンチの空気まで変える一打。"
    if _x_buzz_has_any(t, ("ファインプレー", "好守", "好返球", "美技", "好捕")):
        return f"{who}、この一歩目と送球よ。捕ってから投げるまでが速いからアウトにできる。"
    if _x_buzz_has_any(t, ("レーザービーム", "補殺", "送球", "刺した", "タッチアウト")):
        return f"{who}、この送球は動画で見た方が早い。捕ってから投げるまでが速すぎる。"
    if _x_buzz_has_any(t, ("ダイビング", "背走", "ジャンピング", "フェンス", "スライディング")):
        return f"{who}、この追い方と体の投げ出し方よ。最後まで打球から目が切れてない。"
    if _x_buzz_has_any(t, ("ガッツポーズ", "雄叫び", "表情", "ハイタッチ", "ベンチ", "ダグアウト")):
        return f"{who}、この表情とベンチの反応がいい。文字より動画で伝わる場面。"
    if _x_buzz_has_any(t, ("練習", "フリー打撃", "打撃練習", "居残り")):
        return f"{who}、練習動画でもスイングの強さが分かる。打球の伸び方を見てしまう。"
    if _x_buzz_has_any(t, ("ブルペン", "投球練習", "キャッチボール")):
        return f"{who}、ブルペンの腕の振りがいい。球の出方まで見たくなる動画。"
    if _x_buzz_has_any(t, ("初登板", "初先発", "初勝利", "初安打", "初打点", "初本塁打", "復帰", "昇格", "1軍", "一軍")):
        return f"{who}、この表情と動きなら上でも見たい。きっかけの場面として強い。"
    if _x_buzz_has_any(t, ("勝利", "連勝", "勝ち越", "快勝", "勝った")):
        return f"{who}、ベンチのハイタッチまで含めて勝ち方がいい。動画だと表情まで伝わる。"
    # 出来事が拾えない (編集動画 / 練習周辺 等) 時も、抽象語だけで終わらせない。
    if phase == "試合前":
        return f"{who}、試合前の動きと表情がいい。今日は最初の打席から見たくなる。"
    if phase == "試合中":
        return f"{who}、ベンチとスタンドの反応まで一気に変わってる。動画で見ると温度が違う。"
    if phase == "試合後":
        return f"{who}、試合後に見返すと表情まで効いてくる。今日の勝負どころの動画。"
    return f"{who}、この場面は文字より動画で刺さる。表情と周りの反応まで見てしまう。"


def _x_buzz_player_fact(db_path: Optional[str], canonical: str) -> str:
    """451: 引用RT コメントを濃くするため、 insight.db から選手の今季実数字を 1 行で返す。

    read-only SELECT only。 打者は 打率/安打/打点 (AB>=10)、 それ未満で投手 record があれば
    防御率/奪三振。 取れなければ空文字 (caller は数字なしの voice コメントに fallback)。
    """
    if not db_path or not canonical:
        return ""
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT COALESCE(SUM(AB),0), COALESCE(SUM(H),0), COALESCE(SUM(RBI),0) "
                "FROM batting_logs WHERE player_canonical=?",
                (canonical,),
            ).fetchone()
            ab, h, rbi = (int(row[0]), int(row[1]), int(row[2])) if row else (0, 0, 0)
            if ab >= 10:
                avg = h / ab
                avg_s = f"{avg:.3f}".lstrip("0")
                return f"今季打率{avg_s}・{h}安打{rbi}打点"
            # 投手 fallback (登板数 + 奪三振 + 防御率)
            prow = cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(K),0), COALESCE(SUM(ER),0), COALESCE(SUM(IP),0.0) "
                "FROM pitching_logs WHERE player_canonical=?",
                (canonical,),
            ).fetchone()
            if prow and int(prow[0]) > 0:
                g, k, er, ip = int(prow[0]), int(prow[1]), int(prow[2]), float(prow[3])
                era = f"・防御率{(er * 9.0 / ip):.2f}" if ip > 0 else ""
                return f"今季{g}登板{era}・{k}奪三振"
    except Exception as exc:  # noqa: BLE001
        LOG.info("x_buzz player fact skip %s: %r", canonical, exc)
    return ""


# 2026-06-03 コスト削減: 試合中 (in_game_strong 枠) は 15 分毎発火のため、 buzz ソースを
# 高シグナルなアカウントに絞り、 全8feed 取得→生成の叩きを抑える (user 確定)。 試合外は全ソース。
# 2026-06-03 user: 試合中は DAZN (DAZNJPNBaseball) と 日テレ巨人中継 (ntv_baseball) の動画ソースを
# 戻す。 試合中は動画ハイライトが最も高シグナルなため (報知 + スポニチ + 読売公式 + 日テレ + DAZN)。
_GAME_BUZZ_HANDLES = [
    "hochi_giants",
    "SponichiGiants",
    "TokyoGiants",
    "ntv_baseball",
    "DAZNJPNBaseball",
    # 2026-07-12 user「動画はもっとふやしていい」: 動画率の高い記者/班アカを
    # 試合帯ソースへ追加 (どちらも _BUZZ_HANDLES で実feed検証済。試合中の
    # 球場撮影動画が主で、buzz-only 便のリプ対象にも同時になる)。
    "nikkan_giants",
    "chiehochi6",
]

_today_away_cache: dict[str, Optional[bool]] = {}


def _today_giants_away(now: Optional[datetime] = None) -> Optional[bool]:
    """今日の巨人戦がビジターか。試合なし/判定不能は None (fail-open)。

    NPB公式月間日程 (data_site_query.parse_giants_upcoming) で判定。1 fire 内
    memo cache 付き。
    """
    if now is None:
        now = datetime.now(JST)
    today = now.astimezone(JST).date().isoformat()
    if today in _today_away_cache:
        return _today_away_cache[today]
    result: Optional[bool] = None
    try:
        from src.data_site_query import fetch_giants_upcoming
        for g in fetch_giants_upcoming(limit=2) or []:
            if str(g.get("date") or "") == today:
                ha = str(g.get("home_away") or "").strip()
                if ha:
                    result = ha != "本拠地"
                break
    except Exception as exc:  # noqa: BLE001
        LOG.info("today_giants_away lookup skipped: %r", exc)
    _today_away_cache[today] = result
    return result


def game_buzz_handles(now: Optional[datetime] = None) -> list[str]:
    """試合帯の動画/リプ用ソース handle 一覧 (優先順)。

    2026-07-03 user「ビジターは日テレないよ。ホームだけ」: 日テレは
    ホーム戦の中継局なので、ビジター戦では ntv_baseball を外し、動画は
    DAZN 側で拾う。ホーム/判定不能 (fail-open) は従来通り日テレを含む。
    """
    handles = list(_GAME_BUZZ_HANDLES)
    if _today_giants_away(now) is True:
        handles = [h for h in handles if h != "ntv_baseball"]
        LOG.info("game_buzz_handles: away game -> NTV excluded, DAZN covers video")
    return handles


# トレンド関連選手の 動画+記事 ペア (2026-07-10 user「記事ポストもトレンドに
# かかわる人なら動画と記事ポストの2つ出したい」) 用の枠外ボーナス上限。
_TREND_PAIR_BONUS_MAX = 2


def _trending_text_blob() -> str:
    """Google 急上昇語 + Yahoo トピックス見出しを連結した blob (トレンド選手判定用)。

    ENABLE_X_POST_SEARCH_TREND が OFF なら "" (既存不変 / unit test hermetic)。
    取得は search_trend_note 側の TTL memo で、後段 build_trend_note_and_boost と
    1 fire 1 回に共有される。失敗は ""。
    """
    flag = (os.environ.get("ENABLE_X_POST_SEARCH_TREND") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return ""
    try:
        from src import search_trend_note as _stn

        parts = [t.get("keyword") or "" for t in _stn.fetch_jp_trends()]
        parts += _stn.fetch_yahoo_sports_topics()
        return " ".join(p for p in parts if p)
    except Exception as exc:  # noqa: BLE001 - トレンドは飾り、失敗で止めない
        LOG.info("trend blob skip: %r", exc)
        return ""


def _player_in_trend_blob(player: str, blob: str) -> bool:
    """選手がいまのトレンド (急上昇語/トピックス見出し) に関わっているか。

    フルネーム (空白除去) 一致、または姓 (2 字以上) 一致で True。
    """
    if not player or not blob:
        return False
    name = player.replace(" ", "").replace("　", "")
    if name and name in blob:
        return True
    surname = _re.split(r"[ 　]", player, maxsplit=1)[0]
    return len(surname) >= 2 and surname in blob


def build_video_radar_candidates(
    db_path: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
    max_count: int = 3,
    dedup_set: Optional[set[str]] = None,
    fetch_fn=None,
    min_score: int = 2,
    comment_fn=None,
    handles: Optional[list[str]] = None,
    avoid_player_names: Optional[set[str]] = None,
    keep_low_signal: bool = False,
    allow_photo_and_article: bool = False,
) -> list[Candidate]:
    """451: 巨人系 X account の投稿 (RSSHub 経由) から「懐かしい・ファンが面白い・いま話題」の
    投稿を拾い、 **引用RT / リプライ** 用の X 投稿候補 (メール) を作る。

    ``allow_photo_and_article=True`` (2026-07-10 user): 動画だけでなく報知・公式等の
    写真付き投稿・記事見出し投稿も引用RT候補に含める (📷/📰 で種別表示)。

    user 方針 (2026-06-01): **YouTube は使わない**。 外部リンクは X でリーチが落ちるため、
    X 内で完結する引用RT/リプライ候補にする (本文に外部リンクを貼らない)。 一記事一本 (選手ごと 1 本)。
    公開 X 自動投稿はしない (候補=メールまで)。 Gemini / X API 不使用。
    """
    if now is None:
        now = datetime.now(JST)
    # 試合前後の15分毎 dense 発火帯 (スタメン17:15-19:00 + 試合中19:00-21:45) は
    # ソースを3アカウントに絞る (コスト削減、 user 確定: 18時から試合ランプ)。
    # caller が handles を明示した場合はそれを優先 (override / test 用)。
    _narrow_labels = {
        _X_IMPRESSION_TIMING_LABELS["lineup"],
        _X_IMPRESSION_TIMING_LABELS["in_game_strong"],
    }
    if handles is None and x_impression_timing_label(now) in _narrow_labels:
        handles = game_buzz_handles(now)
        LOG.info("x_buzz dense window: source narrowed to %s", handles)
    try:
        from src import video_radar as _vr
    except Exception as exc:  # noqa: BLE001
        LOG.warning("video_radar import failed: %r", exc)
        return []
    # 2026-06-01 user「コーチ監督も全員名前を入れて」: 選手のみ → 全員 (player ∪ member=選手+監督+コーチ+育成) で検出。
    alias_map = {**_load_giants_player_aliases(), **_load_giants_member_aliases()}

    def _detect(text: str) -> str:
        return detect_giants_player_name(text, alias_map=alias_map)

    # RSSHub 叩きすぎ防止: fetch_buzzing_players と gather_buzz_posts は同じ 8 feed を
    # 同 URL で読むため、 1 fire 内で同 URL を 1 回だけ取得する memo cache を噛ませる
    # (16→8 fetch/fire)。 試合帯は 15 分おき発火なので RSSHub レート対策に効く。
    _base_fetch = fetch_fn or _vr._cached_default_fetch
    _fetch_cache: dict = {}

    def _cached_fetch(url: str) -> str:
        if url not in _fetch_cache:
            _fetch_cache[url] = _base_fetch(url)
        return _fetch_cache[url]

    # X バズ signal (RSSHub 経由、 X API 不使用)。 取得失敗は空で続行 (graceful)。
    try:
        buzz_counts = _vr.fetch_buzzing_players(
            detect_player_fn=_detect, fetch_fn=_cached_fetch, handles=handles
        )
    except Exception as exc:  # noqa: BLE001
        LOG.info("x_buzz buzz skip: %r", exc)
        buzz_counts = {}
    buzz_players = set(buzz_counts)
    if buzz_players:
        LOG.info("x_buzz buzz players: %s", sorted(buzz_counts.items(), key=lambda kv: kv[1], reverse=True))

    try:
        posts = _vr.gather_buzz_posts(
            detect_player_fn=_detect,
            fetch_fn=_cached_fetch,
            buzz_players=buzz_players,
            min_score=min_score,
            now=now,
            # 2026-06-11 user「DAZNの動画試合中のポストをしたい」: 動画クリップは
            # 編集遅延で投稿が 30 分超になりがちで、 試合中窓 0.5h だと DAZN/日テレの
            # 試合中ハイライトがほぼ全滅していた (6/10 実測: 試合中便 built 0 連発)。
            # 動画 lane だけ floor 2h を敷く。 news/fan_voice lane の 0.5h は不変。
            max_age_hours=max(2.0, phase_freshness_max_age_hours(now)),
            handles=handles,
            allow_photo_and_article=allow_photo_and_article,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("x_buzz gather failed: %r", exc)
        return []

    phase_label, phase_hint = _video_comment_phase_hint(now)
    # トレンド関連選手 (2026-07-10 user): 急上昇語に関わる選手は
    # ①動画優先ソート内でさらに前へ ②動画+記事(写真)の 2 本出しを許可。
    trend_blob = _trending_text_blob()
    if trend_blob:
        posts.sort(
            key=lambda d: (
                bool(d.get("has_video")),
                _player_in_trend_blob((d.get("player") or "").strip(), trend_blob),
                d.get("score") or 0,
            ),
            reverse=True,
        )
    trend_video_players: set[str] = set()  # 動画候補を出したトレンド関連選手
    trend_bonus_used = 0
    out: list[Candidate] = []
    used_players: set[str] = set()
    # 2026-07-08 user「同じような文章が」: 定型 fallback (_x_buzz_event_comment) は
    # event 種別ごとに 1 パターンのため、同便内で同文 (選手名差のみ) が並び得る。
    # 選手名を除いた本文 key で 2 本目以降を捨てる (LLM 生成の偶然一致も同様)。
    used_post_texts: set[str] = set()
    avoid_names = {
        _normalize_player_name(name)
        for name in (avoid_player_names or set())
        if _normalize_player_name(name)
    }
    for p in posts:
        _is_video = bool(p.get("has_video"))
        player = (p.get("player") or "").strip()
        _is_trend_player = _player_in_trend_blob(player, trend_blob)
        _bonus_entry = False
        if len(out) >= max_count:
            # 枠が動画で埋まっても、トレンド関連選手の記事/写真側だけは枠外ボーナス
            # (最大 _TREND_PAIR_BONUS_MAX 本) でペア成立を許す (2026-07-10 user)。
            if (
                _is_video
                or not _is_trend_player
                or player not in trend_video_players
                or trend_bonus_used >= _TREND_PAIR_BONUS_MAX
            ):
                continue
            _bonus_entry = True
        url = (p.get("url") or "").strip()
        if not url:
            continue
        signature = "xbuzz|" + _hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        if dedup_set is not None and signature in dedup_set:
            continue
        player_key = _normalize_player_name(player)
        if player_key and player_key in avoid_names:
            LOG.info("x_buzz skip: player in live duplicate cooldown player=%s", player)
            continue
        # A (2026-06-30 user): 低シグナル「選手の話題」(選手名のみ・出来事語なし) は除外。
        # 元投稿に反応材料が無く、 LLM/テンプレ どちらでも選手名以外が同型の generic コメントに
        # なり候補が重複する (別選手で「同じセリフ」になる)。 出来事/懐かし/バズの hook がある
        # 投稿 (好プレー・反応 / 懐かし・名場面 / Xで話題) だけを引用RT候補に残す。
        # 2026-07-02 user 決定「試合前の動画付きSNSはお宝動画があるので逃さない」:
        # 試合前帯は keep_low_signal=True で呼ばれ、 この除外を外す (動画付きが
        # 前提の lane なので、練習動画等は動画そのものが hook)。 重複は URL
        # signature / (選手×媒体) / 内容類似 dedup が従来通り効く。
        if p.get("type_tag") == "選手の話題" and not keep_low_signal:
            LOG.info("x_buzz skip: low-signal tag=選手の話題 player=%s", player or "(none)")
            continue
        # 一記事一本 → (選手×媒体) 一本 (2026-07-02 user 決定): 動画SNS は
        # インプが取れるため、 同じ選手でも発信メディア (@handle) が違えば
        # 別候補として残す。 同一選手×同一媒体だけ 1 本に抑える。
        # トレンド関連選手は 動画/静止 (記事・写真) を別枠にし 2 本出しを許可
        # (2026-07-10 user「トレンドにかかわる人なら動画と記事ポストの2つ」)。
        _pm_key = f"{player}|{(p.get('handle') or '').strip().lower()}"
        if _is_trend_player:
            _pm_key += "|video" if _is_video else "|static"
        if player and _pm_key in used_players:
            continue
        if player:
            used_players.add(_pm_key)
        tag = p["type_tag"]
        src_text = _truncate_text(str(p.get("text") or "").replace("\n", " ").strip(), 140)
        handle = p.get("handle", "")
        # 引用RT コメント案 — まず LLM (comment_fn、 Gemini 3.1 Flash Lite) で元投稿に反応した
        # ヨシラバー voice を生成。 失敗 / 未設定なら LLM なしの出来事 template に fallback
        # (graceful)。 どちらも 出来事と無関係なシーズン平均は本文に貼らない (矛盾回避)。
        # フェーズ (試合前/中/後) で voice トーンを切り替える (既存 voice の例1/2/3 に対応)。
        # 470-②: 差別化テイク用に今季 fact を先に計算し、 comment_fn (引用RT生成) に
        # 渡す。 元投稿が触れていない data 視点を1つ織り込ませる (反応を生む新視点)。
        fact = _x_buzz_player_fact(db_path, player) if player else ""
        post_text = ""
        if comment_fn:
            try:
                try:
                    post_text = (comment_fn(p.get("text", ""), player, phase_hint, db_fact=fact) or "").strip()
                except TypeError:
                    # 旧 2 引数 comment_fn (tests 等) との後方互換
                    post_text = (comment_fn(p.get("text", ""), player) or "").strip()
            except Exception as exc:  # noqa: BLE001
                LOG.info("x_buzz comment_fn failed: %r", exc)
                post_text = ""
        if not post_text:
            # 2026-07-08 user「これが怪しい」: 選手名が取れない候補が定型 fallback に
            # 落ちると主語が「巨人、」の中身ゼロ文になる (フルネーム必須 voice 違反)。
            # LLM 生成ならプレー内容に反応できるが、定型文×選手名なしは投稿価値が
            # 無いのでメール候補から外す。
            if not player:
                LOG.info("x_buzz skip: template fallback without player url=%s", url)
                continue
            if comment_fn is not None:
                # LLM voice が門番で弾かれた時も動画候補自体は捨てない。抽象テンプレへ逃げず、
                # 元投稿の場面語 (打球音 / 一歩目 / 送球 / 表情 / ベンチ反応) に寄せた deterministic
                # hook に落として、メール候補の本数を保つ。
                LOG.info("x_buzz fallback: voice comment empty/gated player=%s", player)
            post_text = _x_buzz_event_comment(p.get("text", ""), player, phase=phase_label)
        post_text = _ensure_player_name_leads_post_text(post_text, player)
        # 動画ポスト対策 (user 2026-06-09): X は本文が長いと「動画＋テキスト」を一緒に
        # 投稿できない (短くすると動画が付く)。 引用RT/動画候補のコメントを短く固定する。
        post_text = _cap_sentence(post_text, _video_post_char_cap())
        _text_key = (post_text.replace(player, "") if player else post_text).strip()
        _dup_comment_note = False
        if _text_key in used_post_texts:
            # 2026-07-15 user「巨人動画SNSが一番インプ取れる。候補は欲しい、コメントは
            # LLM で(時間削減)」: コメント文の重複を理由に候補ごと捨てない。動画は
            # 元投稿 (URL) が違えば別の場面なので、コメント要アレンジの注記付きで残す。
            # LLM voice が付いた候補の重複は従来通り skip (同文連投の防止)。
            if not _is_video:
                LOG.info("x_buzz skip: duplicate post text player=%s", player or "(none)")
                continue
            LOG.info(
                "x_buzz keep: duplicate comment (video, needs edit) player=%s",
                player or "(none)",
            )
            _dup_comment_note = True
        else:
            used_post_texts.add(_text_key)
        # 2026-06-03: ブランディング投稿に「おしゃれ系」ヨシラバー画像を1枚添付 (style B、
        # 選手写真+ブランドパネル、 データなし、 ¥0=PILローカル合成)。 user 確定。
        # env X_POST_BRAND_IMAGE_ENABLED=0 で無効化可。 失敗時は画像なしで続行 (graceful)。
        brand_img = b""
        if player and (os.environ.get("X_POST_BRAND_IMAGE_ENABLED", "1").strip() not in {"0", "false", "no"}):
            try:
                from src import x_post_brand_image as _bimg
                brand_img = _bimg.build_brand_image_for_player(player) or b""
            except Exception as _bexc:  # noqa: BLE001
                LOG.info("brand image skip player=%s: %r", player, _bexc)
                brand_img = b""
        # 種別 (2026-07-10 user「記事も。報知とか公式とかの記事や写真系」):
        # 動画🎬 / 写真📷 / 記事📰 をタイトルと手順文に明示する。
        _kind, _kind_emoji = (
            ("動画", "🎬") if _is_video
            else ("写真", "📷") if p.get("has_image")
            else ("記事", "📰")
        )
        draft = "\n".join([
            f"【{_kind}引用RT候補: {tag}】 @{handle}",
            f"検出選手: {player or '(なし)'}",
            f"▶ 元{_kind}ツイート (タップで開く): {url}",
            f"元投稿本文: {src_text}",
            "",
            (
                f"▼ コピペ用（このコメントだけ貼って動画と一緒に投稿 / {len(post_text)}字）"
                if _is_video else
                f"▼ コピペ用（元ポストを引用RTしてこのコメントを貼る / {len(post_text)}字）"
            ),
            post_text,
            "── ここまで貼る ──",
            (
                "⚠ このコメントは他候補と同文気味。投稿するなら一言アレンジ推奨。"
                if _dup_comment_note else ""
            ),
            "",
            f"参考 (今季・本文には入れない): {fact}" if fact else "",
            (
                "※ 本文が長いと X で動画を一緒に投稿できないため、上のコメントは短く調整済み。"
                if _is_video else
                "※ 引用RTなので元ポストの記事リンク・写真がそのまま読者に見える。転載はしない。"
            ),
            "※ 外部リンク (YouTube 等) は貼らない (リーチ減)。 動画ファイルの転載はしない。",
        ])
        out.append(Candidate(
            title=f"(引用RT{_kind_emoji}) {tag}｜@{handle}｜{player or '巨人'}",
            metric=_VIDEO_RADAR_METRIC,
            period_label="引用RT候補",
            draft_text=draft,
            char_count=len(post_text),
            signature=signature,
            post_text=post_text,
            focus_player=player,
            quote_url=url,
            why_now="X バズ投稿 (引用RT、 native)",
            source_material_type="x_buzz_post",
            image_bytes=brand_img,
            image_alt_text=(f"ヨシラバー {player}" if player else "ヨシラバー"),
            media_handle=(handle or "").strip().lower(),
        ))
        if _is_trend_player and player:
            if _is_video:
                trend_video_players.add(player)
            if _bonus_entry:
                trend_bonus_used += 1
                LOG.info(
                    "x_buzz trend pair bonus: player=%s kind=%s (%d/%d)",
                    player, _kind, trend_bonus_used, _TREND_PAIR_BONUS_MAX,
                )
    LOG.info("x_buzz: built %d candidates (from X posts via RSSHub)", len(out))
    return out


# ---------------------------------------------------------------------------
# MLB watch lane (2026-07-02 user 決定: フォロワー増計画)
# ---------------------------------------------------------------------------
# メジャーへ行った元巨人 (菅野智之 / 岡本和真) + 別枠の大谷翔平 +
# 日本人スター枠 (山本由伸 / 鈴木誠也 / 村上宗隆) を、MLB の
# 試合が動く日本時間の朝〜昼帯だけ引用RT候補としてメールに入れる。
# source は実 feed 検証済 (2026-07-02): MLBJapan=MLB公式日本語 (動画多・
# 大谷/岡本言及多)、SPOTVNOW_jp=MLB中継動画クリップ。日本語のみ採用。
# voice は巨人記事と同じヨシラバーボイス (LLM 失敗時はテンプレで埋めず skip)。

_MLB_WATCH_METRIC = "mlb_watch_post"
# 2026-07-02 user 決定「アメリカの所属チーム公式も入れる」(大谷速報アカ級の速さ狙い):
# 日本語メディア (MLBJapan=数時間遅れの編集済 / SPOTVNOW_jp=日次ダイジェスト) に加え、
# 分単位で clip が出る US 公式を追加。実 feed 検証済 (2026-07-02、動画率 5-13/20):
# MLB=公式ハイライト最速 / Dodgers=大谷 / BlueJays=岡本 / Rockies=菅野。
# 英語 feed でも選手 alias (英名) で拾い、voice LLM が日本語で書くので問題ない。
_MLB_WATCH_HANDLES = [
    "MLBJapan",
    "SPOTVNOW_jp",
    "MLB",
    "Dodgers",
    "BlueJays",
    "Rockies",
    # 2026-07-03 user「メジャーで作られた動画や米国独特のスタッツ画像も引用RTしたい」:
    # MLBStats=公式スタッツカード画像 (大谷言及多、動画混在) /
    # PitchingNinja=投球オーバーレイ動画 (大谷登板日・菅野クリップ)。
    # 実 feed 検証済 (2026-07-03、RSSHub 経由で動画/画像マーカー確認)。
    "MLBStats",
    "PitchingNinja",
    # Dodgers / 日本人MLBの動画・現地記者投稿。英語 feed でも player alias で拾う。
    "SportsNetLA",
    "BLPJapanese",
    "FabianArdaya",
    # 海外動画・大手野球メディア。大谷/山本系は Dodgers/SportsNetLA/FabianArdaya/
    # PitchingNinja を維持しつつ、公式/大手の clip・highlight 供給を増やす。
    "MLBONFOX",
    "MLBNetwork",
    "DodgersNation",
    "DodgerBlue1958",
    "TalkinBaseball_",
    # 鈴木誠也。村上宗隆は所属チーム未固定のため MLBJapan/MLB/MLBStats 側で拾う。
    "Cubs",
    # 2026-07-06 user「入れて」: 吉田正尚 (Red Sox)。佐々木朗希=Dodgers、
    # 今永昇太=Cubs は既存 handle でカバー済み。
    "RedSox",
    # 2026-07-07 user「とかも追加して」「とくに動画でみせたい」: 日本語圏の
    # MLB 動画クリップアカ。実 feed 検証済 (velvityrose=大谷 POV/名場面動画、
    # MasayaKotani=大谷/朗希の現地撮影動画中心、mochiko_dayo17=大谷/山本由伸の
    # 現地観戦動画。いずれも動画マーカー多数、非野球投稿は選手名ゲートで落ちる)。
    "velvityrose",
    "MasayaKotani",
    "mochiko_dayo17",
]
# 表示名 → 検出 alias (部分一致)。MLB 文脈の feed なので姓のみで安全。
# US チーム公式は first name だけで呼ぶ投稿があるため英 first name も入れる
# (Shohei/Kazuma/Tomoyuki。MLB 文脈 feed 限定なので誤爆リスクは低い)。
_MLB_WATCH_PLAYERS: dict[str, tuple[str, ...]] = {
    "菅野智之": ("菅野", "Sugano", "Tomoyuki"),
    "岡本和真": ("岡本", "Okamoto", "Kazuma"),
    # 2026-07-10 user 追加 (元巨人枠)。カタカナは MLB 文脈 feed 限定で安全。
    "グリフィン": ("グリフィン", "Griffin", "Foster"),
    "マイコラス": ("マイコラス", "Mikolas", "Miles"),
    "大谷翔平": ("大谷", "Ohtani", "Shohei"),
    "山本由伸": ("山本由伸", "Yamamoto", "Yoshinobu"),
    "鈴木誠也": ("鈴木誠也", "Suzuki", "Seiya"),
    "村上宗隆": ("村上宗隆", "Murakami", "Munetaka"),
    # 2026-07-06 user 追加。姓のみ alias は巨人・佐々木俊輔 / 他球団吉田との
    # 衝突があるためフルネーム+英名のみ (MLB 文脈 feed 限定でも安全側)。
    "佐々木朗希": ("佐々木朗希", "朗希", "Sasaki", "Roki"),
    "今永昇太": ("今永", "Imanaga", "Shota"),
    "吉田正尚": ("吉田正尚", "Yoshida", "Masataka"),
}
_MLB_EX_GIANTS = frozenset({"菅野智之", "岡本和真", "グリフィン", "マイコラス"})
# 2026-07-05 user lock: 山本由伸/鈴木誠也/村上宗隆も対象。ただし元巨人では
# ないので、LLM framing では「巨人から送り出した」文脈にしない。
_MLB_EXTRA_STARS = frozenset({
    "山本由伸", "鈴木誠也", "村上宗隆",
    # 2026-07-06 user 追加 (非元巨人 = ニュートラル framing)
    "佐々木朗希", "今永昇太", "吉田正尚",
})


# 2026-07-14 user「動画の重複がある」(同じHRのclipが媒体違いで何度も候補に載る):
# 本文から通算/今季の本塁打「号数」を拾い、同一 (選手×号数) を同じプレーとして
# 束ねる。号数が取れない動画は published_at の近接 (同便内のみ) で束ねる。
# 「あと2本で30号」等のカウントダウン文は号数と誤認しないよう除外する。
_MLB_HR_NO_JP = _re.compile(r"第?\s*(\d{1,3})\s*号")
_MLB_HR_NO_EN = _re.compile(
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:home\s*run|homer|hr)\b", _re.I
)
_MLB_HR_NO_EN_NO = _re.compile(r"\b(?:home\s*run|homer|hr)\s+no\.?\s*(\d{1,3})\b", _re.I)


def _mlb_watch_hr_event_no(text: str) -> int:
    """本文が伝える本塁打の号数 (今季/通算) を返す。取れなければ 0。"""
    s = text or ""
    m = _MLB_HR_NO_JP.search(s)
    if m:
        # 「あと N 本で 30 号」「30 号まで」「30 号に王手」等の未達文は
        # 同一プレー key にしない (実際の 30 号 clip を誤ブロックすると
        # 「動画が出なくなる」側に倒れるため、迷ったら key 無しに倒す)
        tail = s[m.end():m.end() + 6]
        head = s[max(0, m.start() - 6):m.start()]
        if "まで" in tail or "王手" in tail or "ならず" in tail or "あと" in head:
            return 0
        return int(m.group(1))
    for pat in (_MLB_HR_NO_EN, _MLB_HR_NO_EN_NO):
        m = pat.search(s)
        if m:
            return int(m.group(1))
    return 0


def _detect_mlb_watch_player(text: str) -> str:
    for name, aliases in _MLB_WATCH_PLAYERS.items():
        if any(a in text for a in aliases):
            return name
    return ""


def build_mlb_watch_candidates(
    *,
    now: Optional[datetime] = None,
    max_count: int = 3,
    ohtani_max: int = 1,
    dedup_set: Optional[set[str]] = None,
    fetch_fn=None,
    comment_fn=None,
    max_age_hours: float = 12.0,
    handles: Optional[list[str]] = None,
    as_reply: bool = False,
    extra_star_max: int = 1,
    per_player_max: int = 1,
    ex_giants_max_age_hours: float = 0.0,
    article_max: int = 0,
    same_play_window_min: float = 45.0,
) -> list[Candidate]:
    """元巨人MLB組 + 大谷の引用RT候補。動画付き優先。

    ``same_play_window_min`` (2026-07-14 user「動画の重複がある」+「厳しすぎて
    動画がでなくなるのはやめて」): 同じプレーの clip が媒体違いで並ぶ重複だけを
    落とす。選手単位の本数は絞らない (別プレーの動画は全部通す)。
    - 号数が取れる本塁打は (選手×号数) を同一プレー key にし、signature を
      event 基準 (``mlbevt|``) にする → 便をまたいでも同じHRのclipは1本。
    - 号数が取れない動画は、同便内で同一選手の published_at がこの分数以内の
      2本目以降だけ落とす (便をまたぐ時間窓ガードはしない = 出なくなる側に
      倒さない)。0 で無効。

    ``article_max`` (2026-07-12 user「メジャーの記事引用増やせる?」LLM枠内):
    テキスト/記事ポスト (メディアなし) を 📰 として 1 便この本数まで通す
    (default 0 = 従来通り全捨て)。sort は 動画 → 画像 → 記事 の順で、
    記事はあくまで枠が余った時の追加素材。as_reply には適用しない。

    - 大谷は別枠 ``ohtani_max`` (既定 1) で上限。元巨人は残り枠。
    - ``extra_star_max`` (既定 1): 日本人スター枠 (山本由伸/鈴木誠也 等) の
      群としての 1 便上限。``per_player_max`` (既定 1): 大谷以外の選手ごとの
      1 便上限。既定は従来挙動、prod は env で緩める (2026-07-07 user
      「大谷岡本など動画SNSはだしちゃっていいよ。沢山」)。同一 (選手×媒体)
      は 1 便 1 本のまま。
    - voice (comment_fn) が空の候補は skip (テンプレで埋めない、
      2026-07-02 余計なポスト方針と同じ)。comment_fn 未設定時も skip。
    - 重複防止: URL signature (24h dedup_set) + 上記の選手別/枠別上限。
    - ``as_reply=True`` (2026-07-03 user「メジャー系の日本公式で大谷や岡本や
      菅野にもリプしたい」): 引用RTではなく返信候補として組む。tweet_id を
      ``reply_to_id`` に載せ、metric は既存リプ policy (_REPLY_CANDIDATE_METRIC)
      に合流する。``handles`` で対象アカウントを差し替え可 (default は引用RT と
      同じ _MLB_WATCH_HANDLES)。
    """
    from src import video_radar as _vr
    from datetime import timezone as _tz

    if now is None:
        now = datetime.now(JST)
    now_utc = now.astimezone(_tz.utc)
    fetch = fetch_fn or _vr._cached_default_fetch
    watch_handles = [h for h in (handles or _MLB_WATCH_HANDLES) if h]
    posts: list[dict] = []
    seen_urls: set[str] = set()
    # 2026-07-07 user「岡本もホームラン打ってるがとんでこない」: 公式アカは投稿数が
    # 多く、岡本HR等が直近30件からスクロール落ちして拾えなかった。50件に拡大。
    feed_urls = {h: f"{_vr._RSSHUB_BASE}/twitter/user/{h}?limit=50" for h in watch_handles}
    fetched = _vr.prefetch_feeds(list(feed_urls.values()), fetch)
    for h in watch_handles:
        xml = fetched.get(feed_urls[h])
        if not isinstance(xml, str):
            LOG.info("mlb_watch fetch skip handle=%s err=%r", h, xml)
            continue
        for item in _vr._extract_rss_items(xml):
            text = item.get("text", "")
            url = item.get("url", "")
            if not text or not url or url in seen_urls:
                continue
            player = _detect_mlb_watch_player(text)
            if not player:
                continue
            published_at = item.get("published_at")
            if published_at is not None:
                age_h = (now_utc - published_at).total_seconds() / 3600.0
                # 2026-07-07 user「巨人アカがメインだから岡本菅野は外せない」:
                # 元巨人だけ鮮度窓を広げる (米デーゲーム=日本深夜のHRを朝一便で
                # 拾う)。大谷/日本人スター枠は従来の max_age_hours のまま。
                age_limit_h = max_age_hours
                if player in _MLB_EX_GIANTS and ex_giants_max_age_hours > 0:
                    age_limit_h = max(max_age_hours, ex_giants_max_age_hours)
                if age_h > age_limit_h:
                    continue
            # 2026-07-02 user 決定「ポストに動画がついてないと意味ない」
            # →「画像でもよいが、動画多め」: メディア付き (動画 or 画像) のみ
            # 候補にし、下の sort で動画を優先する。文字だけの投稿は
            # article_max 枠 (📰、引用RT のみ) を除き出さない。
            _has_media = bool(item.get("has_video") or item.get("has_image"))
            if not _has_media and (as_reply or article_max <= 0):
                continue
            seen_urls.add(url)
            posts.append({
                "text": text,
                "url": url,
                "handle": h,
                "player": player,
                "has_video": bool(item.get("has_video")),
                "has_media": _has_media,
                "published_at": published_at,
            })
    # 動画多め: 動画付きを先に。2026-07-11 user「メジャーの動画が日本人より
    # 早くほしい」: 従来は handle 定義順 (=日本語メディア先頭) がそのまま優先に
    # なっていたため、動画グループ内は鮮度順 (新しい順) に並べ替える。最速で
    # clip を出した海外公式が自然に先頭へ来る。published_at 不明は最後尾。
    # 記事 (メディアなし) は画像の後ろ = 枠が余った時だけ入る。
    posts.sort(
        key=lambda p: (
            (0 if p["has_video"] else (1 if p["has_media"] else 2)),
            -(p["published_at"].timestamp() if p["published_at"] is not None else 0.0),
        )
    )
    out: list[Candidate] = []
    used_player_handles: set[str] = set()
    used_signatures: set[str] = set()
    # 同便内の同一プレー判定用: 採用済み動画の (player, published_at)
    accepted_video_times: list[tuple[str, datetime]] = []
    player_counts: dict[str, int] = {}
    ohtani_used = 0
    ohtani_video_used = 0
    extra_star_used = 0
    article_used = 0
    for p in posts:
        if len(out) >= max_count:
            break
        if not p["has_media"] and article_used >= max(0, article_max):
            continue
        player = p["player"]
        # 媒体種別 (動画/情報/記事) 込みの key: 同一アカでも「動画1 + 情報1」は
        # 許し、同種の連投 (同じアカの動画2本 等) だけ止める (2026-07-07 情報系拾い)。
        player_handle_key = (
            f"{player}|{str(p['handle']).strip().lower()}"
            f"|{'v' if p['has_video'] else ('i' if p['has_media'] else 't')}"
        )
        if player_handle_key in used_player_handles:
            continue
        if player == "大谷翔平":
            if ohtani_used >= ohtani_max:
                continue
            # 2026-07-07 user「大谷HRの動画SNSはだしたいが一個でいい。他の動画では
            # なく情報系を拾って」: 同じHRの動画が媒体違いで並ぶのを止める。
            # 動画は 1 便 1 本、2 本目以降の大谷枠は情報系 (スタッツ画像等) のみ。
            if p["has_video"] and ohtani_video_used >= 1:
                continue
        elif player_counts.get(player, 0) >= max(1, per_player_max):
            continue
        if player in _MLB_EXTRA_STARS and extra_star_used >= max(1, extra_star_max):
            # 軽め枠 (山本由伸/鈴木誠也 等) の群上限
            continue
        url = p["url"]
        tweet_id = ""
        if as_reply:
            m = _re.search(r"/status/(\d+)", url)
            if not m:
                continue
            tweet_id = m.group(1)
        sig_prefix = "mlbreply|" if as_reply else "mlbwatch|"
        signature = sig_prefix + _hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        # 同一プレー重複ガード (2026-07-14): 引用RTの動画のみ対象。
        # 別プレーの動画は落とさない (選手単位の本数制限はしない)。
        if not as_reply and p["has_video"]:
            hr_no = _mlb_watch_hr_event_no(p["text"])
            if hr_no > 0:
                # 同じHR (選手×号数) は媒体・URL が違っても同じ signature に
                # なる → 便をまたいだ再掲も既存の dedup 台帳で止まる。
                signature = "mlbevt|" + _hashlib.sha1(
                    f"{player}|hr{hr_no}".encode("utf-8")
                ).hexdigest()[:16]
            elif same_play_window_min > 0 and p["published_at"] is not None:
                _near_dupe = any(
                    pl == player
                    and abs((p["published_at"] - ts).total_seconds())
                    <= same_play_window_min * 60.0
                    for pl, ts in accepted_video_times
                )
                if _near_dupe:
                    LOG.info(
                        "mlb_watch skip: same-play window player=%s handle=%s",
                        player, p["handle"],
                    )
                    continue
        if signature in used_signatures:
            continue
        if dedup_set is not None and signature in dedup_set:
            continue
        post_text = ""
        if comment_fn is not None:
            try:
                post_text = (comment_fn(p["text"], player) or "").strip()
            except Exception as exc:  # noqa: BLE001
                LOG.info("mlb_watch comment_fn failed: %r", exc)
                post_text = ""
        if not post_text:
            # voice が取れない候補はテンプレで埋めず skip (余計なポスト防止)。
            LOG.info(
                "mlb_watch skip: voice empty player=%s handle=%s",
                player, p["handle"],
            )
            continue
        # 2026-07-07 user「リプは相手の意見にもっとよりそって」: 返信 (empathy) は
        # 同意 first のため選手名 lead を強制しない。引用RTは従来通り名前 lead。
        if not as_reply:
            post_text = _ensure_player_name_leads_post_text(post_text, player)
        post_text = _cap_sentence(post_text, _video_post_char_cap())
        handle = p["handle"]
        if player == "大谷翔平":
            frame = "大谷別枠"
        elif player in _MLB_EXTRA_STARS:
            frame = "日本人スター"
        else:
            frame = "元巨人MLB"
        src_text = _truncate_text(p["text"].replace("\n", " ").strip(), 140)
        # 2026-07-03 user「出来れば動画。米国独特のスタッツ画像も引用したい」:
        # どちらの素材か mail 上でひと目で選べるようマーカーを出す。
        if p["has_video"]:
            media_mark = "🎬動画"
        elif p["has_media"]:
            media_mark = "🖼画像"
        else:
            media_mark = "📰記事"
        if as_reply:
            draft = "\n".join([
                f"【MLBリプ候補: {frame}】 @{handle}",
                f"対象選手: {player}",
                f"返信先 (タップで開く): {url}",
                f"元投稿本文: {src_text}",
                f"リプ文: {post_text}",
                "",
                "※ ボタンで返信画面が開く(リプ文入り)→ 投稿。"
                "MLB系アカの返信欄で露出=インプ近道。自動投稿はしない。",
            ])
            out.append(Candidate(
                title=f"💬 MLBリプ候補: {frame}｜@{handle}｜{player}",
                metric=_REPLY_CANDIDATE_METRIC,
                period_label="MLBリプ候補",
                draft_text=draft,
                char_count=len(post_text),
                signature=signature,
                post_text=post_text,
                focus_player=player,
                reply_to_id=tweet_id,
                why_now="MLB朝昼枠 (元巨人/大谷、返信欄で露出)",
                source_material_type="reply_candidate",
                reason_tags=("reply:mlb", "manual_only"),
                media_handle=handle.strip().lower(),
            ))
        else:
            draft = "\n".join([
                f"【MLB引用RT候補: {frame}】 @{handle}",
                f"対象選手: {player}",
                f"素材: {media_mark}付き投稿",
                f"▶ 元ツイート (タップで開く): {url}",
                f"元投稿本文: {src_text}",
                "",
                f"▼ コピペ用（このコメントだけ貼って引用RT / {len(post_text)}字）",
                post_text,
                "── ここまで貼る ──",
                "",
                "※ 動画/画像は引用RTでそのまま表示されインプが伸びる。ファイルの転載はしない。",
            ])
            out.append(Candidate(
                title=f"(MLB引用RT{media_mark[0]}) {frame}｜@{handle}｜{player}",
                metric=_MLB_WATCH_METRIC,
                period_label="MLB引用RT候補",
                draft_text=draft,
                char_count=len(post_text),
                signature=signature,
                post_text=post_text,
                focus_player=player,
                quote_url=url,
                why_now="MLB朝昼枠 (元巨人/大谷、午前〜午後がインプ強)",
                source_material_type="mlb_watch_post",
                media_handle=handle.strip().lower(),
            ))
        used_player_handles.add(player_handle_key)
        used_signatures.add(signature)
        if not as_reply and p["has_video"] and p["published_at"] is not None:
            accepted_video_times.append((player, p["published_at"]))
        player_counts[player] = player_counts.get(player, 0) + 1
        if not p["has_media"]:
            article_used += 1
        if player == "大谷翔平":
            ohtani_used += 1
            if p["has_video"]:
                ohtani_video_used += 1
        if player in _MLB_EXTRA_STARS:
            extra_star_used += 1
    LOG.info("mlb_watch: built %d candidates (as_reply=%s)", len(out), as_reply)
    return out


def build_live_game_candidates(
    *,
    now: Optional[datetime] = None,
    dedup_set: Optional[set[str]] = None,
    comment_fn=None,
    max_count: int = 2,
) -> list[Candidate]:
    """巨人戦ライブ実況候補 (2026-07-08 user GO / 2026-07-09 一球速報化)。

    NPB 一球速報 (playbyplay) の前便比の新規プレーから候補を作る。得点だけでなく
    長打 / 得点圏の好機 / 巨人投手の三振 / 併殺 / 出塁でも出す (投手戦でも沈黙しない)。
    - 事実行は NPB 公式表記の実名を束ねる (打者 + 投手 + 走者を作った打者 = 検索インプ源)。
    - voice が作れない時はテンプレに逃げず skip。
    - 名前ガード: 事実行に無い選手名が post に出たら捏造として reject。
    - 試合終了だけは playbyplay に出ないのでスコア state から補う。
    """
    from src import live_game_watch as lgw

    cur = lgw.fetch_today_live_game(now)
    if cur is None:
        return []
    date_key = cur.date_key
    # 展開ラベル (逆転/同点/勝ち越し) は前便 state 比のコード計算 (LLM に展開を
    # 読ませない、2026-07-10 user GO)。prev_state は ② の detect_events でも使う。
    prev_state = lgw.load_prev_state(date_key)
    transition = lgw.score_transition_label(prev_state, cur)
    score_ctx = f"巨人{cur.giants_score}-{cur.opp_score}{cur.opp_name}" + (
        f"（{transition}）" if transition else ""
    )

    # ① 一球速報ベースの新規プレー (トリガー低・複数選手束ね)
    plays = lgw.fetch_today_plays(now)
    events: list[dict] = []
    roster: set[str] = set()
    if plays:
        # 2026-07-10 user「検索インプ用に選手名を」: 巨人側の姓のみ表記を
        # roster で一意解決できる分だけフルネーム化 (泉口→泉口友汰)。
        plays = lgw.apply_fullname_map(plays, lgw.giants_fullname_map())
        roster = {p["batter"] for p in plays if p.get("batter")}
        roster |= {p["pitcher"] for p in plays if p.get("pitcher")}
        prev_cursor = lgw.load_play_cursor(date_key)
        events = lgw.detect_play_events(
            prev_cursor, plays, score_ctx=score_ctx, max_count=max_count
        )
        lgw.save_play_cursor(date_key, len(plays))

    # ② 試合終了はスコア state から (playbyplay には出ない)
    score_events = lgw.detect_events(prev_state, cur)
    lgw.save_state(cur)
    events += [e for e in score_events if e.get("kind") == "game_end"]

    if not events:
        return []

    def _fabricated_name(post: str, fact: str) -> str:
        for nm in roster:
            if nm and nm in post and nm not in fact:
                return nm
        return ""

    win = cur.giants_score > cur.opp_score
    losing = cur.giants_score < cur.opp_score
    out: list[Candidate] = []
    for ev in events[: max(0, max_count)]:
        is_recap = ev.get("kind") == "game_end"
        # 試合後 recap は巨人の活躍選手を実名で大量に束ねた fact に差し替える
        fact = (
            lgw.build_recap_fact(plays, cur.giants_score, cur.opp_score, cur.opp_name)
            if (is_recap and plays) else ev["fact"]
        )
        # 実名必須 gate (2026-07-10 user GO): 実名ゼロの事実行は候補にしない。
        # 実測で fav=0 だった唯一の観戦ポスト = 唯一の実名ゼロ文 (検索インプ源が無い)。
        if not any(nm and nm in fact for nm in roster):
            LOG.info("live_game skip: no player name in fact kind=%s", ev["kind"])
            continue
        signature = "livegame|" + _hashlib.sha1(
            f"{date_key}|{fact}".encode("utf-8")
        ).hexdigest()[:16]
        if dedup_set is not None and signature in dedup_set:
            continue
        post_text = ""
        if comment_fn is not None:
            try:
                post_text = (
                    comment_fn(fact, long=is_recap, losing=losing) or ""
                ).strip()
            except TypeError:  # comment_fn が kwarg 非対応 (後方互換)
                post_text = (comment_fn(fact) or "").strip()
            except Exception as exc:  # noqa: BLE001
                LOG.info("live_game comment_fn failed: %r", exc)
                post_text = ""
        if not post_text:
            LOG.info("live_game skip: voice empty kind=%s", ev["kind"])
            continue
        bad = _fabricated_name(post_text, fact)
        if bad:
            LOG.info("live_game skip: fabricated name=%s not in fact", bad)
            continue
        # claim 語 gate (2026-07-10 user GO): 事実行に無い場面 claim / 球種語は
        # 出力ごと破棄 (トレンド lane c3c62b25 と同型の決定的 gate)。
        bad_claim = lgw.find_unsupported_claim(post_text, fact)
        if bad_claim:
            LOG.info("live_game skip: unsupported claim=%s not in fact", bad_claim)
            continue
        if is_recap:
            # 勝=うさほー🐰👊グータッチ / 負=まけほー🐰 で開幕 (2026-07-09 user、絵文字はガード後に付与)
            opener = "うさほー🐰👊 グータッチ！\n\n" if win else "まけほー🐰\n\n"
            post_text = opener + post_text
        out.append(Candidate(
            title=f"⚾{'試合後recap' if is_recap else '実況候補'}｜{score_ctx}｜{cur.inning_label or '試合終了'}",
            metric="LIVE_GAME",
            period_label="実況",
            draft_text=f"{fact}\n(出典: NPB公式一球速報 {cur.game_url})",
            char_count=len(post_text),
            signature=signature,
            post_text=post_text,
            source_material_type="live_game",
        ))
    LOG.info("live_game: built %d candidates (events=%d, plays=%d)", len(out), len(events), len(plays))
    return out


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

    Batting metrics use 打席 (PA). Pitching metrics use 投球回 (IP).
    """
    if metric in _PITCHING_METRICS:
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


def _xpost_sample_floor(metric: str, period_label: str) -> int:
    """436: minimum sample for X-facing Top10 credibility.

    The upstream query may use a lower threshold to keep enough rows
    available. Public X candidates should still avoid rate tables that
    are driven by 1-2 plate appearances or a single relief outing.
    """
    if metric in _BATTING_METRICS:
        if period_label == "直近3試合":
            return 6
        if period_label == "直近5試合":
            return 10
        if period_label == "直近10試合":
            return 20
        if period_label == "直近20試合":
            return 30
        if period_label in {"直近1週間", "今週"}:
            return 10
        if period_label == "今月" or period_label.endswith("月成績"):
            return 30
    if metric in _PITCHING_METRICS:
        if period_label in {"直近3試合", "直近5試合", "直近10試合"}:
            return 3
        if period_label == "直近20試合":
            return 5
        if period_label == "今月" or period_label.endswith("月成績"):
            return 5
    return 0


def _effective_xpost_min_sample(metric: str, period_label: str, min_sample: int) -> int:
    floor = _xpost_sample_floor(metric, period_label)
    return max(int(min_sample or 0), floor)


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
        is_ranking = bool(_re.match(r"^\d+(?:\.|位)\s", line))
        if is_ranking:
            rank_seen += 1
            if rank_seen > top_n and "⭐巨人" not in line and "🟧巨人🟧" not in line:
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


def _db_table_fan_view_line(combo: _MetricCombo) -> str:
    """Return a short, low-temperature fan-view line for Source B tables."""
    if combo.position:
        return "数字で見ると、この比較は追いたい。"
    if combo.metric in {"ERA", "K_per_9", "BB_per_9", "HR_per_9"}:
        return "次の登板で見たい数字。"
    if combo.period_label in {"直近3試合", "直近5試合", "直近10試合", "直近1週間", "今週"}:
        return "この推移は追いたい。"
    return "数字で見るとここは期待したい。"


def _build_db_table_post_text(draft_text: str, combo: _MetricCombo) -> str:
    """429: keep the DB ranking table as the actual public post text.

    ``draft_text`` is already the 418 case B table.  Earlier versions put
    a branded prose paragraph in ``post_text`` and kept the table only as
    proof.  For Yoshilover X, Source B is the brand axis, so the table must
    survive in the X intent ``text=`` value.  The fan-view line is optional:
    add it only when it fits without truncating the table.
    """
    base = "\n".join(
        line for line in draft_text.strip().splitlines()
        if not line.strip().startswith("#")
    ).strip()
    if not base:
        return ""
    fan_line = _db_table_fan_view_line(combo)
    with_line = f"{base}\n{fan_line}"
    if len(with_line) <= X_CHAR_LIMIT:
        return with_line
    return base if len(base) <= X_CHAR_LIMIT else _finalize_post_text(base)


def _normalize_team_level(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw in {"first", "first_team", "ichi", "1", "npb", "central", "ce", "セ"}:
        return "first"
    if raw in {"farm2", "farm", "2", "2gun", "ni", "eastern", "western"}:
        return "farm2"
    if raw in {"farm3", "third", "third_team", "3", "3gun", "san"}:
        return "farm3"
    if raw in {"unknown", "不明"}:
        return "unknown"
    if any(term.lower() in raw for term in _THIRD_TEAM_TERMS):
        return "farm3"
    if any(term.lower() in raw for term in _FARM_TERMS):
        return "farm2"
    if "一軍" in raw or "1軍" in raw or "１軍" in raw:
        return "first"
    return ""


def _infer_team_level_from_text(text: str) -> str:
    if any(term in text for term in _THIRD_TEAM_TERMS):
        return "farm3"
    if any(term in text for term in _FARM_TERMS):
        return "farm2"
    if "一軍" in text or "1軍" in text or "１軍" in text:
        return "first"
    return ""


_TEAM_LEVEL_ROW_FIELDS = (
    "team_level",
    "league_level",
    "level",
    "league_label",
    "source_kind",
    "source_label",
    "competition",
    "scope",
)


def _row_team_level(row: dict) -> str:
    for key in _TEAM_LEVEL_ROW_FIELDS:
        level = _normalize_team_level(row.get(key))
        if level:
            return level
    haystack = " ".join(
        str(row.get(key) or "")
        for key in (
            "title",
            "label",
            "source_title",
            "league_label",
            "team_code",
            "team_name",
        )
    )
    return _infer_team_level_from_text(haystack) or "first"


def _candidate_team_level(candidate: Candidate) -> str:
    level = _normalize_team_level(candidate.team_level)
    if level:
        return level
    if _candidate_source_kind(candidate) not in {"B", "C"}:
        return ""
    haystack = " ".join(
        str(part or "")
        for part in (
            candidate.title,
            candidate.period_label,
            candidate.draft_text,
            candidate.post_text,
            candidate.source_material_type,
        )
    )
    return _infer_team_level_from_text(haystack) or "first"


def _row_sample_size(row: dict) -> Optional[int]:
    for key in ("sample_size", "sample", "pa", "PA", "ip", "IP"):
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _sample_size_for_candidate(candidate: Candidate) -> Optional[int]:
    if candidate.sample_size:
        return int(candidate.sample_size)
    return None


def _filter_first_team_rows(rows: list[dict], combo: _MetricCombo) -> list[dict]:
    kept: list[dict] = []
    for row in rows:
        level = _row_team_level(row)
        if level != "first":
            LOG.info(
                "team_level_separated metric=%s period=%s player=%s level=%s",
                combo.metric,
                combo.period_label,
                row.get("player_canonical"),
                level,
            )
            continue
        kept.append(row)
    return kept


def _filter_rows_by_xpost_sample_gate(
    rows: list[dict],
    combo: _MetricCombo,
    *,
    min_sample: int,
) -> list[dict]:
    floor = _effective_xpost_min_sample(combo.metric, combo.period_label, min_sample)
    if floor <= 0:
        return rows
    kept: list[dict] = []
    for row in rows:
        sample = _row_sample_size(row)
        if sample is None:
            LOG.info(
                "sample_unknown_keep metric=%s period=%s player=%s floor=%d",
                combo.metric,
                combo.period_label,
                row.get("player_canonical"),
                floor,
            )
            kept.append(row)
            continue
        if sample < floor:
            LOG.info(
                "sample_too_small_skip metric=%s period=%s player=%s sample=%d floor=%d",
                combo.metric,
                combo.period_label,
                row.get("player_canonical"),
                sample,
                floor,
            )
            continue
        kept.append(row)
    return kept


def _has_candidate_giants_row(
    rows: list[dict],
    *,
    focus_player_names: Optional[set[str]] = None,
) -> bool:
    return _top_giants_row(rows, focus_player_names=focus_player_names) is not None


def _is_safe_post_text(text: str) -> bool:
    if not text.strip():
        return False
    return not any(term in text for term in _FORBIDDEN_POST_TERMS)


def _candidate_post_text(candidate: Candidate) -> str:
    return candidate.post_text or candidate.draft_text


def _candidate_char_count(candidate: Candidate) -> int:
    return len(_candidate_post_text(candidate))


_SOURCE_A_METRICS = {
    _NEWS_OPINION_METRIC,
    _COMMENT_DB_METRIC,
    _FAN_VOICE_METRIC,
    _PLAYER_COMMENT_METRIC,
    _HOCHI_REPLY_METRIC,
    _REPLY_CANDIDATE_METRIC,
}
_DB_TABLE_REQUIRED_TOKENS = ("📊", "TOP", "巨人最上位", "🟧巨人🟧")
_SOURCE_C_CONDITION_TOKENS = ("規定", "条件", "対象", "sample", "サンプル", "打席", "登板", "投球回")
_SOURCE_C_SLICE_TOKENS = ("対左", "対右", "左右", "打順", "守備", "走者", "カウント", "状況", "起用")
_DATA_PRECISION_SOURCE_TYPES = frozenset(
    {
        "data_split",
        "win_correlation",
        "opponent_split",
        "alltime_chase",
        "weekly_mvp",
        "legend_compare",
        "pregame_preview",
        "salary_value",
        "milestone",
        "rarity",
        "roster_move",
        "on_this_day",
        "on_this_day_birthday",
    }
)
_DATA_PRECISION_FACT_REQUIRED = frozenset(
    {
        "data_split",
        "win_correlation",
        "opponent_split",
        "alltime_chase",
        "weekly_mvp",
        "legend_compare",
        "pregame_preview",
        "salary_value",
        "milestone",
        "rarity",
    }
)
_DATA_PRECISION_MIN_SAMPLE = {
    "data_split": 25,
    "win_correlation": 40,
    "opponent_split": 25,
    "weekly_mvp": 15,
    "legend_compare": 5,
    "pregame_preview": 1,
    "salary_value": 20,
    "roster_move": 1,
}
_DATA_PRECISION_MIN_GAP = {
    "win_correlation": 0.200,
    "opponent_split": 0.120,
}


def _parse_precision_decimal(raw: str) -> Optional[float]:
    token = (raw or "").strip()
    if not token:
        return None
    if token.startswith("."):
        token = "0" + token
    try:
        return float(token)
    except ValueError:
        return None


def _extract_precision_gap(fact: str) -> Optional[float]:
    """Extract ``差 +.200`` / ``勝率差 +.200`` style gap values."""
    matches = _re.findall(r"(?:勝率差|条件付き勝率差|差)\s*\+?\s*([0-9]*\.[0-9]+)", fact)
    if not matches:
        return None
    # Use the last match because data lines may contain multiple rates
    # before the final comparison delta.
    return _parse_precision_decimal(matches[-1])


def _fmt_precision_threshold(v: float) -> str:
    return f"{v:.3f}".lstrip("0")


def _data_precision_drop_reason(candidate: Candidate) -> str:
    """Return a hard-drop reason for thin data-angle X candidates."""
    source_type = (candidate.source_material_type or "").strip()
    if source_type not in _DATA_PRECISION_SOURCE_TYPES:
        return ""
    text = _candidate_post_text(candidate).strip()
    if not text:
        return "data_precision_empty_text"
    if len(text) > X_CHAR_LIMIT:
        return f"data_precision_over_280:{len(text)}"

    fact = (candidate.db_fact_line or "").strip()
    if source_type in _DATA_PRECISION_FACT_REQUIRED and not fact:
        return "data_precision_fact_missing"

    sample = _sample_size_for_candidate(candidate)
    floor = _DATA_PRECISION_MIN_SAMPLE.get(source_type, 0)
    if floor > 0:
        if sample is None:
            return f"data_precision_sample_unknown:floor={floor}"
        if sample < floor:
            return f"data_precision_sample_too_small:{sample}<{floor}"

    if source_type == "win_correlation" and (
        "勝率" not in fact or "条件付き勝率差" not in fact
    ):
        return "data_precision_win_corr_fact_weak"
    if source_type == "opponent_split" and (
        "安打/" not in fact or "他カード" not in fact
    ):
        return "data_precision_opp_split_fact_weak"
    gap_floor = _DATA_PRECISION_MIN_GAP.get(source_type)
    if gap_floor is not None:
        gap = _extract_precision_gap(fact)
        if gap is None:
            return f"data_precision_gap_missing:{source_type}"
        if gap < gap_floor:
            return (
                "data_precision_gap_too_small:"
                f"{_fmt_precision_threshold(gap)}<{_fmt_precision_threshold(gap_floor)}"
            )
    if source_type == "weekly_mvp" and ("打率" not in fact or "打数" not in fact):
        return "data_precision_weekly_mvp_fact_weak"
    return ""


def _candidate_source_kind(candidate: Candidate) -> str:
    if candidate.source_material_type == "specialized_db":
        return "C"
    if candidate.metric in _SOURCE_A_METRICS:
        return "A"
    return "B"


_SELECTED_REASON_LABELS = {
    "source_a_news": "RSS/コメント材料",
    "source_b_db_table": "DB表",
    "source_c_db_slice": "DB slice",
    "metric_family:batting": "打撃指標",
    "metric_family:pitching": "投手指標",
    "metric_family:fielding": "守備指標",
    "metric_family:news": "ニュース材料",
    "reply:hochi": "報知リプ",
    "manual_only": "手動投稿",
    "period:short_window": "短期変化",
    "period:monthly": "月別",
    "period:calendar": "カレンダー期間",
    "period:other": "期間あり",
    "first_team": "一軍",
    "sample_ok": "sample確認",
    "sample_checked": "sample確認",
    "sample_low_fallback": "低sample参考",
    "player_diversity": "選手分散",
    "fan_useful:central_rank": "セ順位で有用",
    "surprise:short_window": "短期の意外性",
}

_X_IMPRESSION_TIMING_LABELS = {
    "morning_catchup": "朝 catchup",
    "pregame_db": "試合前DBカード",
    "lineup": "スタメン/先発直後",
    "in_game_strong": "試合中強イベント枠",
    "postgame_peak": "試合後ピーク",
    "lunch_data": "昼データ枠",
    "afternoon_data": "午後データ枠",
    "standard": "通常データ枠",
}

EXTRA_GAME_DATE_ENV = "X_POST_MAIL_EXTRA_GAME_DATE"
EXTRA_GAME_START_ENV = "X_POST_MAIL_EXTRA_GAME_START"
EXTRA_GAME_END_ENV = "X_POST_MAIL_EXTRA_GAME_END"


def _parse_hhmm_to_minutes(value: str) -> Optional[int]:
    raw = (value or "").strip()
    if not raw:
        return None
    match = _re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def is_extra_game_window(now: datetime) -> bool:
    """Return True for a one-day day-game override window.

    Cloud Scheduler can add one-day 15-minute fires for irregular day games.
    This env gate lets those fires use the same "試合中" freshness/source
    rules as the regular 18:00-21:15 dense window without changing normal days.
    """
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    game_date = (os.environ.get(EXTRA_GAME_DATE_ENV) or "").strip()
    if not game_date or game_date != now_jst.date().isoformat():
        return False
    start = _parse_hhmm_to_minutes(os.environ.get(EXTRA_GAME_START_ENV, ""))
    end = _parse_hhmm_to_minutes(os.environ.get(EXTRA_GAME_END_ENV, ""))
    if start is None or end is None or end < start:
        return False
    minute_of_day = now_jst.hour * 60 + now_jst.minute
    return start <= minute_of_day <= end


def x_impression_timing_label(now: datetime) -> str:
    """Return the human-facing posting window label for the given JST time.

    This is intentionally schedule-agnostic: game existence is decided by
    the caller / scheduler, while this helper only labels the window that
    the current fire falls into.
    """
    if now.tzinfo is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)
    minute_of_day = now_jst.hour * 60 + now_jst.minute
    if is_extra_game_window(now_jst):
        return _X_IMPRESSION_TIMING_LABELS["in_game_strong"]
    if 4 * 60 <= minute_of_day < 8 * 60:
        return _X_IMPRESSION_TIMING_LABELS["morning_catchup"]
    if 11 * 60 <= minute_of_day < 13 * 60:
        return _X_IMPRESSION_TIMING_LABELS["lunch_data"]
    if 15 * 60 <= minute_of_day < 16 * 60:
        return _X_IMPRESSION_TIMING_LABELS["afternoon_data"]
    if 16 * 60 <= minute_of_day < 17 * 60 + 15:
        return _X_IMPRESSION_TIMING_LABELS["pregame_db"]
    if 17 * 60 + 15 <= minute_of_day < 19 * 60:
        return _X_IMPRESSION_TIMING_LABELS["lineup"]
    if 19 * 60 <= minute_of_day < 21 * 60 + 45:
        return _X_IMPRESSION_TIMING_LABELS["in_game_strong"]
    if 21 * 60 + 45 <= minute_of_day < 23 * 60 + 30:
        return _X_IMPRESSION_TIMING_LABELS["postgame_peak"]
    return _X_IMPRESSION_TIMING_LABELS["standard"]


def phase_freshness_max_age_hours(now: datetime) -> float:
    """451 (user 2026-06-01「48hは長い。試合中は即、試合前はその日」「全ポストでそうして」):
    動画 + 野球記事系 (news_opinion / fan_voice / tag_scrape) 全ポストの鮮度窓を試合フェーズで
    統一する。 試合中はライブ即時性、 試合前後はその日に寄せる。 データ系 (DB stats) は当日値
    なので対象外。"""
    label = x_impression_timing_label(now)
    L = _X_IMPRESSION_TIMING_LABELS
    if label == L["in_game_strong"]:
        return 0.5   # 試合中 = 即 (直近30分、 15分おき発火に合わせライブの今だけ)
    if label == L["postgame_peak"]:
        return 6.0   # 試合直後
    if label in (L["lineup"], L["pregame_db"]):
        return 12.0  # 試合前 = その日
    # 2026-07-15 user「昨晩の記事が14時に飛んできた」: 24h だと前夜の試合後
    # 記事が翌日の昼便まで「新鮮」扱いで残る。通常帯も 12h に締めて
    # 「その日のもの」だけを速報として扱う (朝 7 時便は前夜 19 時以降の
    # 試合後記事を一度だけ拾い、昼便以降には持ち越さない)。
    return 12.0      # 朝 / 昼 / 午後 / 通常 = 当日


def _video_comment_phase_hint(now: datetime) -> tuple[str, str]:
    """451 (user 2026-06-01): 動画引用RTコメントのトーンを試合フェーズで切り替えるための
    (phase_label, llm_hint) を返す。 トーンの中身は既存 ``_SYSTEM_PROMPT_YOSHILOVER`` の
    例1=試合後 / 例2=試合中 / 例3=試合前 に対応 (新トーン創作はしない)。"""
    label = x_impression_timing_label(now)
    L = _X_IMPRESSION_TIMING_LABELS
    if label == L["in_game_strong"]:
        return ("試合中", "いまは試合中。 ライブで今この瞬間に反応する熱量で。 "
                "勝敗の完了断定は避け『ここで踏ん張れば』『次の回次第』など流動的に。")
    if label == L["postgame_peak"]:
        return ("試合後", "いまは試合直後。 結果を噛み締める余韻と、 活躍した選手を讃えるトーンで。")
    if label in (L["lineup"], L["pregame_db"]):
        return ("試合前", "いまは試合前。 これからへの期待・ワクワク。 注目選手や先発への期待を込めて。")
    return ("通常", "落ち着いた振り返り・小ネタのトーンで。")


def _candidate_why_now(candidate: Candidate, now: datetime) -> str:
    timing = x_impression_timing_label(now)
    if candidate.why_now:
        return candidate.why_now
    source_kind = _candidate_source_kind(candidate)
    player = (candidate.focus_player or "").strip()
    subject = player or "巨人"
    if source_kind == "A":
        return f"{timing}: ニュース/コメントの鮮度がある"
    if source_kind == "C":
        return f"{timing}: {subject}の条件別データを1枚画像で見せられる"
    metric = _METRIC_LABELS_JP.get(candidate.metric, candidate.metric)
    period = candidate.period_label or "直近データ"
    return f"{timing}: {subject}の{period} {metric}を1枚画像で見せられる"


def _normalize_candidate_post_text(text: str) -> str:
    return _re.sub(r"\s+", "", text or "").lower()


def _candidate_post_text_hash(candidate: Candidate) -> str:
    normalized = _normalize_candidate_post_text(_candidate_post_text(candidate))
    if not normalized:
        return ""
    # 2026-07-15 user「巨人動画SNSが一番インプ。候補は同文コメントでも欲しい」:
    # 引用RT系は元投稿 (quote_url) が違えば別場面なので、同文コメントを理由に
    # 同メール内で落とさない。URL を hash に混ぜて別物として扱う。
    if candidate.metric == _VIDEO_RADAR_METRIC and (candidate.quote_url or "").strip():
        normalized = f"{normalized}|{candidate.quote_url.strip()}"
    return _hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _candidate_image_payload_hash(candidate: Candidate) -> str:
    payload = "|".join(
        (
            candidate.metric or "",
            candidate.period_label or "",
            candidate.focus_player or "",
            candidate.draft_text or "",
        )
    )
    normalized = _normalize_candidate_post_text(payload)
    if not normalized:
        return ""
    return _hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _candidate_topic_key(candidate: Candidate) -> str:
    player = _normalize_player_name(candidate.focus_player)
    metric = str(candidate.metric or "").strip()
    period = str(candidate.period_label or "").strip()
    if not player or not metric or not period:
        return ""
    key = f"{player}|{metric}|{period}"
    # 2026-07-02 user 決定: 媒体つき動画候補は (選手×媒体) 単位で topic 判定
    # (同一選手でも媒体が違えばインプが取れるため別 topic として残す)。
    handle = (candidate.media_handle or "").strip().lower()
    if metric == _VIDEO_RADAR_METRIC and handle:
        key = f"{key}|{handle}"
    return key


# 2026-06-29 user 決定: recent-player クールダウン (dedup_player_recent) を
# レーン群ごとに分離する。 レス/メディアで直近に出た選手が 動画・本人コメントの
# オリジナルを巻き添えで落とす問題への対処 (動画オリジナル 1 本 + メディアレス
# 1 本を同選手で両立)。
_ORIGINAL_LANE_METRICS = frozenset({_VIDEO_RADAR_METRIC, _PLAYER_COMMENT_METRIC})
_REPLY_LANE_METRICS = frozenset({_HOCHI_REPLY_METRIC, _REPLY_CANDIDATE_METRIC})


def _lane_group(metric: object) -> str:
    """Return the recent-player cooldown group for a candidate metric.

    "original" = 引用動画 + 本人/首脳陣コメント, "reply" = 報知/ファンリプ,
    "other" = データ速報など残り全部。 群をまたぐ既出では recent dedup を
    効かせない。
    """
    m = str(metric or "")
    if m in _ORIGINAL_LANE_METRICS:
        return "original"
    if m in _REPLY_LANE_METRICS:
        return "reply"
    return "other"


def apply_x_impression_policy(
    candidates: list[Candidate],
    *,
    now: Optional[datetime] = None,
    max_candidates: Optional[int] = None,
    recent_player_keys: Optional[set[str]] = None,
    recent_player_keys_by_group: Optional[dict[str, set[str]]] = None,
    recent_video_player_media: Optional[set[str]] = None,
) -> tuple[list[Candidate], list[tuple[Candidate, str]]]:
    """Apply final API-free X impression policy before composing mail.

    This is the concrete version of ``spec/x-impression-plan``:
    keep existing 437 media/share behavior, but gate final candidates by
    same-mail duplicates and annotate kept candidates with ``why_now``.

    ``recent_player_keys`` are normalized focus-player names already shown in
    recent mails (cross-run, all lanes). Pre-seeding them drops candidates for
    a player who was just mailed — this is the single choke point that stops
    the same hot player (buzz / comment / image / record lanes alike) from
    recurring in every hourly candidate mail. Reply-lane actions are exempt in
    legacy flat mode; per-group history still cools down repeats inside the
    reply group itself.

    ``recent_player_keys_by_group`` (2026-06-29): when provided, the recent
    gate is scoped per lane-group (original / reply / other) so a player shown
    recently in one group does not suppress candidates in another group. Falls
    back to the flat ``recent_player_keys`` set when ``None``.

    ``recent_video_player_media`` (2026-07-02 user 決定): "player|handle" keys
    of video/引用RT candidates mailed recently. When provided, video candidates
    with a ``media_handle`` use THIS media-aware set for the recent gate —
    同一選手でも媒体 (@handle) が違えば動画はインプが取れるので落とさない。
    ``None`` keeps the legacy player-level gate for videos.
    """
    if now is None:
        now = datetime.now(JST)
    limit = max_candidates if max_candidates is not None else len(candidates)
    limit = max(0, int(limit))
    kept: list[Candidate] = []
    dropped: list[tuple[Candidate, str]] = []
    seen_signatures: set[str] = set()
    seen_topics: set[str] = set()
    seen_text_hashes: set[str] = set()
    seen_image_hashes: set[str] = set()
    seen_players: set[str] = set()
    seen_video_media: set[str] = set()
    recent_players: set[str] = set(recent_player_keys or ())
    # per-group が渡されたら群ごとに recent 判定 (群をまたぐ既出では落とさない)。
    recent_by_group = recent_player_keys_by_group

    for candidate in candidates:
        reason = ""
        signature = (candidate.signature or "").strip()
        topic_key = _candidate_topic_key(candidate)
        text_hash = _candidate_post_text_hash(candidate)
        image_hash = _candidate_image_payload_hash(candidate)
        player_key = _normalize_player_name(candidate.focus_player)
        is_reply_metric = candidate.metric in {
            _HOCHI_REPLY_METRIC,
            _REPLY_CANDIDATE_METRIC,
        }
        # 2026-07-02 user 決定: 動画SNS (引用RT) は同一選手でも媒体が違えば残す。
        # 2026-07-07: MLB引用RT (mlb_watch_post) も動画中心 lane なので同扱い。
        media_key = ""
        if (
            candidate.metric in {_VIDEO_RADAR_METRIC, _MLB_WATCH_METRIC}
            and player_key
            and (candidate.media_handle or "").strip()
        ):
            media_key = f"{player_key}|{candidate.media_handle.strip().lower()}"
        if media_key and recent_video_player_media is not None:
            # 媒体つき動画候補は (選手×媒体) の media-aware recent 判定。
            recent_hit = media_key in recent_video_player_media
        elif recent_by_group is not None:
            recent_hit = player_key in recent_by_group.get(
                _lane_group(candidate.metric), frozenset()
            )
        else:
            recent_hit = player_key in recent_players
        reply_group_recent_hit = (
            is_reply_metric
            and recent_by_group is not None
            and recent_hit
        )
        data_precision_reason = _data_precision_drop_reason(candidate)
        if data_precision_reason:
            reason = data_precision_reason
        elif len(kept) >= limit:
            reason = "over_candidate_limit"
        elif signature and signature in seen_signatures:
            reason = "dedup_signature"
        elif topic_key and topic_key in seen_topics:
            reason = "dedup_player_metric_period"
        elif text_hash and text_hash in seen_text_hashes:
            reason = "dedup_post_text_hash"
        elif image_hash and image_hash in seen_image_hashes:
            reason = "dedup_image_payload_hash"
        elif (
            player_key
            and recent_hit
            and (not is_reply_metric or reply_group_recent_hit)
            and not candidate.history_exempt
        ):
            # 直近の毎時メールで既に出した選手は外す (井上・浦田 等が毎時連続
            # するのを止める)。 per-group 時は同じ群の既出のみで判定するので、
            # レス既出が動画/本人コメントのオリジナルを落とすことはない。
            # history_exempt (メジャー/移籍 級の高ニュース価値) は免除。
            reason = "dedup_player_recent"
        elif (
            media_key
            and media_key in seen_video_media
        ):
            # 同一選手×同一媒体の動画は同メールで 1 本 (媒体違いは下の exempt で残る)。
            reason = "dedup_player_in_mail"
        elif (
            player_key
            and player_key in seen_players
            and not is_reply_metric
            and not media_key
        ):
            # 2026-06-04 user 決定:「引用RT＋記事を1選手1件に。リプは残す」。
            # 旧 exemption から video_radar (引用RT) を外し、 引用RT と記事voice
            # (GEMMA_BRANDING) を同選手で 1 件に。 append 順で高シグナルな動画引用RT が
            # 先に来るので、 同選手では動画が優先的に残る。 報知リプ (HOCHI/REPLY) は
            # 返信欄用の別アクションなので exempt のまま残す。
            # 2026-07-02 user 決定の上書き: 媒体つき動画候補 (media_key あり) は
            # 選手単位では落とさず (選手×媒体) 単位で判定 (動画はインプが取れる)。
            reason = "dedup_player_in_mail"

        if reason:
            dropped.append((replace(candidate, dedup_reason=reason), reason))
            continue

        kept_candidate = replace(candidate, why_now=_candidate_why_now(candidate, now))
        kept.append(kept_candidate)
        if signature:
            seen_signatures.add(signature)
        if topic_key:
            seen_topics.add(topic_key)
        if text_hash:
            seen_text_hashes.add(text_hash)
        if image_hash:
            seen_image_hashes.add(image_hash)
        if player_key and candidate.metric not in {
            # 引用RT (video_radar) と記事voice は seen_players に登録 = 同選手で 1 件に。
            # 報知リプだけは登録せず exempt のまま (返信欄用の別アクションとして残す)。
            _HOCHI_REPLY_METRIC,
            _REPLY_CANDIDATE_METRIC,
        }:
            seen_players.add(player_key)
        if media_key:
            seen_video_media.add(media_key)
    return kept, dropped


def _candidate_metric_family_tag(candidate: Candidate) -> str:
    if candidate.metric in _BATTING_METRICS:
        return "metric_family:batting"
    if candidate.metric in _PITCHING_METRICS:
        return "metric_family:pitching"
    if candidate.metric in _FIELDING_METRICS:
        return "metric_family:fielding"
    if _candidate_source_kind(candidate) == "A":
        return "metric_family:news"
    return "metric_family:other"


def _candidate_period_tag(candidate: Candidate) -> str:
    label = candidate.period_label or ""
    if "直近" in label or label == "今週":
        return "period:short_window"
    if label == "今月" or label.endswith("月成績"):
        return "period:monthly"
    if label:
        return "period:other"
    return ""


def _dedupe_reason_tags(tags: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return tuple(out)


def _candidate_selected_reason_tags(candidate: Candidate) -> tuple[str, ...]:
    tags = list(candidate.reason_tags)
    source_kind = _candidate_source_kind(candidate)
    if source_kind == "A":
        tags.append("source_a_news")
    elif source_kind == "C":
        tags.append("source_c_db_slice")
    else:
        tags.append("source_b_db_table")
    tags.append(_candidate_metric_family_tag(candidate))
    period_tag = _candidate_period_tag(candidate)
    if period_tag:
        tags.append(period_tag)
    if _candidate_team_level(candidate) == "first":
        tags.append("first_team")
    if candidate.sample_size or candidate.sample_label:
        tags.append("sample_checked")
    if _normalize_player_name(candidate.focus_player):
        tags.append("player_diversity")
    return _dedupe_reason_tags(tags)


def _candidate_selected_reason_text(candidate: Candidate) -> str:
    if candidate.selected_reason:
        return candidate.selected_reason
    labels: list[str] = []
    for tag in _candidate_selected_reason_tags(candidate):
        labels.append(_SELECTED_REASON_LABELS.get(tag, tag))
    return " / ".join(labels)


def _with_selected_reason(candidate: Candidate) -> Candidate:
    return replace(candidate, selected_reason=_candidate_selected_reason_text(candidate))


def _selection_reason_summary(candidates: list[Candidate]) -> str:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for tag in _candidate_selected_reason_tags(candidate):
            if tag == "first_team":
                continue
            counts[tag] = counts.get(tag, 0) + 1
    if not counts:
        return "採用理由: none"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return "採用理由: " + " / ".join(
        f"{_SELECTED_REASON_LABELS.get(tag, tag)}={count}"
        for tag, count in ordered
    )


def _source_a_voice_flags(text: str) -> list[str]:
    # 2026-05-25 user 確定: ヨシラバー voice 短文化 (180-280→100-180 字)。
    # hard NG: <60 字 (極端に短い)、 warn: <100 字 (目標下限割れ)、
    # X over: >280 字 (X char limit 不変)。
    flags: list[str] = []
    public_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(text) < 60:
        flags.append("hard:source_a_under_60")
    elif len(text) < 100:
        flags.append("warn:source_a_under_100")
    if len(text) > X_CHAR_LIMIT:
        flags.append("hard:source_a_over_280")
    if not 2 <= len(public_lines) <= 3:
        flags.append(f"warn:source_a_line_count:{len(public_lines)}")
    return flags


def _source_c_slice_flags(text: str) -> list[str]:
    flags: list[str] = []
    if "巨人" not in text:
        flags.append("hard:source_c_giants_row_missing")
    if not any(token in text for token in _SOURCE_C_CONDITION_TOKENS):
        flags.append("hard:source_c_sample_condition_missing")
    if not any(token in text for token in _SOURCE_C_SLICE_TOKENS):
        flags.append("warn:source_c_slice_label_missing")
    if len(text) > X_CHAR_LIMIT:
        flags.append("hard:source_c_over_280")
    return flags


def _team_level_flags(candidate: Candidate) -> list[str]:
    if _candidate_source_kind(candidate) not in {"B", "C"}:
        return []
    level = _candidate_team_level(candidate)
    if level == "first" or not level:
        return []
    if level == "farm2":
        return ["hard:team_level_farm2_separated"]
    if level == "farm3":
        return ["hard:team_level_farm3_separated"]
    if level == "unknown":
        return ["hard:team_level_unknown"]
    return [f"hard:team_level_unsupported:{level}"]


def _sample_gate_flags(candidate: Candidate) -> list[str]:
    if _candidate_source_kind(candidate) not in {"B", "C"}:
        return []
    floor = _xpost_sample_floor(candidate.metric, candidate.period_label)
    if floor <= 0:
        return []
    sample = _sample_size_for_candidate(candidate)
    if sample is None:
        return [f"warn:sample_unknown:floor={floor}"]
    if sample < floor:
        return [f"hard:sample_too_small:{sample}<{floor}"]
    return []


def _candidate_anomaly_flags(candidate: Candidate) -> list[str]:
    """434 phase 1: deterministic flags only, no ML and no live calls."""
    text = _candidate_post_text(candidate)
    flags: list[str] = []
    for term in _FORBIDDEN_POST_TERMS:
        if term in text:
            flags.append(f"hard:ng_word:{term}")
            break

    source_kind = _candidate_source_kind(candidate)
    if source_kind == "A":
        flags.extend(_source_a_voice_flags(text))
    if source_kind == "B":
        missing = [token for token in _DB_TABLE_REQUIRED_TOKENS if token not in text]
        if missing:
            flags.append("hard:source_b_table_token_missing:" + ",".join(missing))
        if "どう見ますか" in text or "数字だけで語り切る" in text:
            flags.append("hard:source_b_prose_overwrite")
    if source_kind == "C":
        flags.extend(_source_c_slice_flags(text))
    flags.extend(_team_level_flags(candidate))
    flags.extend(_sample_gate_flags(candidate))
    return flags


def _source_mix_summary(candidates: list[Candidate]) -> tuple[list[str], list[str]]:
    counts = {"A": 0, "B": 0, "C": 0}
    level_counts = {"first": 0, "farm2": 0, "farm3": 0, "unknown": 0}
    player_counts: dict[str, int] = {}
    metric_counts: dict[str, int] = {}
    period_counts: dict[str, int] = {}
    warning_flags: list[str] = []
    hard_flags: list[str] = []
    for idx, candidate in enumerate(candidates, start=1):
        kind = _candidate_source_kind(candidate)
        counts[kind] = counts.get(kind, 0) + 1
        if kind in {"B", "C"}:
            level = _candidate_team_level(candidate) or "unknown"
            level_counts[level] = level_counts.get(level, 0) + 1
            player_key = _normalize_player_name(candidate.focus_player)
            if player_key:
                player_counts[player_key] = player_counts.get(player_key, 0) + 1
            if candidate.metric:
                metric_counts[candidate.metric] = metric_counts.get(candidate.metric, 0) + 1
            if candidate.period_label:
                period_counts[candidate.period_label] = period_counts.get(candidate.period_label, 0) + 1
        for flag in _candidate_anomaly_flags(candidate):
            label = f"候補{idx}:{flag}"
            if flag.startswith("hard:"):
                hard_flags.append(label)
            else:
                warning_flags.append(label)

    total = len(candidates)
    if total < 5:
        warning_flags.append(f"candidate_count_low:{total}")
    if total > 8:
        warning_flags.append(f"candidate_count_high:{total}")
    if total and counts["B"] <= total / 2:
        warning_flags.append(f"source_b_ratio_low:{counts['B']}/{total}")
    duplicate_players = {k: v for k, v in player_counts.items() if v > 1}
    duplicate_metrics = {k: v for k, v in metric_counts.items() if v > 2}
    duplicate_periods = {k: v for k, v in period_counts.items() if v > 3}
    if duplicate_players:
        warning_flags.append(
            "duplicate_player:" + ",".join(
                f"{name}x{count}" for name, count in sorted(duplicate_players.items())
            )
        )
    if duplicate_metrics:
        warning_flags.append(
            "duplicate_metric:" + ",".join(
                f"{name}x{count}" for name, count in sorted(duplicate_metrics.items())
            )
        )
    if duplicate_periods:
        warning_flags.append(
            "duplicate_period:" + ",".join(
                f"{name}x{count}" for name, count in sorted(duplicate_periods.items())
            )
        )

    lines = [
        f"Source構成: A(RSS観戦)={counts['A']} / B(DB表)={counts['B']} / C(DB slice)={counts['C']} / total={total}",
        (
            "Data構成: "
            f"first={level_counts.get('first', 0)} / "
            f"farm2={level_counts.get('farm2', 0)} / "
            f"farm3={level_counts.get('farm3', 0)} / "
            f"unknown={level_counts.get('unknown', 0)}"
        ),
        _selection_reason_summary(candidates),
    ]
    if warning_flags:
        lines.append("flags: " + "; ".join(warning_flags))
    if hard_flags:
        lines.append("hard_drop_candidates: " + "; ".join(hard_flags))
    return lines, warning_flags + hard_flags


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


def _dedup_blob_prefix(date_str: str) -> str:
    """その日の dedup record blob 群の共通 prefix。

    2026-07-07: 便の同時発火 (毎時:00/:05 + 試合中15分毎) で read+concat+
    re-upload が競合し record が消えていた (実測: load 件数が 509→505 に後退)。
    書き込みを「便ごとの一意 blob」に変え、読みは prefix 一覧で新旧両形式
    (``{date}.jsonl`` 旧 / ``{date}_HHMMSS_xxx.jsonl`` 新) を拾う。
    """
    return f"x_post_mail/dedup/{date_str}"


def _load_recent_dedup_records(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 168,
) -> list[dict]:
    """355 / 441: read JSONL files in ``gs://{bucket_name}/x_post_mail/dedup/``
    for the days covering ``lookback_hours`` (default 168h = 7d) and filter
    to records with ``ts >= now - lookback_hours``.

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
    # 441: cover lookback_hours days back (ceil + 1 safety day for JST boundary).
    days_back = max(1, (int(lookback_hours) + 23) // 24 + 1)
    date_strs = [
        (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days_back)
    ]
    out: list[dict] = []
    for date_str in date_strs:
        # 2026-07-07: 旧 day-file (``{date}.jsonl``) と新 per-run blob
        # (``{date}_HHMMSS_xxx.jsonl``) の両方を prefix 一覧で読む。
        try:
            blobs = list(bucket.list_blobs(prefix=_dedup_blob_prefix(date_str)))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("_load_recent_dedup_records: list %s failed: %r",
                        date_str, exc)
            continue
        for blob in blobs:
            try:
                content = blob.download_as_text()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("_load_recent_dedup_records: read %s failed: %r",
                            getattr(blob, "name", date_str), exc)
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
    lookback_hours: int = 168,
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


def _players_within_cooldown(
    records: list[dict],
    now: datetime,
    cooldown_hours: float,
) -> set[str]:
    """Return normalized focus-player keys posted within ``cooldown_hours``.

    Used to suppress LLM branding generation for a player who was just posted
    (during a game or the next day). Many media cover the same hot player, so
    without a per-player cooldown the same player would be re-generated each
    run and the Gemini cost is wasted on posts that will not be published.
    ``cooldown_hours <= 0`` disables the gate (returns an empty set).
    """
    if cooldown_hours <= 0:
        return set()
    cutoff = now - timedelta(hours=cooldown_hours)
    recent: set[str] = set()
    for rec in records:
        player_key = _normalize_player_name(rec.get("focus_player"))
        if not player_key:
            continue
        ts_str = rec.get("ts") or ""
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            # Treat naive timestamps as JST per project convention.
            ts = ts.replace(tzinfo=JST)
        if ts >= cutoff:
            recent.add(player_key)
    return recent


def _players_within_cooldown_by_group(
    records: list[dict],
    now: datetime,
    cooldown_hours: float,
) -> dict[str, set[str]]:
    """Like ``_players_within_cooldown`` but split per lane-group.

    Returns ``{"original": set, "reply": set, "other": set}`` keyed by
    ``_lane_group(rec["metric"])``. Used so a player shown recently in one
    lane-group does not suppress candidates in another group (レス既出が
    動画/本人コメントのオリジナルを落とさない)。
    """
    groups: dict[str, set[str]] = {
        "original": set(),
        "reply": set(),
        "other": set(),
    }
    if cooldown_hours <= 0:
        return groups
    cutoff = now - timedelta(hours=cooldown_hours)
    for rec in records:
        player_key = _normalize_player_name(rec.get("focus_player"))
        if not player_key:
            continue
        ts_str = rec.get("ts") or ""
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            # Treat naive timestamps as JST per project convention.
            ts = ts.replace(tzinfo=JST)
        if ts >= cutoff:
            groups[_lane_group(rec.get("metric"))].add(player_key)
    return groups


def _video_player_media_within_cooldown(
    records: list[dict],
    now: datetime,
    cooldown_hours: float,
) -> set[str]:
    """2026-07-02 user 決定: 動画/引用RT lane の media-aware recent set。

    直近 ``cooldown_hours`` に送った video 候補の "player|handle" key を返す。
    同一選手でも媒体 (@handle) が違えば動画はインプが取れるので落とさない —
    この set に (選手×媒体) が居る時だけ recent 落ちさせる。
    media_handle の無い旧 record は key を作れないため対象外 (URL signature の
    完全一致 dedup は別途効いている)。
    """
    out: set[str] = set()
    if cooldown_hours <= 0:
        return out
    cutoff = now - timedelta(hours=cooldown_hours)
    # 2026-07-07 user「MLBのおりポスが少ない」「とくに動画でみせたい」: MLB引用RT
    # (mlb_watch_post) も動画引用RT lane なので同じ (選手×媒体) 判定に含める
    # (大谷動画が 12h player cooldown で 1 本/12h に絞られていた)。
    _media_aware_metrics = {_VIDEO_RADAR_METRIC, _MLB_WATCH_METRIC}
    for rec in records:
        if str(rec.get("metric") or "") not in _media_aware_metrics:
            continue
        player_key = _normalize_player_name(rec.get("focus_player"))
        handle = str(rec.get("media_handle") or "").strip().lower()
        if not player_key or not handle:
            continue
        ts_str = rec.get("ts") or ""
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=JST)
        if ts >= cutoff:
            out.add(f"{player_key}|{handle}")
    return out


def _load_recent_player_counts(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 168,
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
    media_handles: Optional[list[str]] = None,
) -> bool:
    """355: record signatures as a per-run JSONL blob on GCS. Returns
    ``True`` on success, ``False`` on any error. Failures are logged and
    never abort the calling flow.

    2026-07-07: 旧実装は day-file への read+concat+re-upload で、便の同時
    発火 (毎時:00/:05 + 試合中15分毎) に record が消えていた (実測 509→505)。
    便ごとの一意 blob 書き込みへ変更し、read-modify-write 競合を無くす。
    読み側は :func:`_dedup_blob_prefix` の一覧で新旧両形式を拾う。
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
        if media_handles is not None and idx < len(media_handles):
            handle = str(media_handles[idx] or "").strip().lower()
            if handle:
                rec["media_handle"] = handle
        new_records.append(rec)
    new_lines = [_json.dumps(rec, ensure_ascii=False) for rec in new_records]
    new_block = "\n".join(new_lines) + "\n"
    # 便ごとの一意 blob 名: 時刻 + 内容 hash (同秒の別便でも内容が違えば別名)。
    run_suffix = _hashlib.sha1(new_block.encode("utf-8")).hexdigest()[:8]
    blob = bucket.blob(
        f"{_dedup_blob_prefix(date_str)}_{now.strftime('%H%M%S')}_{run_suffix}.jsonl"
    )
    try:
        blob.upload_from_string(
            new_block,
            content_type="application/x-jsonlines",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_record_dedup_signatures: upload failed: %r", exc)
        return False


# ── LLM 窓内消費台帳 (2026-07-14 user GO「残高連動の自動配分 + 枯渇通知」) ──
# Gemini 無料枠の窓 (16:00 JST リセット) 内の呼び出し数を GCS に記録し、
# 便ごとに「残り枠 ÷ 残り時間」で per-fire 予算を自動計算する。
# 書き込みは dedup 台帳と同じ per-run 一意 blob (read-modify-write 競合なし)。
# 台帳不達時は従来の固定 cap にそのまま落ちる (mail を止めない)。


def _llm_quota_window_key(now: datetime) -> str:
    """無料枠の窓 key。窓は 16:00 JST 起点なので、16 時前は前日扱い。"""
    local = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    if local.hour < 16:
        local = local - timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def _llm_quota_blob_prefix(window_key: str) -> str:
    return f"x_llm_quota/{window_key}/"


def _llm_quota_minutes_left(now: datetime) -> float:
    """窓末 (次の 16:00 JST) までの残り分。"""
    local = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
    reset = local.replace(hour=16, minute=0, second=0, microsecond=0)
    if local >= reset:
        reset += timedelta(days=1)
    return max(1.0, (reset - local).total_seconds() / 60.0)


def load_llm_window_usage(bucket_name: str, now: datetime) -> Optional[int]:
    """窓内の記録済み LLM 呼び出し数合計。台帳不達は None (pacing 無効化)。"""
    if not bucket_name:
        return None
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        prefix = _llm_quota_blob_prefix(_llm_quota_window_key(now))
        total = 0
        for blob in bucket.list_blobs(prefix=prefix):
            if blob.name.endswith("DEAD.json"):
                continue
            try:
                rec = _json.loads(blob.download_as_text())
                total += int(rec.get("calls") or 0)
            except Exception:  # noqa: BLE001 - 壊れた blob は読み飛ばす
                continue
        return total
    except Exception as exc:  # noqa: BLE001
        LOG.warning("load_llm_window_usage failed (pacing off this run): %r", exc)
        return None


def record_llm_window_usage(
    bucket_name: str, now: datetime, calls: int, label: str
) -> bool:
    """run の LLM 呼び出し数を窓台帳へ記録。calls<=0 は書かない。"""
    if not bucket_name or calls <= 0:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        window_key = _llm_quota_window_key(now)
        local = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
        rec = {"ts": local.isoformat(), "calls": int(calls), "job": label}
        body = _json.dumps(rec, ensure_ascii=False)
        suffix = _hashlib.sha1(body.encode("utf-8")).hexdigest()[:8]
        blob = bucket.blob(
            f"{_llm_quota_blob_prefix(window_key)}"
            f"{local.strftime('%H%M%S')}_{suffix}.json"
        )
        blob.upload_from_string(body, content_type="application/json")
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("record_llm_window_usage failed: %r", exc)
        return False


def llm_window_dead_marked(bucket_name: str, now: datetime) -> bool:
    """この窓で「全モデル日次枠切れ」マークが立っているか。"""
    if not bucket_name:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(
            f"{_llm_quota_blob_prefix(_llm_quota_window_key(now))}DEAD.json"
        )
        return bool(blob.exists())
    except Exception as exc:  # noqa: BLE001
        LOG.warning("llm_window_dead_marked check failed: %r", exc)
        return False


def mark_llm_window_dead(bucket_name: str, now: datetime, reason: str) -> bool:
    """窓の枠切れマークを書く。新規に書けた時だけ True (通知 mail は 1 回)。"""
    if not bucket_name:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(
            f"{_llm_quota_blob_prefix(_llm_quota_window_key(now))}DEAD.json"
        )
        if blob.exists():
            return False
        local = now.astimezone(JST) if now.tzinfo else now.replace(tzinfo=JST)
        blob.upload_from_string(
            _json.dumps(
                {"ts": local.isoformat(), "reason": reason}, ensure_ascii=False
            ),
            content_type="application/json",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("mark_llm_window_dead failed: %r", exc)
        return False


def paced_llm_fire_budget(
    remaining: int,
    now: datetime,
    *,
    fire_interval_min: float,
    static_cap: int,
    floor: int = 2,
    window_quota: int = 0,
) -> int:
    """窓の残り枠から、この便の LLM 予算を返す (ガードレール型)。

    - **on-track なら絞らない**: 残り枠の割合 >= 窓の残り時間の割合 の間は
      固定 cap をそのまま返す。窓の頭 (夜試合帯) はフル予算で走る
      (2026-07-14 user「厳しすぎて出なくなるのはやめて」)。
    - 消費が時間より先行した時だけ、「残り枠 × (便間隔 ÷ 残り時間)」の
      等配分へ切り替える。固定 cap が上限、``floor`` が下限
      (枠が残る限り便を全滅させない)。
    - remaining<=0 は 0 (この便は LLM を呼ばない)。
    """
    if static_cap <= 0:
        return static_cap
    if remaining <= 0:
        return 0
    minutes_left = _llm_quota_minutes_left(now)
    if window_quota > 0:
        frac_left = minutes_left / (24.0 * 60.0)
        if remaining >= window_quota * frac_left:
            return static_cap
    share = remaining * (float(fire_interval_min) / max(minutes_left, float(fire_interval_min)))
    return min(static_cap, max(min(floor, remaining), int(share)))


def _format_one(
    combo: _MetricCombo,
    rows: list[dict],
    *,
    min_sample: int,
    now: datetime,
    focus_player_names: Optional[set[str]] = None,
    avoid_player_names: Optional[set[str]] = None,
    context_label: str = "",
    sample_gate_relaxed: bool = False,
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
    effective_xpost_min_sample = _effective_xpost_min_sample(
        combo.metric,
        combo.period_label,
        min_sample,
    )
    base_threshold_label = _sample_threshold_label(combo.metric, effective_xpost_min_sample)
    threshold_label = (
        f"参考値・通常目安={base_threshold_label}"
        if sample_gate_relaxed
        else base_threshold_label
    )
    period_suffix = f"（{period_label}・{threshold_label}）"
    metric_jp = _METRIC_LABELS_JP.get(combo.metric, combo.metric)
    header_emoji = _METRIC_HEADER_EMOJI.get(combo.metric, "📊")
    focus_rank = focus_row.get("rank")
    focus_total = focus_row.get("total") or len(rows)
    focus_name = focus_row.get("player_canonical") or "巨人選手"
    scope_label = _scope_label(combo)
    fact_metric_label = metric_jp

    # 351+353 follow-up: 守備位置別 / セ・リーグ ranking で header の prefix を切替。
    # X インプ向上 Phase 3 (2026-05-27): format_as_x_post output は
    # "📊 セ {metric_jp} TOP{N} {emoji}" 形式。 position は _build_header 側で
    # すでに反映済 (`📊 セ 投手 ERA TOP10 ⚡`)。 旧 ランキング 文字列前提の
    # header rewrite は dead code だったため削除。 header 行は「📊」 を marker
    # に検索し、 period_suffix / focus_line をその直後に挿入する。
    if combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        fact_metric_label = f"{position_jp}{metric_jp}"
    header_idx = next((i for i, line in enumerate(lines) if "📊" in line), -1)
    context_prefix = f"{context_label} " if context_label else ""
    title = (
        f"{_angle_for_combo(combo)[0]} Xポスト案｜"
        f"{context_prefix}{focus_name} {metric_jp} {scope_label} {focus_rank}/{focus_total}位 "
        f"({period_label}・{threshold_label})"
    )
    # 353: period_suffix と focus_line を header の直後に挿入。
    # X インプ向上 Phase 3: hook line がある時は header_idx は 2 行目 (line[2])、
    # 無い時は 0 行目。 どちらでも header_idx+1 / +2 に挿入で同じ semantics。
    focus_line_prefix = context_label or "巨人最上位"
    focus_line = f"{focus_line_prefix}: {focus_name} {scope_label} {focus_rank}/{focus_total}位"
    if header_idx >= 0:
        lines.insert(header_idx + 1, period_suffix)
        lines.insert(header_idx + 2, focus_line)
    else:
        # 念のため fallback (format_as_x_post output が前提崩れの場合)
        lines.insert(1, period_suffix)
        lines.insert(2, focus_line)

    # 353: ranking rows に medal / metric label / strong Giants marker を post-process。
    lines = _rewrite_ranking_rows(lines, metric_jp)

    draft_text = "\n".join(lines)
    # 353: 280 字 cap を超えたら top 5 まで cut (rows-only trim)、 それでも
    # 超過なら最終手段として末尾 truncation + … で安全網。
    if len(draft_text) > X_CHAR_LIMIT:
        draft_text = _truncate_to_x_limit_top_n(draft_text, top_n=5)
        if len(draft_text) > X_CHAR_LIMIT:
            draft_text = draft_text[: X_CHAR_LIMIT - 1] + "…"
    post_text = _build_db_table_post_text(draft_text, combo)
    if not _is_safe_post_text(post_text):
        LOG.warning(
            "unsafe Source B table X post text skipped for %s/%s",
            combo.metric,
            combo.period_label,
        )
        post_text = ""
    # data 投稿も先頭に 【選手名】 を付与 (focus_name が「巨人選手」fallback / 未検証なら helper 内 skip)
    post_text = _prepend_focus_player_tag(post_text, focus_name)
    value_text = f"{metric_jp} {_format_metric_value(combo.metric, focus_row.get('metric_value'))}"
    db_fact_line = (
        f"{focus_name}は{period_label}の{fact_metric_label}で"
        f"{scope_label} {focus_rank}/{focus_total}位"
        f"（{value_text}、{threshold_label}）"
    )
    reason_tags = (
        "first_team",
        "fan_useful:central_rank",
        "surprise:short_window"
        if ("直近" in combo.period_label or combo.period_label == "今週")
        else "",
        "sample_low_fallback" if sample_gate_relaxed else "sample_ok",
    )
    candidate = Candidate(
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
        team_level="first",
        sample_size=_row_sample_size(focus_row) or 0,
        sample_label=threshold_label,
        reason_tags=_dedupe_reason_tags(list(reason_tags)),
    )
    return _with_selected_reason(candidate)


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
    # 2026-06-12 user 方針「驚きのない数字は出す意味がない」(効果学習 v0 実測:
    # 直近7日打率 voice 投稿 ♥0-1 vs 【】驚き角度 ♥3-5)。 DB ランキング combo 系
    # 候補 (直近N日/N試合 打率等) を env で止める kill switch。 驚き gate を持つ
    # data_angles (キラー/歴代チェイス/勝利相関) は別 builder のため影響しない。
    # default "1" = 従来挙動 (テスト互換)、 prod job env は "0" で停止。
    if (os.environ.get("X_POST_MAIL_DB_RANKING_ENABLED") or "1").strip() == "0":
        LOG.info(
            "db_ranking candidates disabled via X_POST_MAIL_DB_RANKING_ENABLED=0"
        )
        return []
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
        rows = _filter_first_team_rows(rows, combo)
        first_team_rows = rows
        sample_strict_rows = _filter_rows_by_xpost_sample_gate(
            first_team_rows,
            combo,
            min_sample=effective_min_sample,
        )
        sample_gate_relaxed = False
        strict_rows_enough = len(sample_strict_rows) >= min_central_rows
        strict_has_giants = _has_candidate_giants_row(
            sample_strict_rows,
            focus_player_names=focus_names,
        )
        if not strict_rows_enough:
            LOG.info(
                "sample_gate_hard_skip metric=%s period=%s reason=too_few_sample_rows "
                "strict_rows=%d required=%d first_team_rows=%d",
                combo.metric,
                combo.period_label,
                len(sample_strict_rows),
                min_central_rows,
                len(first_team_rows),
            )
            continue
        if not strict_has_giants:
            fallback_top = _top_giants_row(
                first_team_rows,
                focus_player_names=focus_names,
            )
            if (
                sample_strict_rows != first_team_rows
                and fallback_top is not None
            ):
                LOG.info(
                    "sample_gate_hard_skip metric=%s period=%s player=%s "
                    "reason=focus_row_below_sample_floor strict_rows=%d first_team_rows=%d",
                    combo.metric,
                    combo.period_label,
                    fallback_top.get("player_canonical"),
                    len(sample_strict_rows),
                    len(first_team_rows),
                )
            else:
                LOG.info(
                    "sample_gate_hard_skip metric=%s period=%s reason=no_sample_qualified_giants "
                    "strict_rows=%d first_team_rows=%d",
                    combo.metric,
                    combo.period_label,
                    len(sample_strict_rows),
                    len(first_team_rows),
                )
            continue
        rows = sample_strict_rows
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
            sample_gate_relaxed=sample_gate_relaxed,
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

    Per 382 系 rule and Codex review (2026-05-22): no URL, no hashtag,
    no site link appended — pure text= only. X intent params cannot
    force a posting account; account selection is the user's
    responsibility (browser session / X app default / composer switch).

    ``urllib.parse.quote`` with ``safe=""`` encodes every non-RFC3986-
    unreserved char including ``#`` (so it is not parsed as a fragment)
    and ``&`` (so it does not truncate the query string).
    """
    encoded = _url_quote(text or "", safe="")
    return f"{_X_INTENT_URL_BASE}?text={encoded}"


def encode_x_quote_intent_url(text: str, quote_url: str) -> str:
    """引用RT 用 X Web Intent URL。 ``text`` (コメント) + ``url`` (引用元ツイート) を
    付け、 X の compose を「引用ツイート (quote)」として開く (半自動: user が投稿を押すだけ)。

    382 系の text-only rule は新規投稿向け。 ここは引用元ツイート = X-native な quote
    であり外部リンクではないため url= を付ける (x_buzz_post 候補のみで使用)。
    """
    enc_text = _url_quote(text or "", safe="")
    enc_url = _url_quote(quote_url or "", safe="")
    return f"{_X_INTENT_URL_BASE}?text={enc_text}&url={enc_url}"


def encode_x_reply_intent_url(text: str, tweet_id: str) -> str:
    """リプライ用 X Web Intent URL。 ``in_reply_to`` で対象 tweet への返信として開く
    (text=ヨシラバー声のリプ文)。 大手投稿に返信=大観客に露出 (インプ近道)。 半自動。"""
    enc_text = _url_quote(text or "", safe="")
    tid = _url_quote(str(tweet_id or ""), safe="")
    return f"{_X_INTENT_URL_BASE}?text={enc_text}&in_reply_to={tid}"


# ---------------------------------------------------------------------------
# Mail composition
# ---------------------------------------------------------------------------


def time_band_label(hour: int) -> str:
    for hr_range, label in _TIME_BANDS:
        if hour in hr_range:
            return label
    return "夜"  # fall-through (should not happen with TIME_BANDS coverage)


def _subject_purpose_label(now: datetime, band: str, context_label: str) -> str:
    if context_label:
        return context_label
    timing = x_impression_timing_label(now)
    if timing not in {
        _X_IMPRESSION_TIMING_LABELS["standard"],
        _X_IMPRESSION_TIMING_LABELS["morning_catchup"],
    }:
        return timing
    return _TIME_BAND_PURPOSE.get(band, "Xポスト案")


def build_subject(
    now: datetime,
    n_candidates: int,
    *,
    context_label: str = "",
) -> str:
    band = time_band_label(now.hour)
    band_emoji = _TIME_BAND_EMOJI.get(band, "")
    purpose = _subject_purpose_label(now, band, context_label)
    return (
        f"🟠🐦📮【Xポスト案 {n_candidates}件】"
        f"{band_emoji}{band}｜{purpose} {now.strftime('%H:%M')} JST"
    )


_NEWS_DERIVED_METRICS = frozenset(
    {
        _NEWS_OPINION_METRIC,
        _COMMENT_DB_METRIC,
        _FAN_VOICE_METRIC,
        _PLAYER_COMMENT_METRIC,
        _GEMINI_BRANDING_METRIC,
        _HOCHI_REPLY_METRIC,
        _REPLY_CANDIDATE_METRIC,
    }
)


def _has_news_opinion_candidate(candidates: list[Candidate]) -> bool:
    # 仕様: 画像 (= DB ranking) のある候補だけを「巨人データXポスト案」と
    # 呼ぶ。 news 派生 (NEWS_OPINION / COMMENT_DB / FAN_VOICE /
    # GEMMA_BRANDING) は draft_text に ranking 行が無く画像生成 skip
    # されるため、 1 件でも混ざれば「巨人Xポスト案」表示に倒す。
    return any(c.metric in _NEWS_DERIVED_METRICS for c in candidates)


def _mail_header_label(candidates: list[Candidate]) -> str:
    if _has_news_opinion_candidate(candidates):
        return "巨人Xポスト案"
    return "巨人データXポスト案"


_DROPPED_REASON_JA = {
    "over_candidate_limit": "候補上限超え",
    "dedup_signature": "重複 (signature)",
    "dedup_player_metric_period": "重複 (同選手×同指標×同期間)",
    "dedup_post_text_hash": "重複 (本文 hash)",
    "dedup_image_payload_hash": "重複 (画像 hash)",
    "dedup_player_in_mail": "重複 (同 mail 内 同選手)",
    "dedup_player_recent": "重複 (直近メールで既出の選手)",
}


def _format_dropped_section_text(
    dropped: "Sequence[tuple[Candidate, str]] | None",
) -> list[str]:
    """spec/x-impression-plan item 4「止めた理由を残す」: text mail 用 section."""
    if not dropped:
        return []
    lines = [
        "━" * 40,
        f"【止めた候補】{len(dropped)} 件 (重複防止)",
        "━" * 40,
        "",
    ]
    for cand, reason in dropped:
        player = (cand.focus_player or "").strip() or "?"
        metric = (str(cand.metric or "")).strip() or "?"
        period = (cand.period_label or "").strip() or "?"
        reason_ja = _DROPPED_REASON_JA.get(reason, reason)
        lines.append(f"- {player} ({metric} / {period}): {reason_ja}")
    lines.append("")
    return lines


def _format_dropped_section_html(
    dropped: "Sequence[tuple[Candidate, str]] | None",
) -> str:
    if not dropped:
        return ""
    rows: list[str] = []
    for cand, reason in dropped:
        player = _html.escape((cand.focus_player or "").strip() or "?")
        metric = _html.escape((str(cand.metric or "")).strip() or "?")
        period = _html.escape((cand.period_label or "").strip() or "?")
        reason_ja = _html.escape(_DROPPED_REASON_JA.get(reason, reason))
        rows.append(
            f"<li>{player} ({metric} / {period}) — <code>{reason_ja}</code></li>"
        )
    return (
        "<div style=\"font-size:12px;color:#5d4037;background:#f6f8fa;"
        "border:1px solid #d0d7de;border-radius:4px;padding:8px 10px;"
        "margin:14px 0 4px;\">"
        f"<div style=\"font-weight:600;margin-bottom:4px;\">"
        f"止めた候補 {len(dropped)} 件 (重複防止)</div>"
        f"<ul style=\"margin:0;padding-left:18px;\">{''.join(rows)}</ul>"
        "</div>"
    )


def _compose_text_body(
    candidates: list[Candidate],
    now: datetime,
    *,
    context_note: str = "",
    dropped: "Sequence[tuple[Candidate, str]] | None" = None,
) -> str:
    band = time_band_label(now.hour)
    timing = x_impression_timing_label(now)
    header_label = _mail_header_label(candidates)
    parts = [
        f"📮 {header_label} — {band} / {now.strftime('%Y-%m-%d %H:%M')} JST",
        f"現在の投稿枠: {timing}",
        "",
        "公開通知ではありません。X に手動投稿するための候補メールです。",
        "各候補のテキストをコピーして X アプリに貼り付けて投稿してください。",
        "(HTML mail を表示できる client なら 🐦 ボタンで X アプリが直接開きます)",
        "",
    ]
    if context_note:
        parts.extend([context_note, ""])
    summary_lines, _ = _source_mix_summary(candidates)
    parts.extend(["【Source / flags】", *summary_lines, ""])
    for idx, cand in enumerate(candidates, start=1):
        post_text = _candidate_post_text(cand)
        parts.append("━" * 40)
        parts.append(f"■ 候補 {idx}: {cand.title}")
        parts.append("━" * 40)
        parts.append("")
        parts.append(f"【採用理由】{_candidate_selected_reason_text(cand)}")
        why_now = _candidate_why_now(cand, now)
        if why_now:
            parts.append(f"【今出す理由】{why_now}")
        parts.append("")
        parts.append(post_text)
        parts.append("")
        parts.append(f"【文字数】{_candidate_char_count(cand)} / {X_CHAR_LIMIT}")
        if cand.post_text and cand.draft_text and cand.post_text != cand.draft_text:
            parts.append("")
            parts.append("【根拠データ】")
            parts.append(cand.draft_text)
        parts.append("")
        cand_quote_url = getattr(cand, "quote_url", "") or ""
        cand_reply_id = getattr(cand, "reply_to_id", "") or ""
        if cand_reply_id:
            parts.append("💬 X 返信 URL:")
            parts.append(encode_x_reply_intent_url(post_text, cand_reply_id))
        elif cand_quote_url:
            parts.append("🐦 X 引用RT URL:")
            parts.append(encode_x_quote_intent_url(post_text, cand_quote_url))
        else:
            parts.append("🐦 X 投稿 URL:")
            parts.append(encode_x_intent_url(post_text))
        parts.append("")
    parts.extend(_format_dropped_section_text(dropped))
    return "\n".join(parts)


RANKING_IMAGE_CID_PREFIX = "giants-ranking-cand-"


# 437 Phase 5 fix: production draft_text は「{rank}位 {name}（{team}）{value} 🟧巨人🟧」
# 形式 (`format_as_x_post` 出力)。 旧 `_RANKING_ROW_PATTERN` (1. {name}…) と併用する。
_RANKING_ROW_PATTERN_V2 = _re.compile(
    r"^(?P<rank>\d+)位\s+"
    r"(?P<name>[^（]+?)"
    r"（(?P<team>[^）]+)）"
    r"(?P<value>\S+?)"
    r"(?P<marker>\s+🟧巨人🟧)?$"
)


def _extract_ranking_rows_from_draft(
    draft_text: str, *, focus_player: str = "", max_rows: int = 8
) -> list[dict]:
    """draft_text の各行を ranking 行として parse。

    対応 format:
      旧: `1. {name}（{team}）{value} ← 巨人`
      新 (production): `1位 {name}（{team}）{value} 🟧巨人🟧`

    marker (` ← 巨人` / `🟧巨人🟧`) または focus_player 名一致で is_giants=True。
    解析行 0 なら [] を返し caller は画像 skip。
    """
    rows: list[dict] = []
    for raw_line in draft_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _RANKING_ROW_PATTERN_V2.match(line) or _RANKING_ROW_PATTERN.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        is_giants = bool(m.group("marker"))
        if not is_giants and focus_player and focus_player.strip() == name:
            is_giants = True
        rows.append(
            {
                "rank": int(m.group("rank")),
                "name": name,
                "team": m.group("team").strip(),
                "value": m.group("value").strip(),
                "is_giants": is_giants,
            }
        )
        if len(rows) >= max_rows:
            break
    return rows


def _build_candidate_hook_and_title(
    metric: str, period_label: str, focus_player: str, rows: list[dict]
) -> tuple[str, str, str]:
    """画像 header の title / subtitle / hook_line を組む。"""
    title = f"セ・リーグ {metric} ランキング" if metric else "セ・リーグ ランキング"
    subtitle = period_label or ""
    giants_in_top = [r for r in rows if r.get("is_giants")]
    if focus_player and any(r.get("name") == focus_player for r in giants_in_top):
        hook = f"★ {focus_player} {metric} ★"
    elif len(giants_in_top) >= 2:
        hook = f"★ 巨人 {len(giants_in_top)} 名 トップ {len(rows)} 入り ★"
    elif len(giants_in_top) == 1:
        only = giants_in_top[0]
        hook = f"★ {only['name']} {metric} {only['value']} ★"
    else:
        hook = f"★ セ・リーグ {metric} ranking ★"
    return title, subtitle, hook


# 437 Phase 6: 候補 metric から最適 template を自動選択するための分類。
_PITCHER_METRIC_KEYWORDS = (
    "防御率", "ERA", "WHIP", "K_per_9", "BB_per_9", "HR_per_9",
    "奪三振率", "与四球率", "被本塁打率", "投球", "登板", "K/BB",
)
_PLAYER_SPOTLIGHT_RANK_THRESHOLD = 1  # 1 位の時だけ spotlight


def _is_pitcher_metric(metric: str) -> bool:
    if not metric:
        return False
    return any(kw in metric for kw in _PITCHER_METRIC_KEYWORDS)


# 437 Phase 7: rank 1 既定 router 以外は candidate index で round-robin に
# template を振り分け、 mail 内 8 候補で 8 異なる visual を見せる。
# 2026-06-11: variation 3 種追加 (podium_top3 / focus_duel / dark_hero)。
_ROUND_ROBIN_TEMPLATES = (
    "ranking_table",
    "podium_top3",
    "chart_bars",
    "focus_duel",
    "data_sheet",
    "monthly_summary",
    "dark_hero",
    "starting_lineup",
    "12team_crown",
    "12team_bar",
    "scoreboard",
    "standings",
)


def _select_template_and_data(candidate, rows: list[dict], *, candidate_index: int = 0):
    """候補と抽出済 rows から、 使う template_key と data dict を返す。

    優先順位:
      1. focus_player が TOP1 で投手指標 → pitcher_card
      2. focus_player が TOP1 → player_spotlight
      3. candidate_index に基づき _ROUND_ROBIN_TEMPLATES からピック
    """
    from src.x_post_image_gen_v2 import (
        build_12team_bar_data,
        build_pitcher_card_data,
        build_player_spotlight_data,
        build_ranking_data,
        build_standings_data,
    )

    metric = getattr(candidate, "metric", "") or ""
    period_label = getattr(candidate, "period_label", "") or ""
    focus_player = getattr(candidate, "focus_player", "") or ""
    title, subtitle, hook = _build_candidate_hook_and_title(
        metric, period_label, focus_player, rows
    )

    # 1) focus_player が rank 1 で投手指標 → pitcher_card
    focus_row = next(
        (r for r in rows if r.get("name") == focus_player and r.get("is_giants")),
        None,
    )
    if (
        focus_row is not None
        and _is_pitcher_metric(metric)
        and focus_row.get("rank", 99) <= _PLAYER_SPOTLIGHT_RANK_THRESHOLD
    ):
        stats: list[dict] = [
            {"label": metric, "value": str(focus_row.get("value", "")), "highlight": True}
        ]
        for r in rows[:5]:
            if r.get("name") == focus_player:
                continue
            stats.append({"label": str(r.get("name", "")), "value": str(r.get("value", ""))})
            if len(stats) >= 6:
                break
        data = build_pitcher_card_data(
            title=title, subtitle=subtitle, hook_line=hook,
            player_name=focus_player, player_team=str(focus_row.get("team", "")), stats=stats,
        )
        return "pitcher_card", data

    # 2) focus_player が rank 1 → player_spotlight
    if focus_row is not None and focus_row.get("rank", 99) == _PLAYER_SPOTLIGHT_RANK_THRESHOLD:
        sub_stats = [
            {"label": str(r.get("name", "")), "value": str(r.get("value", ""))}
            for r in rows[1:3]
        ]
        data = build_player_spotlight_data(
            title=title, subtitle=subtitle, hook_line=hook,
            player_name=focus_player, player_team=str(focus_row.get("team", "")),
            metric_label=metric, hero_value=str(focus_row.get("value", "")), sub_stats=sub_stats,
        )
        return "player_spotlight", data

    # 3) round-robin: candidate_index で template 切替
    template_key = _ROUND_ROBIN_TEMPLATES[candidate_index % len(_ROUND_ROBIN_TEMPLATES)]

    if template_key == "12team_bar":
        # rows[].name を team として扱う簡易 mapping (TOP10 個別選手の絶対値 bar)
        teams = [
            {
                "name": str(r.get("name", "")),
                "value": _safe_float(r.get("value", 0)),
                "value_label": str(r.get("value", "")),
                "is_giants": bool(r.get("is_giants")),
            }
            for r in rows[:12]
        ]
        data = build_12team_bar_data(
            title=title, subtitle=subtitle, hook_line=hook, teams=teams
        )
        return template_key, data

    if template_key == "standings":
        # ranking rows を順位表っぽく流用 (record / win_pct は値で代用)
        standings_rows = [
            {
                "rank": r.get("rank", i + 1),
                "team": str(r.get("team", "")) + (" / " + str(r.get("name", "")) if r.get("name") else ""),
                "record": str(r.get("value", "")),
                "win_pct": str(r.get("value", "")),
                "games_back": "-" if i == 0 else f"{i}",
                "is_giants": bool(r.get("is_giants")),
            }
            for i, r in enumerate(rows[:6])
        ]
        data = build_standings_data(
            title=title, subtitle=subtitle, hook_line=hook, rows=standings_rows
        )
        return template_key, data

    # その他 (ranking_table / chart_bars / data_sheet / monthly_summary /
    # starting_lineup / 12team_crown / scoreboard / podium_top3 /
    # focus_duel / dark_hero): rows を共通 schema で渡す
    data = build_ranking_data(title=title, subtitle=subtitle, hook_line=hook, rows=rows)
    return template_key, data


def _safe_float(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _generate_candidate_image_png(
    candidate, *, sample_rows: list[dict] | None = None, candidate_index: int = 0
) -> bytes | None:
    """1 候補の metric / period / focus_player + draft_text から PNG bytes 生成。

    候補 metric / index で template を自動選択 (pitcher_card / spotlight /
    round-robin 7 種類)。 draft_text に ranking 行が無いと None (image skip)。

    438 Phase 1 (2026-05-27): 候補に ``image_bytes`` が直接乗っていれば
    (= GEMMA_BRANDING の og:image fetch 済) その bytes をそのまま返し、
    既存 ranking image gen path を bypass する。
    """
    # 438: 直接 og:image bytes が乗っている候補は そのまま返す
    direct_image = getattr(candidate, "image_bytes", None)
    if direct_image:
        return direct_image
    # 2026-07-10 user「図が意味わからない。いらないかも」: ranking 図解カードを
    # env で止められるようにする (選手写真系 = 上の direct_image は残る)。
    if (os.environ.get("X_POST_RANKING_CARD_ENABLED", "1").strip().lower()
            in {"0", "false", "no", "off"}):
        return None
    try:
        from src.x_post_image_gen_v2 import generate_png
    except Exception as exc:
        logger.warning(
            "[437 phase7] image gen import failed (%s): %s — mail skips image",
            type(exc).__name__, exc,
        )
        return None
    rows = _extract_ranking_rows_from_draft(
        getattr(candidate, "draft_text", "") or "",
        focus_player=getattr(candidate, "focus_player", "") or "",
    )
    if not rows and sample_rows is not None:
        rows = sample_rows
    if not rows:
        return None
    try:
        template_key, data = _select_template_and_data(
            candidate, rows, candidate_index=candidate_index
        )
        png = generate_png(template_key, data)
    except Exception as exc:
        logger.warning(
            "[437 phase7] image gen failed (%s): %s — mail skips image",
            type(exc).__name__, exc,
        )
        return None
    if not png:
        return None
    return png


def _candidate_image_cid(index: int) -> str:
    """候補 index → cid (mail 単位で unique)。"""
    return f"{RANKING_IMAGE_CID_PREFIX}{index}"


# 437 Phase 8 (2026-05-26): share-x button (Web Share API) で候補 PNG を X app に
# 直接送るための GCS upload + URL 生成。 inline CID は mail 内表示用、 GCS upload
# は fetcher /share-x-cand 経由で外部 fetch 可能にするため。
_SHARE_X_CAND_BLOB_PREFIX = "share_x_cand"


def _resolve_share_x_cand_config() -> tuple[str, str, bool]:
    """share-x-cand button を有効化する env 3 点を読む。

    Returns (bucket_name, fetcher_base_url, enabled). enabled は env 必須 3 点
    + ENABLE_SHARE_X_BUTTON が truthy のときのみ True。 1 つでも欠ければ False で
    button URL は X intent fallback (現状動作) のまま。
    """
    bucket = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    fetcher_base = (os.environ.get("FETCHER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    flag = (os.environ.get("ENABLE_SHARE_X_BUTTON") or "").strip().lower()
    enabled = bool(bucket) and bool(fetcher_base) and flag in {"1", "true", "yes", "on"}
    return bucket, fetcher_base, enabled


def _detect_image_format(image_bytes: bytes) -> tuple[str, str]:
    """bytes signature から (content_type, extension) を返す.

    438 (2026-05-28 PM3): overlay (D) を廃止して raw og:image (C) に切替えた結果、
    hochi/sanspo の JPEG og:image を image/png 扱いで GCS upload + .png blob key
    していた mismatch が真のデグレ (share-x-cand で X app が画像 attach 拒否
    する原因)。 bytes signature 検出で正しく png/jpeg/webp/gif 判定する。
    """
    if not image_bytes or len(image_bytes) < 4:
        return "image/png", "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png", "png"
    if image_bytes[:4] == b"RIFF" and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp", "webp"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    return "image/png", "png"


def _share_x_cand_blob_key(run_id: str, index: int, *, ext: str = "png") -> str:
    """GCS blob key (path within bucket)。 mail run + candidate idx + 実 ext で一意。"""
    return f"{_SHARE_X_CAND_BLOB_PREFIX}/{run_id}/cand-{index:02d}.{ext}"


def _upload_candidate_image_to_gcs(
    image_bytes: bytes,
    *,
    bucket_name: str,
    blob_key: str,
    content_type: str = "image/png",
) -> bool:
    """image bytes を GCS にアップロード。 成功 True、 失敗 False (mail は止めない).

    content_type は caller が bytes signature から判定して渡す (default は
    後方互換の image/png)。 share-x-cand JS は GCS content-type をそのまま
    blob.type に反映し navigator.share に渡すため、 ここで誤ると X app で
    画像 attach 拒否 (438 PM3 デグレ真因)。
    """
    if not image_bytes or not bucket_name or not blob_key:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_key)
        blob.upload_from_string(image_bytes, content_type=content_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[437 phase8] share-x-cand GCS upload failed key=%s err=%r",
            blob_key, exc,
        )
        return False
    return True


def _build_share_x_cand_button_url(
    blob_key: str,
    *,
    fetcher_base: str,
    post_text: str,
    post_url: str = "",
) -> str:
    """fetcher /share-x-cand への URL を組み立てる。

    URL params:
      - key: GCS blob key (URL-encoded)
      - token: HMAC + expiry (24h)
      - text: post_text (URL-encoded、 X compose 用)
      - url: post_url (URL-encoded、 任意、 share に URL を添える場合)
    """
    if not blob_key or not fetcher_base:
        return ""
    try:
        from src.share_x_cand_token import generate_share_x_cand_token
    except Exception as exc:  # noqa: BLE001
        logger.warning("[437 phase8] share_x_cand_token import failed: %r", exc)
        return ""
    token = generate_share_x_cand_token(blob_key)
    if not token:
        return ""
    from urllib.parse import urlencode

    params = {
        "key": blob_key,
        "token": token,
        "text": post_text or "",
        "url": post_url or "",
    }
    return f"{fetcher_base}/share-x-cand?{urlencode(params)}"


def _render_candidate_image_html(cid: str | None, *, alt_text: str = "") -> str:
    """候補の text の真上に置く <img cid:...> HTML フラグメント (画像無しなら空).

    438 Phase 1 (2026-05-27): comment 系候補 (og:image attach) は alt_text に
    「引用元: 媒体名」 が乗っている。 ranking 系は alt_text 空で従来通り。
    """
    if not cid:
        return ""
    alt_value = (alt_text or "").strip() or "giants ranking"
    return (
        "<div style=\"text-align:center;margin:0 0 10px;\">"
        f"<img src=\"cid:{cid}\" alt=\"{_html.escape(alt_value)}\" "
        "style=\"max-width:520px;width:100%;height:auto;border:1px solid #ddd;"
        "border-radius:6px;display:inline-block;\" draggable=\"true\"/>"
        "<div style=\"font-size:11px;color:#777;margin-top:4px;\">"
        "↑ X compose にドラッグ (PC) / 長押し保存 (スマホ) で添付"
        "</div></div>"
    )


def _compose_html_body(
    candidates: list[Candidate],
    now: datetime,
    *,
    context_note: str = "",
    candidate_image_cids: list[str | None] | None = None,
    share_x_button_urls: list[str | None] | None = None,
    direct_post_button_urls: list[str | None] | None = None,
    dropped: "Sequence[tuple[Candidate, str]] | None" = None,
) -> str:
    band = time_band_label(now.hour)
    timing = x_impression_timing_label(now)
    header_label = _mail_header_label(candidates)
    summary_lines, _ = _source_mix_summary(candidates)
    summary_html = (
        "<div style=\"font-size:12px;color:#444;background:#f6f8fa;"
        "border:1px solid #d0d7de;border-radius:4px;padding:8px 10px;"
        "margin:0 0 12px;\">"
        "<div style=\"font-weight:600;margin-bottom:4px;\">Source / flags</div>"
        + "".join(f"<div>{_html.escape(line)}</div>" for line in summary_lines)
        + "</div>"
    )
    rows_html: list[str] = []
    for idx, cand in enumerate(candidates, start=1):
        post_text = _candidate_post_text(cand)
        cand_quote_url = getattr(cand, "quote_url", "") or ""
        cand_reply_id = getattr(cand, "reply_to_id", "") or ""
        if cand_reply_id:
            # 451: リプライ候補は reply intent (大手投稿への返信) で開く
            intent_url = encode_x_reply_intent_url(post_text, cand_reply_id)
        elif cand_quote_url:
            # 451: 引用RT 候補は quote intent (コメント + 元ツイート) で開く
            intent_url = encode_x_quote_intent_url(post_text, cand_quote_url)
        else:
            intent_url = encode_x_intent_url(post_text)
        char_count = _candidate_char_count(cand)
        over = char_count > X_CHAR_LIMIT
        counter_color = "#b71c1c" if over else "#666"
        counter_suffix = " ⚠️ 超過" if over else ""
        selected_reason = _candidate_selected_reason_text(cand)
        why_now = _candidate_why_now(cand, now)
        why_now_html = (
            "<div style=\"font-size:12px;color:#5d4037;margin:0 0 8px;\">"
            f"今出す理由: {_html.escape(why_now)}</div>"
            if why_now else ""
        )
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
        image_html_for_candidate = ""
        if candidate_image_cids and idx - 1 < len(candidate_image_cids):
            image_html_for_candidate = _render_candidate_image_html(
                candidate_image_cids[idx - 1],
                alt_text=getattr(cand, "image_alt_text", "") or "",
            )
        # 437 Phase 8: share-x-cand URL があれば、 ボタン href をそちらに置換。
        # 画像つき Web Share API (Pixel / Android) で X app へ直送、 不支持 device
        # では server 側 JS が X intent URL fallback。
        share_x_url = ""
        if share_x_button_urls and idx - 1 < len(share_x_button_urls):
            share_x_url = share_x_button_urls[idx - 1] or ""
        # 2026-07-06: API 直投稿ボタン (X app を開かない = アカウント切替不要)。
        # スマホ側のアクティブアカウントに関係なく @yoshilover6760 から投稿される。
        direct_post_url = ""
        if direct_post_button_urls and idx - 1 < len(direct_post_button_urls):
            direct_post_url = direct_post_button_urls[idx - 1] or ""
        direct_post_html = ""
        if direct_post_url:
            direct_post_html = (
                f"<a href=\"{_html.escape(direct_post_url)}\" "
                "style=\"display:inline-block;padding:8px 14px;background:#f57f17;"
                "color:#fff;text-decoration:none;border-radius:6px;font-size:13px;"
                "font-weight:700;\">🚀 @yoshilover6760で即投稿 (切替不要)</a>"
            )
        button_href = share_x_url or intent_url
        # 2026-06-11 user「次へ遷移せず戻る」: 画像つき share (navigator.share →
        # X app の画像編集ステップ) が端末/X app 側で詰まると投稿手段が無くなる
        # ため、 画像つきボタンがある時もテキストのみ intent を予備ボタンで併記
        # する (intent は X compose 直開きで画像ステップを通らない = 確実)。
        fallback_intent_html = ""
        if share_x_url:
            button_label = "🐦 画像つきで X に投稿"
            if intent_url:
                fallback_intent_html = (
                    f"<a href=\"{_html.escape(intent_url)}\" "
                    "style=\"display:inline-block;padding:8px 14px;"
                    "background:#fff;color:#000;text-decoration:none;"
                    "border-radius:6px;font-size:13px;font-weight:600;"
                    "border:1px solid #000;\">"
                    "✍ テキストのみで投稿 (画像は手動添付)</a>"
                )
        elif cand_reply_id:
            button_label = "💬 この投稿にリプライ"
        elif cand_quote_url:
            button_label = "🐦 引用RTで X に投稿"
        else:
            button_label = "🐦 X で投稿"
        # 451 followup: 元投稿 (動画つき) を開くリンク + X 公式「動画をポスト」手順を併記。
        # user 運用 = 動画を長押し →「動画をポスト」(リポスト+引用の公式機能、 元投稿に
        # 自動帰属) → コメントを貼って投稿。 引用RT ボタンより native 動画でリーチが出る。
        open_original_html = ""
        video_howto_html = ""
        if cand_quote_url:
            open_original_html = (
                f"<a href=\"{_html.escape(cand_quote_url)}\" "
                "style=\"display:inline-block;padding:8px 14px;"
                "background:#fff;color:#000;text-decoration:none;border-radius:6px;"
                "font-size:13px;font-weight:600;border:1px solid #000;\">"
                "▶ 元の動画ポストを開く</a>"
            )
            video_howto_html = (
                "<div style=\"font-size:12px;color:#33691e;background:#f1f8e9;"
                "border:1px solid #c5e1a5;border-radius:4px;padding:8px 10px;"
                "margin-top:8px;line-height:1.6;\">"
                "🎬 <b>動画で投稿する手順</b>（X公式「動画をポスト」）<br>"
                "① 上の「▶ 元の動画ポストを開く」をタップ<br>"
                "② 動画を<b>長押し</b> →「<b>動画をポスト</b>」を選ぶ<br>"
                "③ 上のコメント案を貼り付けて投稿"
                "</div>"
            )
        rows_html.append(
            "<div style=\"border-left:3px solid #f57f17;"
            "padding:10px 14px;margin:14px 0;background:#fff8e1;"
            "border-radius:4px;\">"
            f"<div style=\"font-weight:600;font-size:14px;color:#5d4037;"
            f"margin:0 0 8px;\">■ 候補 {idx}: {_html.escape(cand.title)}</div>"
            f"{image_html_for_candidate}"
            "<div style=\"font-size:12px;color:#5d4037;margin:0 0 8px;\">"
            f"採用理由: {_html.escape(selected_reason)}</div>"
            f"{why_now_html}"
            "<pre style=\"white-space:pre-wrap;word-break:keep-all;"
            "font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',"
            "'Yu Gothic',monospace;font-size:13px;line-height:1.5;"
            "background:#fff;padding:10px;border:1px solid #ddd;"
            f"border-radius:4px;margin:0;\">{_html.escape(post_text)}</pre>"
            f"{proof_html}"
            "<div style=\"display:flex;gap:10px;align-items:center;"
            "margin-top:8px;flex-wrap:wrap;\">"
            f"{direct_post_html}"
            f"<a href=\"{_html.escape(button_href)}\" "
            "style=\"display:inline-block;padding:8px 14px;background:#000;"
            "color:#fff;text-decoration:none;border-radius:6px;font-size:13px;"
            f"font-weight:600;\">{button_label}</a>"
            f"{fallback_intent_html}"
            f"{open_original_html}"
            f"<div style=\"font-size:11px;color:{counter_color};\">"
            f"{char_count} / {X_CHAR_LIMIT} 字{counter_suffix}</div>"
            "</div>"
            f"{video_howto_html}"
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
        "<div style=\"font-size:12px;color:#5d4037;background:#fff8e1;"
        "border-left:3px solid #f57f17;padding:7px 10px;margin:0 0 12px;\">"
        f"現在の投稿枠: {_html.escape(timing)}</div>"
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
        + summary_html
        + "\n".join(rows_html)
        + _format_dropped_section_html(dropped)
        + "</body></html>"
    )


@dataclass(frozen=True)
class CandidateImage:
    """437 Phase 5: 候補ごとの inline 画像。"""

    cid: str
    png: bytes


@dataclass(frozen=True)
class ComposedMail:
    subject: str
    text_body: str
    html_body: str
    candidate_count: int
    candidate_images: list[CandidateImage] = field(default_factory=list)


def compose_mail(
    candidates: list[Candidate],
    *,
    now: Optional[datetime] = None,
    context_label: str = "",
    context_note: str = "",
    dropped: "Sequence[tuple[Candidate, str]] | None" = None,
) -> ComposedMail:
    if now is None:
        now = datetime.now(JST)
    if not context_label and _has_news_opinion_candidate(candidates):
        context_label = "データ+ニュース意見"
    subject = build_subject(now, len(candidates), context_label=context_label)
    # 437 Phase 7: 候補ごとに draft_text から ranking parse + index で template
    # round-robin
    candidate_images: list[CandidateImage] = []
    cids_for_html: list[str | None] = []
    # 437 Phase 8: share-x-cand env が揃えば GCS upload + 候補ごと URL 生成。
    bucket_name, fetcher_base, share_x_enabled = _resolve_share_x_cand_config()
    run_id = now.strftime("%Y%m%d-%H%M%S")
    share_x_urls: list[str | None] = []
    for idx, cand in enumerate(candidates):
        png = _generate_candidate_image_png(cand, candidate_index=idx)
        if not png:
            cids_for_html.append(None)
            share_x_urls.append(None)
            continue
        cid = _candidate_image_cid(idx)
        candidate_images.append(CandidateImage(cid=cid, png=png))
        cids_for_html.append(cid)
        share_x_url: str | None = None
        if share_x_enabled:
            # 438 PM3 (2026-05-28): bytes signature から実フォーマット検出して
            # content_type + blob 拡張子を一致させる。 raw og:image (JPEG/WebP) を
            # image/png 扱いで upload すると share-x-cand JS の navigator.share で
            # X app が画像 attach を拒否する mismatch デグレを修正。
            content_type, ext = _detect_image_format(png)
            blob_key = _share_x_cand_blob_key(run_id, idx, ext=ext)
            if _upload_candidate_image_to_gcs(
                png,
                bucket_name=bucket_name,
                blob_key=blob_key,
                content_type=content_type,
            ):
                share_x_url = _build_share_x_cand_button_url(
                    blob_key,
                    fetcher_base=fetcher_base,
                    post_text=_candidate_post_text(cand),
                )
        share_x_urls.append(share_x_url or None)
    # 2026-07-06: API 直投稿 URL (画像有無に関係なく全候補分)。
    # X API は 2026-02 から従量課金 (Pay-Per-Use) のため、user「金は使いたくない」
    # 方針で既定 OFF。ENABLE_X_DIRECT_POST_BUTTON=1 の明示 opt-in 時のみボタンを出す。
    direct_post_urls: list[str | None] = []
    xdp_flag = (os.environ.get("ENABLE_X_DIRECT_POST_BUTTON") or "").strip().lower()
    xdp_base = (os.environ.get("FETCHER_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if xdp_flag not in {"1", "true", "yes", "on"}:
        xdp_base = ""
    if xdp_base:
        from src.x_direct_post_handler import build_direct_post_button_url

        for cand in candidates:
            url = build_direct_post_button_url(
                _candidate_post_text(cand),
                account="baseball",
                base_url=xdp_base,
                reply_to_id=getattr(cand, "reply_to_id", "") or "",
                quote_url=getattr(cand, "quote_url", "") or "",
            )
            direct_post_urls.append(url or None)
    else:
        direct_post_urls = [None] * len(candidates)
    text_body = _compose_text_body(
        candidates, now, context_note=context_note, dropped=dropped
    )
    html_body = _compose_html_body(
        candidates,
        now,
        context_note=context_note,
        candidate_image_cids=cids_for_html,
        share_x_button_urls=share_x_urls,
        direct_post_button_urls=direct_post_urls,
        dropped=dropped,
    )
    return ComposedMail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        candidate_count=len(candidates),
        candidate_images=candidate_images,
    )
