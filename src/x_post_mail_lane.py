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
import json as _json
import logging
import math as _math
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
SAFE_METRICS = ("AVG", "OBP", "SLG", "OPS", "ERA")

# Friendly Japanese label per metric (mirrors 346 format_as_x_post
# helper but inline here to avoid coupling to a private constant).
_METRIC_LABELS_JP: dict[str, str] = {
    "AVG": "打率",
    "OBP": "出塁率",
    "SLG": "長打率",
    "OPS": "OPS",
    "ERA": "防御率",
}

# 353: metric 別 header 絵文字。 batting (AVG/OBP/SLG/OPS) = ⚾、 pitching
# (ERA) = ⚡、 守備 (将来 SAFE_METRICS 拡張時) = 🛡️。 fallback は 📊。
_METRIC_HEADER_EMOJI: dict[str, str] = {
    "AVG": "⚾",
    "OBP": "⚾",
    "SLG": "⚾",
    "OPS": "⚾",
    "ERA": "⚡",
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

# X intent URL base. The Web Intent endpoint is supported by both X
# Web (x.com / twitter.com) and the native X apps on iOS/Android.
_X_INTENT_URL_BASE = "https://twitter.com/intent/tweet"

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
    (直近 5/10 試合 / 直近 7 日 / 守備位置別 / 巨人最上位の短期変化) を
    novelty_high として扱う。

    354: ``db_path`` を渡すと 直近 5/10 巨人試合 × OPS/AVG/ERA の
    6 combo (全部 novelty="high"、 min_sample_override で AB 閾値緩和)
    を追加する。 ``db_path=None`` (default) では直近 N 試合 combo を除外し、
    test / 旧呼出 互換を維持する。

    357: 月別は毎日出すと mail 過多になるため、月初 3 日だけ前月成績を
    セ・リーグ ranking として追加する (例: 8/1-8/3 に「7月成績」)。
    """
    combos: list[_MetricCombo] = []
    # 356+357: シーズン累積 / 直近30日 は大手が出しやすく、同じ
    # mail に複数期間が並ぶ原因にもなるため pool から外す。月別は
    # 月初だけ下の branch で制限付き追加。

    # 1. 直近 7 日 — short-term league slice.
    last7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    for m in ("OPS", "AVG", "ERA"):
        combos.append(_MetricCombo(m, last7, "直近7日", novelty="high"))
    # 2. 守備位置別 — niche slice that 大手 / のもとけ rarely cover.
    # 357: 全期間 / 今シーズンは大手も出すため使わない。守備位置別も
    # 直近 7 日に寄せる。
    # 守備位置 single-kanji codes match insight_rank_query expectations.
    for pos in ("捕", "二", "遊", "三"):
        combos.append(_MetricCombo("OPS", last7, "直近7日", position=pos, novelty="high"))
    # 3. 354: 直近 5/10 巨人試合 × OPS/AVG/ERA — yoshilover 独自
    # の試合数 base ranking。 games table が読めて且つ N 試合分の row が
    # あれば追加 (case-by-case fallback、 取得失敗時は skip)。
    if db_path:
        for n_games, label in ((5, "直近5試合"), (10, "直近10試合")):
            window = _query_recent_n_games_date_range(n_games, db_path)
            if window is None:
                continue
            since, until = window
            for m in ("OPS", "AVG", "ERA"):
                combos.append(
                    _MetricCombo(
                        m,
                        since,
                        label,
                        until=until,
                        novelty="high",
                        min_sample_override=n_games,
                    )
                )
    # 4. 357: 前月成績 — 「7月成績」のような月別表記は分かりやすいが、
    # 毎日出すと過剰なので月初だけ候補に入れる。セ・リーグ内で
    # 巨人最上位を見せ、period-family skip と 24h dedup の対象にする。
    if 1 <= now.day <= 3:
        month_since, month_until = _prev_month_range(now)
        month_label = _month_period_label(month_since, month_until) or "前月成績"
        for m in ("OPS", "AVG", "ERA"):
            combos.append(
                _MetricCombo(
                    m,
                    month_since,
                    month_label,
                    until=month_until,
                    novelty="high",
                    min_sample_override=10 if m == "ERA" else 30,
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


def _rebuild_ranks_within_central(rows: list[dict]) -> list[dict]:
    """After filtering to セ-only, rewrite ``rank`` so the column shows
    1..N within the 6-team scope (not the 12-team residual).
    """
    out = []
    for idx, r in enumerate(rows, start=1):
        # shallow copy keeps the original rank result intact for caller
        out.append({**r, "rank": idx, "total": len(rows)})
    return out


def _top_giants_row(rows: list[dict]) -> Optional[dict]:
    """Return the highest-ranked Giants row from already-ranked rows."""
    for row in rows:
        if _is_giants(row.get("team_code")):
            return row
    return None


def _rows_with_giants_focus(rows: list[dict], *, max_rows: int = 10) -> list[dict]:
    """Return display rows while guaranteeing the top Giants row is visible.

    The mail must answer "巨人の選手がセ・リーグで何位か". If the first
    Giants row falls outside the top-N display, replace the last display row
    with that Giants row rather than switching to a Giants-only ranking.
    """
    if max_rows <= 0:
        return []
    top_rows = list(rows[:max_rows])
    focus = _top_giants_row(rows)
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


def _rewrite_ranking_rows(
    lines: list[str],
    metric_jp: str,
) -> list[str]:
    """353: post-process the ``format_as_x_post`` body so each ranking
    row gets a medal prefix (🥇/🥈/🥉 for ranks 1-3, ``N.`` for 4+),
    a strong Giants marker (``←⭐巨人``), a metric-label-prefixed
    value (``OPS .945``), and a blank separator line between top-3
    and the remainder.
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
        # Strong Giants marker (← 巨人 → ←⭐巨人, drop the half-width
        # space so the star sits flush against the arrow).
        if marker.strip():
            new_marker = " ←⭐巨人"
        else:
            new_marker = ""
        # Medal prefix for top 3, numeric otherwise.
        if rank_num == 1:
            prefix = "🥇"
        elif rank_num == 2:
            prefix = "🥈"
        elif rank_num == 3:
            prefix = "🥉"
        else:
            prefix = f"{rank_num}."
        # Metric label prefix on value (e.g. ``OPS .945``).
        new_value = f"{metric_jp} {value}"
        new_lines.append(f"{prefix} {name}（{team}）{new_value}{new_marker}")
        # Blank line between top 3 and the rest.
        if rank_num == 3:
            new_lines.append("")
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
        is_ranking = (
            line.startswith("🥇")
            or line.startswith("🥈")
            or line.startswith("🥉")
            or bool(_re.match(r"^\d+\.\s", line))
        )
        if is_ranking:
            rank_seen += 1
            if rank_seen > top_n and "←⭐巨人" not in line:
                continue  # drop rows beyond top_n
        kept.append(line)
    return "\n".join(kept)


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


def _load_recent_dedup_signatures(
    bucket_name: str,
    now: datetime,
    *,
    lookback_hours: int = 24,
) -> set[str]:
    """355: read JSONL files in ``gs://{bucket_name}/x_post_mail/dedup/``
    for today + yesterday, filter to records with ``ts >= now -
    lookback_hours``, and return the set of seen signatures.

    Returns an empty set on any GCS error (silent fallback — the mail
    send must never block on dedup infrastructure problems).
    """
    if not bucket_name:
        return set()
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_load_recent_dedup_signatures: client init failed: %r", exc)
        return set()
    cutoff = now - timedelta(hours=lookback_hours)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    out: set[str] = set()
    for date_str in (today, yesterday):
        blob = bucket.blob(_dedup_blob_path(date_str))
        try:
            if not blob.exists():
                continue
            content = blob.download_as_text()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("_load_recent_dedup_signatures: read %s failed: %r",
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
            signature = rec.get("signature") or ""
            if not signature or not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if ts.tzinfo is None:
                # Treat naive timestamps as JST per project convention.
                ts = ts.replace(tzinfo=JST)
            if ts >= cutoff:
                out.add(signature)
    return out


def _record_dedup_signatures(
    bucket_name: str,
    signatures: list[str],
    now: datetime,
) -> bool:
    """355: append signatures to today's JSONL on GCS. Returns ``True``
    on success, ``False`` on any error (silent failure — never abort
    the calling flow).

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
    new_lines = [
        _json.dumps({"ts": ts_iso, "signature": s}, ensure_ascii=False)
        for s in signatures
    ]
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
) -> Optional[Candidate]:
    focus_row = _top_giants_row(rows)
    if focus_row is None:
        LOG.info("No Giants row for %s/%s — skip", combo.metric, combo.period_label)
        return None
    display_rows = _rows_with_giants_focus(rows, max_rows=10)
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

    # 351+353 follow-up: 守備位置別 / セ・リーグ ranking で header の prefix を切替。
    # 346 format_as_x_post の output 1 行目は「セ・{metric_jp} ランキング 📊」固定
    # なので、 1 行目を新 prefix + metric 別絵文字で置換する。
    if combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        if lines and "ランキング" in lines[0]:
            lines[0] = f"セ・{position_jp} {metric_jp} ランキング {header_emoji}"
    else:
        if lines and "ランキング" in lines[0]:
            lines[0] = f"セ・リーグ {metric_jp} ランキング {header_emoji}"
    title = (
        f"{focus_name} {metric_jp} {scope_label} {focus_rank}/{focus_total}位 "
        f"({period_label}・{threshold_label})"
    )
    # 353: period_suffix を 1 行目 append から 2 行目挿入に変更。
    lines.insert(1, period_suffix)
    lines.insert(2, f"巨人最上位: {focus_name} {scope_label} {focus_rank}/{focus_total}位")

    # 353: ranking rows に medal / metric label / strong Giants marker を post-process。
    lines = _rewrite_ranking_rows(lines, metric_jp)

    draft_text = "\n".join(lines)
    # 353: 280 字 cap を超えたら top 5 まで cut (rows-only trim)、 それでも
    # 超過なら最終手段として末尾 truncation + … で安全網。
    if len(draft_text) > X_CHAR_LIMIT:
        draft_text = _truncate_to_x_limit_top_n(draft_text, top_n=5)
        if len(draft_text) > X_CHAR_LIMIT:
            draft_text = draft_text[: X_CHAR_LIMIT - 1] + "…"
    return Candidate(
        title=title,
        metric=combo.metric,
        period_label=combo.period_label,
        draft_text=draft_text,
        char_count=len(draft_text),
        signature=_combo_signature(combo),
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
    """
    if now is None:
        now = datetime.now(JST)
    out: list[Candidate] = []
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
        try:
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
        min_rows_required = min_central_rows
        if len(rows) < min_rows_required:
            LOG.info("Too few rows (%d < %d) for %s/%s (position=%s) — skip",
                     len(rows), min_rows_required, combo.metric,
                     combo.period_label, combo.position)
            continue
        rows = _rebuild_ranks_within_central(rows)
        if _top_giants_row(rows) is None:
            LOG.info("No Giants row in central ranking for %s/%s (position=%s) — skip",
                     combo.metric, combo.period_label, combo.position)
            continue
        candidate = _format_one(combo, rows, min_sample=effective_min_sample, now=now)
        if candidate:
            out.append(candidate)
            seen_period_families.add(family_key)
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
    """
    encoded = _url_quote(text or "", safe="")
    return f"{_X_INTENT_URL_BASE}?text={encoded}"


# ---------------------------------------------------------------------------
# Mail composition
# ---------------------------------------------------------------------------


def time_band_label(hour: int) -> str:
    for hr_range, label in _TIME_BANDS:
        if hour in hr_range:
            return label
    return "夜"  # fall-through (should not happen with TIME_BANDS coverage)


def build_subject(now: datetime, n_candidates: int) -> str:
    band = time_band_label(now.hour)
    band_emoji = _TIME_BAND_EMOJI.get(band, "")
    return (
        f"🟠🐦📮【手動X投稿 {n_candidates}件】"
        f"{band_emoji}{band} {now.strftime('%H:%M')} JST"
    )


def _compose_text_body(candidates: list[Candidate], now: datetime) -> str:
    band = time_band_label(now.hour)
    parts = [
        f"📮 巨人データX投稿候補 — {band} / {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
        "公開通知ではありません。X に手動投稿するための候補メールです。",
        "各候補のテキストをコピーして X アプリに貼り付けて投稿してください。",
        "(HTML mail を表示できる client なら 🐦 ボタンで X アプリが直接開きます)",
        "",
    ]
    for idx, cand in enumerate(candidates, start=1):
        parts.append("━" * 40)
        parts.append(f"■ 候補 {idx}: {cand.title}")
        parts.append("━" * 40)
        parts.append("")
        parts.append(cand.draft_text)
        parts.append("")
        parts.append(f"【文字数】{cand.char_count} / {X_CHAR_LIMIT}")
        parts.append("")
        parts.append("🐦 X 投稿 URL:")
        parts.append(encode_x_intent_url(cand.draft_text))
        parts.append("")
    return "\n".join(parts)


def _compose_html_body(candidates: list[Candidate], now: datetime) -> str:
    band = time_band_label(now.hour)
    rows_html: list[str] = []
    for idx, cand in enumerate(candidates, start=1):
        intent_url = encode_x_intent_url(cand.draft_text)
        over = cand.char_count > X_CHAR_LIMIT
        counter_color = "#b71c1c" if over else "#666"
        counter_suffix = " ⚠️ 超過" if over else ""
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
            f"border-radius:4px;margin:0;\">{_html.escape(cand.draft_text)}</pre>"
            "<div style=\"display:flex;gap:10px;align-items:center;"
            "margin-top:8px;flex-wrap:wrap;\">"
            f"<a href=\"{_html.escape(intent_url)}\" "
            "style=\"display:inline-block;padding:8px 14px;background:#000;"
            "color:#fff;text-decoration:none;border-radius:6px;font-size:13px;"
            "font-weight:600;\">🐦 X で投稿</a>"
            f"<div style=\"font-size:11px;color:{counter_color};\">"
            f"{cand.char_count} / {X_CHAR_LIMIT} 字{counter_suffix}</div>"
            "</div>"
            "</div>"
        )
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\"><head><meta charset=\"utf-8\">"
        "<title>巨人データX投稿候補</title></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,"
        "'Hiragino Sans','Yu Gothic',sans-serif;color:#222;"
        "max-width:680px;margin:0 auto;padding:18px;\">"
        f"<h2 style=\"font-size:17px;margin:0 0 8px;\">📮 巨人データX投稿候補 — {band} / "
        f"{now.strftime('%Y-%m-%d %H:%M')} JST</h2>"
        "<p style=\"font-size:13px;color:#555;margin:0 0 14px;\">"
        "公開通知ではなく、X に手動投稿するための候補メールです。"
        "各候補の <strong>🐦 X で投稿</strong> ボタンを押すと X アプリ "
        "(または x.com) が本文プリフィル済で開きます。タップして "
        "「ポスト」だけ押せば投稿完了です。テキスト編集も可能。</p>"
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
) -> ComposedMail:
    if now is None:
        now = datetime.now(JST)
    subject = build_subject(now, len(candidates))
    text_body = _compose_text_body(candidates, now)
    html_body = _compose_html_body(candidates, now)
    return ComposedMail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        candidate_count=len(candidates),
    )
