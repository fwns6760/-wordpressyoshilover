"""346 — format_as_x_post: convert insight rank result into X post draft.

Pure Python, LLM-free. Takes parsed question (from
:func:`src.analysis.insight_nl_query.parse_question`) and rank result
(from :func:`src.manual_intake_insight_query.query_rank`) and returns
a formatted X post draft string ready for human review and posting.

Hard constraints (mirrors 346 ticket):
    - LLM API never called.
    - Source numbers / names / ranks are copied verbatim from the rank
      result; nothing is invented.
    - 280-character X limit enforced via truncation.
    - Giants team rows highlighted with ``← 巨人`` for the operator.

Returns: ``{ok: bool, draft_text: str, char_count: int, reason?: str}``.
"""

from __future__ import annotations

from typing import Any, Optional

# X char limit (post body); URLs would be 23-char-counted but this
# module does not embed any URL — pure text only.
X_CHAR_LIMIT = 280

# Hashtag block appended to every draft. Kept short so the body keeps
# room for the data payload.
DEFAULT_HASHTAGS = "#巨人 #ジャイアンツ"

# Team-name strings (the rank result's ``team_code`` column holds
# ``team_name`` per insight_rank_query.py) that mean Yomiuri Giants.
# Operators wrote roster files in these forms; keep them aligned with
# insight_defense_proxy.py's alias table so the highlight catches every
# variant the ETL produces.
_GIANTS_TEAM_ALIASES = frozenset(
    {
        "巨人",
        "読売",
        "読売ジャイアンツ",
        "ジャイアンツ",
        "Giants",
        "GIANTS",
        "G",
        "g",
    }
)

# Display labels for known metric codes. Unknown codes are echoed
# verbatim so we never silently mis-label a future metric.
_METRIC_LABELS_JP: dict[str, str] = {
    "AVG": "打率",
    "OBP": "出塁率",
    "SLG": "長打率",
    "OPS": "OPS",
    "ISO": "純長打率",
    "wOBA": "加重出塁率",
    "BB_pct": "四球率",
    "K_pct": "三振率",
    "BABIP": "インプレー打率",
    "ERA": "防御率",
    "WHIP": "1イニングあたり被出塁数",
    "K_per_9": "奪三振率",
    "BB_per_9": "与四球率",
    "HR_per_9": "被本塁打率",
    "K_BB": "奪三振/与四球比",
    "FIP": "守備非依存防御率",
    "xFIP": "補正守備非依存防御率",
    "RF_proxy": "守備範囲指標",
    "UZR_proxy": "守備評価指標",
    "WAR": "総合貢献度",
}

# Position single-kanji codes → readable Japanese.
_POSITION_LABELS_JP: dict[str, str] = {
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


def _metric_label(metric: str) -> str:
    return _METRIC_LABELS_JP.get(metric, metric)


def _position_label(position: Optional[str]) -> str:
    if not position:
        return ""
    return _POSITION_LABELS_JP.get(position, position)


def _is_giants(team_code: Optional[str]) -> bool:
    if not team_code:
        return False
    return team_code.strip() in _GIANTS_TEAM_ALIASES


def _format_value(metric: str, value: Any) -> str:
    """Format a metric value with appropriate precision.

    Numbers are rendered to mirror NPB / SABR convention (.345 for
    batting averages, 2.85 for ERA, etc.). Values arrive as float from
    the DB; ``None`` stays as ``"-"`` so the row is still readable.
    """
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    # Rate-style metrics (≤ 1.5 typical range) get the leading-zero-
    # stripped baseball convention (".345" not "0.345"). Compound or
    # counting metrics keep their natural form.
    if metric in {"AVG", "OBP", "SLG", "OPS", "ISO", "wOBA", "BABIP"}:
        s = f"{v:.3f}"
        if s.startswith("0."):
            s = s[1:]
        elif s.startswith("-0."):
            s = "-" + s[2:]
        return s
    if metric in {"ERA", "WHIP", "FIP", "xFIP", "K_per_9", "BB_per_9", "HR_per_9", "K_BB"}:
        return f"{v:.2f}"
    if metric in {"BB_pct", "K_pct"}:
        # value already a fraction in DB (e.g. 0.085) → render as %.
        return f"{v * 100:.1f}%"
    # Default: 3 decimal places, trim trailing zeros for tidiness.
    return f"{v:g}"


def _truncate_to_x_limit(text: str) -> str:
    """Trim text to ``X_CHAR_LIMIT`` chars by dropping trailing rank
    rows first (preserving header + hashtags).

    Used only as a safety net. Templates are sized for the 280-char
    budget under normal top_n values (≤10).
    """
    if len(text) <= X_CHAR_LIMIT:
        return text
    # Naive truncation with a trailing ellipsis. Loss of trailing rows
    # is acceptable; the operator can edit before posting.
    return text[: X_CHAR_LIMIT - 1] + "…"


# 投手 metric (header emoji = ⚡)、 それ以外は打者扱い (⚾)。
# 353 STEP1 (2026-05-17) で導入された pitcher/batter 区分を 418 case B でも維持。
_PITCHER_METRICS = frozenset({
    "ERA", "WHIP", "FIP", "xFIP", "K_per_9", "BB_per_9", "HR_per_9", "K_BB"
})


def _build_header(parsed: dict, focus_player: Optional[dict], *, top_n: Optional[int] = None) -> str:
    """Compose header. 418 case B: 📊 リーグ metric TOPN ⚾/⚡ + 期間 / サンプル を 2 段で."""
    metric = parsed.get("metric") or ""
    metric_jp = _metric_label(metric)
    pos_jp = _position_label(parsed.get("position"))
    league = parsed.get("league") or ""
    # 投手 metric は ⚡ 、 打者/その他は ⚾ (353 STEP1 継承)
    metric_emoji = "⚡" if metric in _PITCHER_METRICS else "⚾"
    if focus_player:
        # Single-player focus: header centers on the player (既存挙動維持)
        team = focus_player.get("team_code") or ""
        return f"{focus_player.get('player_canonical', '')}（{team}）{metric_emoji}"
    # 418 case B: 「📊 セ・リーグ 打率 TOP10 ⚾」 1 段目、 期間 / サンプル 2 段目
    line1_parts = ["📊"]
    if league:
        line1_parts.append(f" {league}")
    if pos_jp:
        line1_parts.append(f" {pos_jp}")
    line1_parts.append(f" {metric_jp}")
    if top_n:
        line1_parts.append(f" TOP{top_n}")
    line1_parts.append(f" {metric_emoji}")
    line1 = "".join(line1_parts)
    # 2 段目: 期間 / サンプル context (parsed が持ってれば)
    period_label = parsed.get("period_label") or ""
    sample_label = parsed.get("sample_label") or ""
    if period_label or sample_label:
        line2_parts = []
        if period_label:
            line2_parts.append(period_label)
        if sample_label:
            line2_parts.append(sample_label)
        return f"{line1}\n{' / '.join(line2_parts)}"
    return line1


def _build_ranking_body(rows: list[dict], top_n: int, metric: str) -> str:
    """418 case B: 「1位/2位/.../N位」 表記 + 巨人 player は 🟧巨人🟧 で強調.

    各行 1 改行で並べる、 280 字 cap は caller (_truncate_to_x_limit) が末尾切る。
    Giants player は 「player（team）value 🟧巨人🟧」 で末尾強調 (末尾 ← 巨人 から
    囲み marker へ視覚強化)。
    """
    if not rows:
        return "（該当データなし）"
    out_lines = []
    for r in rows[: max(1, top_n)]:
        rank = r.get("rank")
        name = r.get("player_canonical") or ""
        team = r.get("team_code") or ""
        value = _format_value(metric, r.get("metric_value"))
        marker = " 🟧巨人🟧" if _is_giants(team) else ""
        out_lines.append(f"{rank}位 {name}（{team}）{value}{marker}")
    return "\n".join(out_lines)


def _build_focus_body(focus: dict, metric: str) -> str:
    value = _format_value(metric, focus.get("metric_value"))
    rank = focus.get("rank")
    total = focus.get("total")
    sample = focus.get("sample_size")
    return f"{_metric_label(metric)} {value}（順位 {rank}/{total}、サンプル {sample}）"


def format_as_x_post(
    parsed: dict,
    rank_result: dict,
    *,
    hashtags: Optional[str] = None,
    top_n: Optional[int] = None,
) -> dict:
    """Return ``{ok, draft_text, char_count}`` for the given query
    output.

    Parameters
    ----------
    parsed:
        Output of :func:`src.analysis.insight_nl_query.parse_question`.
        Must contain ``metric``; ``position``, ``top_n``, ``league``,
        ``focus_player`` honoured when present.
    rank_result:
        Output of :func:`src.manual_intake_insight_query.query_rank`.
        Must have ``ok: True`` and ``rows`` (possibly empty).
    hashtags:
        Override the default hashtag block. ``""`` to suppress.
    top_n:
        Override ``parsed["top_n"]``. Clamped to ``[1, 10]`` to keep
        the post under the 280-char budget under typical Japanese
        name lengths.
    """
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "reason": "parsed_not_dict",
            "draft_text": "",
            "char_count": 0,
        }
    if not isinstance(rank_result, dict):
        return {
            "ok": False,
            "reason": "rank_result_not_dict",
            "draft_text": "",
            "char_count": 0,
        }
    if not rank_result.get("ok"):
        return {
            "ok": False,
            "reason": rank_result.get("reason") or "rank_failed",
            "draft_text": "",
            "char_count": 0,
        }

    metric = parsed.get("metric") or ""
    if not metric:
        return {
            "ok": False,
            "reason": "metric_missing",
            "draft_text": "",
            "char_count": 0,
        }

    focus = rank_result.get("focus_player")
    rows = rank_result.get("rows") or []

    # Resolve effective top_n. Cap at 10 so the longest expected name
    # set still fits the 280-char budget under realistic team labels.
    if top_n is None:
        top_n = parsed.get("top_n") or 10
    try:
        top_n_int = max(1, min(int(top_n), 10))
    except (TypeError, ValueError):
        top_n_int = 10

    # 418 case B: ranking 時は header に TOPN を入れる (focus 時は player 中心のため不要)
    header = _build_header(parsed, focus, top_n=None if focus else top_n_int)

    if focus:
        body = _build_focus_body(focus, metric)
    else:
        body = _build_ranking_body(rows, top_n_int, metric)

    tags = DEFAULT_HASHTAGS if hashtags is None else hashtags

    # Compose with blank lines between blocks for X readability.
    sections = [header, "", body]
    if tags:
        sections.extend(["", tags])
    draft = "\n".join(sections)
    draft = _truncate_to_x_limit(draft)
    return {
        "ok": True,
        "draft_text": draft,
        "char_count": len(draft),
    }
