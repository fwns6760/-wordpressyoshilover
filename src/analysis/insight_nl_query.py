"""INSIGHT-009 — natural language query parser (rule-based, no LLM).

Maps free-form Japanese questions like
    「セリーグのセカンドUZRトップ10は？」
    「巨人の岡本のwOBA何位？」
    「先発FIPランキング上位5」
to structured query parameters that feed into
:func:`manual_intake_insight_query.generate_article`.

Pure dict + regex, no Gemini / external API. Coverage ~80% of common
operator phrasings; falls back to ``unresolved`` flags so the UI can
prompt for missing pieces.

Returns ``{metric, position, top_n, focus_player, league, raw_text,
unresolved: [...] }``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# ─── dictionaries ───────────────────────────────────────────────────────────

# Position aliases — Japanese natural language → single-kanji canonical
# used by insight_defense_proxy / insight_rank_query.
POSITION_ALIASES: dict[str, str] = {
    "ピッチャー": "投", "投手": "投", "先発": "投", "中継ぎ": "投", "抑え": "投",
    "キャッチャー": "捕", "捕手": "捕",
    "ファースト": "一", "一塁": "一", "一塁手": "一", "1B": "一",
    "セカンド": "二", "二塁": "二", "二塁手": "二", "2B": "二",
    "サード": "三", "三塁": "三", "三塁手": "三", "3B": "三",
    "ショート": "遊", "遊撃": "遊", "遊撃手": "遊", "SS": "遊",
    "レフト": "左", "左翼": "左", "左翼手": "左", "LF": "左",
    "センター": "中", "中堅": "中", "中堅手": "中", "CF": "中",
    "ライト": "右", "右翼": "右", "右翼手": "右", "RF": "右",
    "外野": None,  # unresolved, prompt user
    "内野": None,
}

# Metric aliases — natural Japanese / English → canonical name in
# insight_rank_query.KNOWN_METRICS
METRIC_ALIASES: dict[str, str] = {
    # batting
    "打率": "AVG", "AVG": "AVG",
    "出塁率": "OBP", "OBP": "OBP",
    "長打率": "SLG", "SLG": "SLG",
    "OPS": "OPS",
    "ISO": "ISO", "純長打": "ISO",
    "wOBA": "wOBA",
    "三振率": "K_pct", "K%": "K_pct", "K_pct": "K_pct",
    "四球率": "BB_pct", "BB%": "BB_pct", "BB_pct": "BB_pct",
    "BABIP": "BABIP",
    # pitching
    "防御率": "ERA", "ERA": "ERA",
    "WHIP": "WHIP",
    "K/9": "K_per_9", "K9": "K_per_9", "奪三振率": "K_per_9",
    "BB/9": "BB_per_9", "BB9": "BB_per_9",
    "HR/9": "HR_per_9", "HR9": "HR_per_9",
    "K/BB": "K_BB", "KBB": "K_BB",
    "FIP": "FIP",
    "xFIP": "xFIP",
    # defense
    "UZR": "UZR_proxy", "RF": "RF_proxy",
    "Range Factor": "RF_proxy",
    "守備機会変換率": "RF_proxy",
    "UZR_proxy": "UZR_proxy", "RF_proxy": "RF_proxy",
}

LEAGUE_ALIASES: dict[str, str] = {
    "セ・リーグ": "central", "セリーグ": "central", "セリーグの": "central",
    "セ": "central",
    "パ・リーグ": "pacific", "パリーグ": "pacific", "パリーグの": "pacific",
    "パ": "pacific",
    "全12球団": "all", "全球団": "all",
}

# top_n triggers — extract a number
_TOP_N_RE = re.compile(
    r"(?:トップ|上位|TOP|top)\s*(?P<n>\d+)|(?P<n2>\d+)\s*位",
    re.IGNORECASE,
)

# 自然語の数字 (一桁の漢数字、稀に必要)
_KANJI_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


# ─── helpers ────────────────────────────────────────────────────────────────


def _giants_roster_names() -> list[tuple[str, str]]:
    """Return active Giants ``(alias_or_canonical, canonical)`` pairs.

    Each canonical name is paired with itself and with every alias (so
    free-form input like 「岡本」「岡本 和真」「マー君」 all resolve back
    to the canonical). Surname-only entries are also generated when the
    surname uniquely maps to one canonical."""
    roster = Path(__file__).resolve().parents[2] / "config" / "giants_roster.json"
    if not roster.exists():
        return []
    try:
        rows = json.loads(roster.read_text(encoding="utf-8"))
    except Exception:
        return []
    pairs: list[tuple[str, str]] = []
    canonicals: list[str] = []
    for r in rows:
        if not r.get("active"):
            continue
        canon = (r.get("name") or "").strip()
        if not canon:
            continue
        canonicals.append(canon)
        # canonical itself + every alias
        pairs.append((canon, canon))
        for a in r.get("aliases") or []:
            alias = (a or "").strip()
            if alias and alias != canon:
                pairs.append((alias, canon))
        # spaces-removed variant for "岡本 和真" → "岡本和真"
        compact = canon.replace(" ", "").replace("　", "")
        if compact != canon and compact:
            pairs.append((compact, canon))
    # Surname (first 2 chars) fallback for unique surnames
    surname_groups: dict[str, list[str]] = {}
    for canon in canonicals:
        compact = canon.replace(" ", "").replace("　", "")
        if len(compact) >= 2:
            surname_groups.setdefault(compact[:2], []).append(canon)
    for surname, cands in surname_groups.items():
        if len(cands) == 1:
            pairs.append((surname, cands[0]))
    # Longest first so substring matches prefer specific names
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


def _detect_metric(text: str) -> Optional[str]:
    # Longer aliases first to avoid sub-matches (e.g. "BB/9" vs "9")
    for alias in sorted(METRIC_ALIASES, key=len, reverse=True):
        if alias in text:
            return METRIC_ALIASES[alias]
    return None


def _detect_position(text: str) -> tuple[Optional[str], bool]:
    """Return (canonical_position_kanji, was_ambiguous)."""
    for alias in sorted(POSITION_ALIASES, key=len, reverse=True):
        if alias in text:
            v = POSITION_ALIASES[alias]
            if v is None:
                return (None, True)  # 外野 / 内野 = ambiguous
            return (v, False)
    return (None, False)


def _detect_league(text: str) -> Optional[str]:
    for alias in sorted(LEAGUE_ALIASES, key=len, reverse=True):
        if alias in text:
            return LEAGUE_ALIASES[alias]
    return None


def _detect_top_n(text: str) -> Optional[int]:
    m = _TOP_N_RE.search(text)
    if m:
        n = m.group("n") or m.group("n2")
        try:
            return max(1, min(int(n), 50))
        except (TypeError, ValueError):
            pass
    return None


def _detect_focus_player(text: str, roster_pairs: list[tuple[str, str]]) -> Optional[str]:
    """Find the longest matching alias / canonical in ``text`` and return
    the canonical name. ``roster_pairs`` already sorted longest-first."""
    for alias, canon in roster_pairs:
        if alias in text:
            return canon
    return None


# ─── public API ─────────────────────────────────────────────────────────────


def parse_question(text: str) -> dict:
    """Parse a natural Japanese question into structured query params.

    Returns ``{metric, position, top_n, focus_player, league, raw_text,
                unresolved}`` where ``unresolved`` is a list of fields the
    parser couldn't pin down (UI can prompt for them).
    """
    raw = (text or "").strip()
    metric = _detect_metric(raw)
    position, position_ambiguous = _detect_position(raw)
    league = _detect_league(raw)
    top_n = _detect_top_n(raw)
    roster = _giants_roster_names()
    focus = _detect_focus_player(raw, roster)

    unresolved: list[str] = []
    if not metric:
        unresolved.append("metric")
    # Defense metric requires position
    if metric in {"RF_proxy", "UZR_proxy"} and not position:
        unresolved.append("position")
    if position_ambiguous and not position:
        unresolved.append("position_ambiguous")

    return {
        "metric": metric,
        "position": position,
        "top_n": top_n or 10,
        "focus_player": focus,
        "league": league,
        "raw_text": raw,
        "unresolved": unresolved,
    }
