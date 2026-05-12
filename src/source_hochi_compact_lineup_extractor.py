"""NOMOTOKE-LINEUP-FROM-HOCHI-COMPACT-001 — pure offline parser for 報知 /
スポニチ X "compact" lineup tweets.

Typical tweet shapes (production samples 2026-05-12)
====================================================

報知 ファーム (id=66442 source):

  ファーム・リーグ（Ｇタウン）スタメン【DeNA】 【巨人】
  D東妻 7萩尾 3加藤 9皆川 6石上 6小濱 5宮下 5藤井 7井上 3三塚
  4小田 8浅野 9梶原 Dティマ 2古市 2山瀬 8濱 4湯浅 P片山 P又木

報知 1軍 (compact form):

  巨人スタメン 中日戦(バンテリンD、13:30)
  4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田

Position digit / letter mapping (Japanese baseball convention):

  1=投 (P)  2=捕 (C)  3=一 (1B)  4=二 (2B)  5=三 (3B)
  6=遊 (SS) 7=左 (LF) 8=中 (CF)  9=右 (RF)
  D=指 (DH) P=投 (pitcher when explicit, e.g. ファーム両軍)

Conservative parser:

- Source must belong to the 報知 / スポニチ family (allowlist by name +
  URL substring). Other sources defer to existing extractors.
- Tweet text must contain a lineup keyword (スタメン / オーダー / etc.).
- Text must contain ≥ ``_MIN_LINEUP_TOKEN_COUNT`` consecutive compact tokens.
- The 巨人公式X clean format (``1番（中）ヘルナンデス``) is detected and
  skipped — defer to ``source_x_lineup_extractor``.
- Returns ``None`` (NOT silent skip — caller logs the parse skip) when any
  gate condition fails. The router treats ``None`` as "no compact lineup
  available, fall back to prose body".

Renderer contract: each row dict carries ``order`` (sequential 1..N within
this tweet, NOT batting order in the literal Japanese sense), ``position``
(kanji like ``左``), ``name``. ``batting_average`` / ``starter_era`` are
left empty — they would need a separate stats extractor (later phase).
"""

from __future__ import annotations

import html as html_lib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Source allowlist (報知 / スポニチ family)
# ---------------------------------------------------------------------------

# Exact source_name strings produced by ``config/rss_sources.json`` (verified
# 2026-05-12 against the production config).
HOCHI_SPONICHI_SOURCE_NAMES: frozenset[str] = frozenset(
    {
        "スポーツ報知巨人班X",
        "スポニチ野球記者X",
        "スポーツ報知X",
        "報知野球X",
        "スポーツ報知 巨人 tag",
        # Lower-cased aliases occasionally surfaced by the rsshub bridge.
        "hochi_giants",
        "hochi_baseball",
        "SportsHochi",
        "SponichiYakyu",
    }
)

# URL substrings that imply the article originates from 報知 / スポニチ.
_HOCHI_SPONICHI_URL_SUBSTRINGS: tuple[str, ...] = (
    "hochi.news",
    "sponichi.co.jp",
    "/hochi_giants",
    "/hochi_baseball",
    "/sportshochi",
    "/sponichiyakyu",
)


# ---------------------------------------------------------------------------
# Lineup keyword + position mapping
# ---------------------------------------------------------------------------

LINEUP_KEYWORDS: tuple[str, ...] = (
    "スタメン",
    "オーダー発表",
    "本日のオーダー",
    "本日のスタメン",
    "本日のメンバー",
    "本日のラインナップ",
    "ファーム・リーグ",
    "ファームのスタメン",
    "二軍スタメン",
)

# Japanese baseball position digit / letter -> kanji.
# 1=投 / 2=捕 / 3=一 / 4=二 / 5=三 / 6=遊 / 7=左 / 8=中 / 9=右
# D=指 (DH) / P=投 (explicit pitcher shorthand used by hochi for both teams)
_POSITION_MAP: Dict[str, str] = {
    "1": "投",
    "2": "捕",
    "3": "一",
    "4": "二",
    "5": "三",
    "6": "遊",
    "7": "左",
    "8": "中",
    "9": "右",
    "D": "指",
    "P": "投",
}


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Defensive: HTML tag stripping + entity decoding before token extraction.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Compact token: position character (D / P / 1-9) immediately followed
# (no whitespace) by a player name (1-8 chars).
#
# Name char class includes:
#   - kanji / katakana / hiragana (Japanese name set)
#   - UPPERCASE Latin only (for romanised initials like ``F.ウィットリー``)
#   - dot, middle-dot, hyphen variants (for compound names)
#
# Lowercase Latin is INTENTIONALLY EXCLUDED so that team-name fragments
# like ``DeNA`` (which would otherwise match as ``D`` + ``eNA``) cannot
# be misread as a position+name token. Numerals and whitespace are also
# excluded so that adjacent compact tokens (``7萩尾3加藤``) split cleanly.
_NAME_CHAR_CLASS = r"一-龥々ァ-ヴーぁ-んA-Z・．\.\-‐ー"
_LINEUP_TOKEN_RE = re.compile(
    r"(?P<pos>[DP1-9])(?P<name>[" + _NAME_CHAR_CLASS + r"]{1,8})"
)

# 巨人公式X clean form: ``1番（中）ヘルナンデス`` / ``1番(中)ヘルナンデス``.
# When this format is present, defer to ``source_x_lineup_extractor`` and
# return ``None`` to avoid double extraction.
_OFFICIAL_X_FORMAT_RE = re.compile(
    r"[1-9]番\s*[（(]\s*[投捕一二三遊左中右指]\s*[）)]"
)

# Minimum consecutive compact tokens needed to treat the text as a lineup.
# 8 = 8 position players (DH-less, pitcher batting 9th).
_MIN_LINEUP_TOKEN_COUNT = 8

# Conservative cap to bound runaway extraction on very long X tweets.
# 22 = 10 batters * 2 teams + a couple of substitution rows.
_MAX_LINEUP_TOKEN_COUNT = 22


# ---------------------------------------------------------------------------
# Roster lookup + opponent team detection (NOMOTOKE-LINEUP-FROM-HOCHI-COMPACT-002)
# ---------------------------------------------------------------------------

# Path to the operator-curated 巨人 roster file. Same path constant scheme
# as ``src/nomotoke_card_renderer._ROSTER_PATH`` so the two stay in sync
# even if the project root layout changes.
_GIANTS_ROSTER_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "giants_roster.json"
)
_GIANTS_ROSTER_CACHE: Optional[List[Dict[str, Any]]] = None

# Marker regex matches ``【XXX】`` (CJK lenticular brackets). Used to detect
# opponent team name in the tweet text.
_TEAM_MARKER_RE = re.compile(r"【([^】]{1,12})】")

# Known NPB team name fragments (used both for opponent detection and as
# the value rendered into the table heading). Order matters for partial
# matching — longer / more specific names first to avoid prefix collisions.
_NPB_OPPONENT_TEAM_NAMES: tuple[str, ...] = (
    "ソフトバンク",
    "日本ハム",
    "オリックス",
    "ヤクルト",
    "DeNA",
    "横浜",
    "阪神",
    "中日",
    "広島",
    "ロッテ",
    "西武",
    "楽天",
)

# Marker tokens that identify the OWN team (巨人) — skipped when searching
# for the opponent.
_OWN_TEAM_MARKERS: frozenset[str] = frozenset(
    {"巨人", "読売", "ジャイアンツ", "読売ジャイアンツ"}
)


def _load_giants_roster() -> List[Dict[str, Any]]:
    """Return the operator-curated 巨人 roster (cached). Empty list on
    any read / parse error so the parser never breaks on missing config.
    """
    global _GIANTS_ROSTER_CACHE
    if _GIANTS_ROSTER_CACHE is None:
        try:
            with _GIANTS_ROSTER_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            _GIANTS_ROSTER_CACHE = data if isinstance(data, list) else []
        except Exception:
            _GIANTS_ROSTER_CACHE = []
    return _GIANTS_ROSTER_CACHE or []


def _normalize_name_for_match(name: str) -> str:
    """Strip leading ``*`` (roster convention for 2軍/育成 markers),
    half/full-width spaces, and trim. Used for both roster entries and
    parsed source names so they compare cleanly."""
    if not isinstance(name, str):
        return ""
    return name.lstrip("*").replace(" ", "").replace("　", "").strip()


def is_giants_player(name: str) -> bool:
    """Return ``True`` when ``name`` matches a 巨人 roster entry.

    Match strategy (mirrors ``nomotoke_card_renderer._lookup_roster_by_name``):

    1. Exact match against any roster entry's ``name`` or any alias.
    2. Surname-prefix match (``len(name) in {2, 3, 4}``) against the
       start of any roster ``name`` / alias.

    Only ``active=True`` entries are consulted so retired players don't
    cause false positives.

    Known limitation: same-surname players across teams (e.g. ``井上``
    on 巨人 and DeNA) cannot be disambiguated by surname alone — caller
    surfaces this through a roster-attribution note in the rendered output.
    """
    norm = _normalize_name_for_match(name)
    if not norm:
        return False
    roster = _load_giants_roster()
    for entry in roster:
        if not entry.get("active"):
            continue
        full = _normalize_name_for_match(entry.get("name") or "")
        if full and full == norm:
            return True
        for alias in entry.get("aliases", []) or []:
            clean = _normalize_name_for_match(alias)
            if clean and clean == norm:
                return True
    # Compact lineup tweets routinely use 1-char surnames (e.g. ``1丸``
    # → 丸佳浩, ``9森`` → 森田駿哉). Allow 1-4 char surname-prefix here
    # (slightly more permissive than ``nomotoke_card_renderer``'s 2-4 cap)
    # because the position digit prefix in the source token already gives
    # an extra signal that this is a lineup row and not arbitrary text.
    if 1 <= len(norm) <= 4:
        for entry in roster:
            if not entry.get("active"):
                continue
            full = _normalize_name_for_match(entry.get("name") or "")
            if full and full.startswith(norm):
                return True
            for alias in entry.get("aliases", []) or []:
                clean = _normalize_name_for_match(alias)
                if clean and clean.startswith(norm):
                    return True
    return False


def extract_opponent_team_name(text: str) -> str:
    """Return the first non-巨人 team name found in ``text``.

    Match strategy (in order):

    1. Exact ``【XXX】`` marker where ``XXX`` matches a known NPB team
       fragment.
    2. ``【XXX】`` marker substring-containing a known NPB team
       (e.g. ``【横浜DeNA】`` → ``DeNA``).
    3. Prose-level ``<team>戦`` pattern (e.g. ``中日戦(バンテリンD…)`` →
       ``中日``). The ``戦`` suffix is the standard Japanese game-name
       indicator and is safe (won't accidentally hit ``中日新聞`` etc.).
    4. Prose-level ``巨人 vs <team>`` / ``<team> vs 巨人`` pattern
       (e.g. ``【二軍】巨人 vs ロッテ ...`` → ``ロッテ``). Common in 巨人
       公式X 2軍 tweet headlines that don't include the team name in
       ``【XXX】`` markers.

    Returns ``""`` when no opponent indicator is found.
    """
    if not text:
        return ""
    # 1 + 2: marker-based extraction
    for m in _TEAM_MARKER_RE.finditer(text):
        marker_inner = m.group(1).strip()
        if not marker_inner or marker_inner in _OWN_TEAM_MARKERS:
            continue
        if marker_inner in _NPB_OPPONENT_TEAM_NAMES:
            return marker_inner
        for npb in _NPB_OPPONENT_TEAM_NAMES:
            if npb in marker_inner:
                return npb
    # 3: prose `<team>戦` fallback
    for npb in _NPB_OPPONENT_TEAM_NAMES:
        if f"{npb}戦" in text:
            return npb
    # 4: prose `vs <team>` / `<team> vs` fallback (case-insensitive ``vs``)
    vs_re = re.compile(
        r"(?:巨人|読売|ジャイアンツ)\s*(?:[vV][sS]|VS|×|🆚)\s*([^\s　]{1,12})"
        r"|([^\s　]{1,12})\s*(?:[vV][sS]|VS|×|🆚)\s*(?:巨人|読売|ジャイアンツ)"
    )
    for m in vs_re.finditer(text):
        candidate = (m.group(1) or m.group(2) or "").strip()
        if not candidate or candidate in _OWN_TEAM_MARKERS:
            continue
        if candidate in _NPB_OPPONENT_TEAM_NAMES:
            return candidate
        for npb in _NPB_OPPONENT_TEAM_NAMES:
            if npb in candidate:
                return npb
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_hochi_sponichi_source(source_name: str = "", source_url: str = "") -> bool:
    """Return ``True`` when ``source_name`` or ``source_url`` belongs to
    the 報知 / スポニチ family.

    Purely text-based; no I/O. The check is intentionally permissive on
    name substrings (``報知`` / ``スポニチ``) so that minor naming
    variations in ``config/rss_sources.json`` don't silently fall out of
    coverage.
    """
    name = (source_name or "").strip()
    if name in HOCHI_SPONICHI_SOURCE_NAMES:
        return True
    if "報知" in name or "スポニチ" in name:
        return True
    url_lower = (source_url or "").lower()
    for fragment in _HOCHI_SPONICHI_URL_SUBSTRINGS:
        if fragment in url_lower:
            return True
    return False


def parse_hochi_compact_lineup(
    title: str,
    summary: str,
    source_name: str = "",
    source_url: str = "",
) -> Optional[Dict[str, Any]]:
    """Parse a 報知 / スポニチ X compact-format lineup tweet.

    Returns

        {
          "lineup":   [{"order": "1", "position": "指", "name": "東妻"}, ...],
          "keyword":  "<the keyword that matched>",
          "raw_position_count": <int>,
        }

    or ``None`` when the input doesn't look like a compact lineup we can
    safely extract (silent skip is intentional ONLY here — the caller
    decides whether to log).

    Gate conditions (ALL required):

    1. ``source_name`` / ``source_url`` belongs to the 報知 / スポニチ family.
    2. Combined ``title + summary`` contains a lineup keyword.
    3. The 巨人公式X clean format is NOT present (defer to
       ``source_x_lineup_extractor`` to avoid double extraction).
    4. The combined text contains ≥ ``_MIN_LINEUP_TOKEN_COUNT``
       extractable compact tokens.
    """
    if not is_hochi_sponichi_source(source_name, source_url):
        return None

    # Production X tweets typically pass identical (or near-identical)
    # title and summary. Concatenating both would double every match, so
    # we use the longer of the two as the canonical source text.
    title_norm = _normalize_text(title or "")
    summary_norm = _normalize_text(summary or "")
    if len(summary_norm) >= len(title_norm):
        text = summary_norm or title_norm
    else:
        text = title_norm
    if not text:
        return None

    if not _has_lineup_keyword(text):
        return None
    if _OFFICIAL_X_FORMAT_RE.search(text):
        return None

    matches = list(_LINEUP_TOKEN_RE.finditer(text))
    if len(matches) < _MIN_LINEUP_TOKEN_COUNT:
        return None

    # Dedupe by (position, name) preserving order. Same player at same
    # position appearing twice in one tweet is redundant; different
    # players at the same position (DeNA 7萩尾 vs 巨人 7井上) are kept.
    seen: set[tuple[str, str]] = set()
    deduped: List[Dict[str, str]] = []
    for m in matches:
        pos_char = m.group("pos")
        name = (m.group("name") or "").strip()
        position = _POSITION_MAP.get(pos_char, "")
        if not name or not position:
            continue
        key = (position, name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"position": position, "name": name})
        if len(deduped) >= _MAX_LINEUP_TOKEN_COUNT:
            break

    if len(deduped) < _MIN_LINEUP_TOKEN_COUNT:
        return None

    # NOMOTOKE-LINEUP-FROM-HOCHI-COMPACT-002: classify each row by 巨人
    # roster membership and record the opponent team name from the tweet
    # markers. The renderer in ``rss_fetcher`` uses these fields to split
    # output into 「巨人スタメン」 / 「<opponent>スタメン」 tables.
    rows: List[Dict[str, str]] = [
        {
            "order": str(index),
            "position": row["position"],
            "name": row["name"],
            "team": "巨人" if is_giants_player(row["name"]) else "相手",
        }
        for index, row in enumerate(deduped, start=1)
    ]

    keyword = next((kw for kw in LINEUP_KEYWORDS if kw in text), "")
    opponent_team_name = extract_opponent_team_name(text)
    return {
        "lineup": rows,
        "keyword": keyword,
        "raw_position_count": len(matches),
        "opponent_team_name": opponent_team_name,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_text(raw: str) -> str:
    """Decode entities, strip HTML tags, NFKC-normalize so half/full-width
    digits and brackets compare cleanly. Whitespace is preserved (the
    token regex anchors on positions, not on whitespace)."""
    if not isinstance(raw, str) or not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return text


def _has_lineup_keyword(text: str) -> bool:
    return any(kw in text for kw in LINEUP_KEYWORDS)
