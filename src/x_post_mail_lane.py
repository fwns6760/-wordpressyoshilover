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
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
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

    Extended in 351 with optional ``until``, ``position`` (守備位置 single
    kanji), and ``giants_only`` (filter the final ranking to 巨人 rows
    only, used for 「巨人内 OPS top 5」 style posts).
    """

    metric: str
    since: Optional[str]
    period_label: str
    until: Optional[str] = None
    position: Optional[str] = None
    giants_only: bool = False


def _prev_month_range(now: datetime) -> tuple[str, str]:
    """Return (since, until) for the previous calendar month as ISO dates."""
    first_of_this = now.replace(day=1)
    last_of_prev = first_of_this - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return (
        first_of_prev.strftime("%Y-%m-%d"),
        last_of_prev.strftime("%Y-%m-%d"),
    )


def _build_combos(now: datetime) -> list[_MetricCombo]:
    """Compose the metric × period × position combo pool for one mail.

    351: pool grows from 10 to 22+ entries. ``pick_candidates`` samples
    ``max_candidates`` (default 10) from this pool with diversity-seeded
    randomness so identical-hour mails on different days don't repeat
    the same combo set.

    Caller takes the first ``max_candidates`` successful ones after
    shuffling (see ``_select_with_diversity``).
    """
    combos: list[_MetricCombo] = []
    # 1. Season-wide (5 metrics)
    for m in ("OPS", "AVG", "ERA", "OBP", "SLG"):
        combos.append(_MetricCombo(m, None, "今シーズン"))
    # 2. Monthly = current month (3 metrics)
    month_since = now.replace(day=1).strftime("%Y-%m-%d")
    for m in ("OPS", "AVG", "ERA"):
        combos.append(_MetricCombo(m, month_since, "今月"))
    # 3. Last 30 days (2 metrics)
    last30 = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    for m in ("OPS", "AVG"):
        combos.append(_MetricCombo(m, last30, "直近30日"))
    # 4. 351: Previous month (2 metrics) — closed range
    prev_since, prev_until = _prev_month_range(now)
    for m in ("OPS", "AVG"):
        combos.append(_MetricCombo(m, prev_since, "先月", until=prev_until))
    # 5. 351: Last 7 days (1 metric)
    last7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    combos.append(_MetricCombo("OPS", last7, "直近7日"))
    # 6. 351: Last 14 days (2 metrics)
    last14 = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    for m in ("OPS", "AVG"):
        combos.append(_MetricCombo(m, last14, "直近14日"))
    # 7. 351: 守備位置別 — niche slice that 大手 / のもとけ rarely cover.
    # 守備位置 single-kanji codes match insight_rank_query expectations.
    for pos in ("捕", "二", "遊", "三"):
        combos.append(_MetricCombo("OPS", None, "今シーズン", position=pos))
    # 8. 351: 巨人内 ranking — filter final rows to 巨人 rows only.
    for m in ("OPS", "AVG", "ERA"):
        combos.append(_MetricCombo(m, None, "今シーズン", giants_only=True))
    return combos


def _select_with_diversity(
    combos: list[_MetricCombo],
    *,
    max_candidates: int,
    now: datetime,
) -> list[_MetricCombo]:
    """Shuffle ``combos`` deterministically per (date, hour) seed and
    return up to ``max_candidates``.

    Same hour on the same day yields the same order (so the schedule's
    7:00 → 7:00 next day rotates), but day-over-day or band-over-band
    produces different sets. Avoids the 「毎日同じ ranking ばかり」
    fatigue while keeping the run reproducible inside one trigger
    window.
    """
    import random as _random

    seed = int(now.strftime("%Y%m%d")) * 100 + now.hour
    rng = _random.Random(seed)
    shuffled = list(combos)
    rng.shuffle(shuffled)
    return shuffled[: max(1, max_candidates)]


@dataclass(frozen=True)
class Candidate:
    title: str
    metric: str
    period_label: str
    draft_text: str
    char_count: int


def _rebuild_ranks_within_central(rows: list[dict]) -> list[dict]:
    """After filtering to セ-only, rewrite ``rank`` so the column shows
    1..N within the 6-team scope (not the 12-team residual).
    """
    out = []
    for idx, r in enumerate(rows, start=1):
        # shallow copy keeps the original rank result intact for caller
        out.append({**r, "rank": idx, "total": len(rows)})
    return out


def _sample_label_for_metric(metric: str) -> str:
    """Return the Japanese unit label used in the 規定打席 / 投球回 suffix.

    Batting metrics use 打席 (PA). Pitching (ERA) uses 投球回 (IP).
    """
    if metric == "ERA":
        return "投球回"
    return "打席"


def _format_period_range(combo: _MetricCombo, now: datetime) -> str:
    """Return a concrete date-range label for the header.

    Replaces vague labels (今シーズン / 今月 / 直近30日) with explicit
    ``M/D〜M/D`` ranges so the operator (and X readers) see exactly what
    window the ranking covers. Season-wide collapses to ``開幕〜M/D 累積``
    because the actual opening-day date is not embedded in this module
    (would require a games-table query, deferred per 348 disjoint).

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


def _format_one(
    combo: _MetricCombo,
    rows: list[dict],
    *,
    min_sample: int,
    now: datetime,
) -> Optional[Candidate]:
    parsed = {
        "metric": combo.metric,
        "position": None,
        "top_n": min(10, len(rows)),
        "league": "セ",
        "focus_player": None,
    }
    rank_result = {
        "ok": True,
        "rows": rows[:10],
        "count": min(10, len(rows)),
        "total": len(rows),
        "focus_player": None,
    }
    formatted = _format_as_x_post(parsed, rank_result, top_n=10)
    if not formatted.get("ok"):
        LOG.warning("format_as_x_post failed for %s (%s): %s",
                    combo.metric, combo.period_label, formatted.get("reason"))
        return None
    # 350+351: header に 具体的 date range + 規定 sample 閾値 + 状況 slice を明示。
    text = formatted["draft_text"]
    lines = text.split("\n")
    period_range = _format_period_range(combo, now)
    sample_label = _sample_label_for_metric(combo.metric)
    period_suffix = f"（{period_range}・規定{sample_label} {min_sample}+）"
    metric_jp = _METRIC_LABELS_JP.get(combo.metric, combo.metric)

    # 351: 守備位置別 / 巨人内 ranking で header の prefix を切替。
    # 346 format_as_x_post の output 1 行目は「セ・{metric_jp} ランキング 📊」固定
    # なので、prefix を「セ・捕手 {metric_jp} ランキング」「巨人内 {metric_jp} ランキング」
    # 等に置換する。
    if combo.giants_only:
        if lines and "ランキング" in lines[0]:
            lines[0] = f"巨人内 {metric_jp} ランキング 📊" + period_suffix
        title = (
            f"巨人内 {metric_jp} top {min(10, len(rows))} "
            f"({period_range}・規定{sample_label} {min_sample}+)"
        )
    elif combo.position:
        position_jp = _POSITION_DISPLAY_JP.get(combo.position, combo.position)
        if lines and "ランキング" in lines[0]:
            lines[0] = f"セ・{position_jp} {metric_jp} ランキング 📊" + period_suffix
        title = (
            f"セ・{position_jp} {metric_jp} top {min(10, len(rows))} "
            f"({period_range}・規定{sample_label} {min_sample}+)"
        )
    else:
        if lines and "ランキング" in lines[0]:
            lines[0] = lines[0].rstrip() + period_suffix
        title = (
            f"セ {metric_jp} top {min(10, len(rows))} "
            f"({period_range}・規定{sample_label} {min_sample}+)"
        )
    draft_text = "\n".join(lines)
    return Candidate(
        title=title,
        metric=combo.metric,
        period_label=combo.period_label,
        draft_text=draft_text,
        char_count=len(draft_text),
    )


def pick_candidates(
    query_rank_fn: Callable[..., dict],
    *,
    now: Optional[datetime] = None,
    max_candidates: int = 10,
    min_sample: int = 30,
    min_central_rows: int = 5,
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
        small samples out.
    min_central_rows:
        Minimum number of セ teams that must appear in a query result
        for the candidate to be emitted. If fewer than this number of
        セ rows show up, that combo is skipped (silent fallback to the
        next combo).
    """
    if now is None:
        now = datetime.now(JST)
    out: list[Candidate] = []
    # 351: shuffle the combo pool with a (date, hour) seed so each trigger
    # picks a different variety slice while staying reproducible inside a
    # single run.
    shuffled = _select_with_diversity(
        _build_combos(now),
        max_candidates=len(_build_combos(now)),
        now=now,
    )
    for combo in shuffled:
        if len(out) >= max_candidates:
            break
        try:
            result = query_rank_fn(
                metric_name=combo.metric,
                since=combo.since,
                until=combo.until,
                position_filter=combo.position,
                min_sample=min_sample,
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
        # 351: 巨人内 ranking — keep only Giants rows after the セ filter.
        if combo.giants_only:
            rows = [r for r in rows if _is_giants(r.get("team_code"))]
            min_rows_required = 3  # only need a few 巨人 players for a meaningful list
        else:
            min_rows_required = min_central_rows
        if len(rows) < min_rows_required:
            LOG.info("Too few rows (%d < %d) for %s/%s (giants_only=%s, position=%s) — skip",
                     len(rows), min_rows_required, combo.metric,
                     combo.period_label, combo.giants_only, combo.position)
            continue
        rows = _rebuild_ranks_within_central(rows)
        candidate = _format_one(combo, rows, min_sample=min_sample, now=now)
        if candidate:
            out.append(candidate)
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
    return f"[X 投稿候補 {n_candidates}件] {band} / {now.strftime('%Y-%m-%d %H:%M')} JST"


def _compose_text_body(candidates: list[Candidate], now: datetime) -> str:
    band = time_band_label(now.hour)
    parts = [
        f"X 投稿候補 — {band} / {now.strftime('%Y-%m-%d %H:%M')} JST",
        "",
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
        "<title>X 投稿候補</title></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,"
        "'Hiragino Sans','Yu Gothic',sans-serif;color:#222;"
        "max-width:680px;margin:0 auto;padding:18px;\">"
        f"<h2 style=\"font-size:17px;margin:0 0 8px;\">X 投稿候補 — {band} / "
        f"{now.strftime('%Y-%m-%d %H:%M')} JST</h2>"
        "<p style=\"font-size:13px;color:#555;margin:0 0 14px;\">"
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
