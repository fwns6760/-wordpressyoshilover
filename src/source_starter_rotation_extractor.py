"""NOMOTOKE-LINEUP-FROM-STARTER-ROTATION-001 Phase 2C — pure offline
parser for 報知 / スポニチ / 巨人公式X starter-rotation tweets and articles
that announce upcoming pitcher rotation as ``<P1>→<P2>→<P3>`` arrow chains.

Production sample id=66418 (2026-05-12, hochi.news):

  巨人が先発ローテ再編　１５日からのＤｅＮＡ３連戦は
  井上温大→ウィットリー→竹丸和幸　フレッシュ布陣で貯金アップ

Conservative parser:

- Source must belong to the 報知 / スポニチ / 巨人公式X family
  (same allowlist as ``source_hochi_compact_lineup_extractor``).
- Title or summary must contain an arrow-chain with ≥ 2 pitcher names.
- A rotation keyword (先発ローテ / 予告先発 / etc.) must be present so
  unrelated arrow chains (``二塁打→三塁打``) don't fire.
- Each name must be present in ``config/giants_roster.json`` so we
  cannot accidentally promote opposing-team rotation announcements.
- Returns ``None`` on any gate failure (no silent skip — caller logs).

Renderer contract: rotation rows carry ``order`` (sequential 1..N
within the chain) and ``pitcher`` (full or surname).
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from typing import Any, Dict, List, Optional

# Reuse single source-of-truth roster + opponent helpers so the parser
# stays consistent with the hochi-compact and emoji extractors.
from src.source_hochi_compact_lineup_extractor import (
    extract_opponent_team_name as _extract_opponent_team_name,
    is_giants_player as _is_giants_player,
)


# ---------------------------------------------------------------------------
# Source allowlist (broader than the lineup parsers — rotation tweets can
# come from any 巨人-friendly publication that uses the arrow shorthand).
# ---------------------------------------------------------------------------

STARTER_ROTATION_SOURCE_NAMES: frozenset[str] = frozenset(
    {
        # hochi family
        "スポーツ報知巨人班X",
        "スポーツ報知X",
        "報知野球X",
        "スポーツ報知 巨人 tag",
        # sponichi family
        "スポニチ野球記者X",
        # 巨人公式X
        "巨人公式X",
        "読売ジャイアンツX",
        "TokyoGiants",
        # ASCII aliases
        "hochi_giants",
        "hochi_baseball",
        "SportsHochi",
        "SponichiYakyu",
    }
)

_STARTER_ROTATION_URL_SUBSTRINGS: tuple[str, ...] = (
    "hochi.news",
    "sponichi.co.jp",
    "/tokyogiants",
    "/hochi_giants",
    "/hochi_baseball",
    "/sportshochi",
    "/sponichiyakyu",
)


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Pitcher name char class: kanji / katakana / hiragana / UPPERCASE Latin
# / dot variants. Same as hochi/emoji extractors (excludes lowercase Latin
# so team-name fragments cannot bleed into the name).
_NAME_CHAR_CLASS = r"一-龥々ァ-ヴーぁ-んA-Z・．\.\-‐ー"

# Arrow separators recognised in starter-rotation prose / titles.
_ARROW_PATTERN = r"(?:→|⇒|⇨|⟶|->)"

# Arrow-chain detector. We need to confirm the text contains ≥ 1 arrow
# operator with name-class characters on both sides. Actual name extraction
# is done by ``_split_chain_into_names`` below using an arrow-split
# strategy so prefix prose (e.g. ``連戦は井上温大``) cannot bleed into the
# first name.
_ARROW_PRESENT_RE = re.compile(
    r"[" + _NAME_CHAR_CLASS + r"]\s*" + _ARROW_PATTERN + r"\s*[" + _NAME_CHAR_CLASS + r"]"
)

# Splitter on arrow operators (with optional surrounding whitespace).
_ARROW_SPLIT_RE = re.compile(r"\s*" + _ARROW_PATTERN + r"\s*")

# Strict name char class (no hiragana). Player surnames + given names
# are overwhelmingly kanji / katakana; excluding hiragana here lets the
# trailing-name extractor stop cleanly at particles like ``は`` that may
# appear in the prose prefix (``連戦は井上温大`` → ``井上温大``).
_NAME_STRICT_CHAR_CLASS = r"一-龥々ァ-ヴーA-Z・．\.\-‐ー"

# Pitcher-name suffix extractor: take the trailing run of strict name
# characters from a chain segment. Bounded to 2-8 chars.
_TRAILING_NAME_RE = re.compile(r"([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})\s*$")
# Leading name extractor: take the first run of strict name characters
# from the tail segment of the chain.
_LEADING_NAME_RE = re.compile(r"^\s*([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})")

# Lineup keyword used to gate the parser (avoid firing on unrelated
# arrow chains like ``二塁打→三塁打``).
_ROTATION_KEYWORDS: tuple[str, ...] = (
    "先発ローテ",
    "ローテ再編",
    "ローテ予告",
    "予告先発",
    "先発予告",
    "先発陣",
    "ローテーション",
    "先発オーダー",
    "ローテ",
)

# Conservative bounds. 2-name minimum keeps the parser useful for
# 2-game rotation tweets; 6-name max protects against runaway chains.
_MIN_ROTATION_LEN = 2
_MAX_ROTATION_LEN = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_starter_rotation_source(source_name: str = "", source_url: str = "") -> bool:
    """Return True when source belongs to the rotation-tweet allowlist."""
    name = (source_name or "").strip()
    if name in STARTER_ROTATION_SOURCE_NAMES:
        return True
    if "報知" in name or "スポニチ" in name or "巨人公式" in name:
        return True
    url_lower = (source_url or "").lower()
    for fragment in _STARTER_ROTATION_URL_SUBSTRINGS:
        if fragment in url_lower:
            return True
    return False


def parse_starter_rotation(
    title: str,
    summary: str,
    source_name: str = "",
    source_url: str = "",
) -> Optional[Dict[str, Any]]:
    """Parse a starter-rotation arrow-chain tweet or article headline.

    Returns

        {
          "rotation": [{"order": "1", "pitcher": "井上温大"}, ...],
          "keyword": "<matched rotation keyword>",
          "raw_chain_length": <int>,
          "opponent_team_name": "<team name>",
        }

    or ``None`` when the input doesn't match the gate conditions.

    Gate (ALL required):

    1. Source belongs to the 報知 / スポニチ / 巨人公式X family.
    2. Combined text contains at least one rotation keyword.
    3. An arrow chain with ≥ ``_MIN_ROTATION_LEN`` names is present.
    4. ≥ 1 of those names is a 巨人 roster member.
    """
    if not is_starter_rotation_source(source_name, source_url):
        return None

    title_norm = _normalize_text(title or "")
    summary_norm = _normalize_text(summary or "")
    text = summary_norm if len(summary_norm) >= len(title_norm) else title_norm
    if not text:
        return None

    keyword = next((kw for kw in _ROTATION_KEYWORDS if kw in text), "")
    if not keyword:
        return None

    if not _ARROW_PRESENT_RE.search(text):
        return None

    names = _split_chain_into_names(text)
    if len(names) < _MIN_ROTATION_LEN:
        return None

    giants_hits = [n for n in names if _is_giants_player(n)]
    if not giants_hits:
        return None

    rotation = [
        {"order": str(i), "pitcher": name}
        for i, name in enumerate(names, start=1)
    ]
    opponent_team_name = _extract_opponent_team_name(text)
    return {
        "rotation": rotation,
        "keyword": keyword,
        "raw_chain_length": len(names),
        "opponent_team_name": opponent_team_name,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_text(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return text


def _split_chain_into_names(text: str) -> List[str]:
    """Find the longest arrow-chain in ``text`` and return the player
    names along it.

    Strategy:

    1. Walk every arrow operator. Each arrow has a name-class run on
       both sides; combine adjacent arrow positions into a single chain
       when they are separated only by name-class characters.
    2. For the leftmost (first) segment take its **trailing** name run
       (so prefix prose like ``連戦は井上温大`` yields ``井上温大``).
    3. For middle segments take the entire run (it's bounded by arrows
       on both sides — clean name).
    4. For the rightmost (last) segment take its **leading** name run
       (so suffix prose like ``竹丸和幸　フレッシュ布陣`` yields
       ``竹丸和幸``).

    Returns at most ``_MAX_ROTATION_LEN`` names, deduped, in order.
    """
    if not text:
        return []
    # Find all arrow positions; merge into chains where adjacent positions
    # share name-class context.
    arrows = list(re.finditer(_ARROW_PATTERN, text))
    if not arrows:
        return []
    # For simplicity, treat the whole region from just before the first
    # arrow's left context to just after the last arrow's right context
    # as the chain. We then split by arrows and trim per-segment.
    first = arrows[0]
    last = arrows[-1]
    # Expand left from `first.start()` over name-class chars (the head
    # segment may have prose prefix; we'll trim it).
    left = first.start()
    while left > 0 and re.match(r"[" + _NAME_CHAR_CLASS + r"]", text[left - 1]):
        left -= 1
    # Expand right from `last.end()` similarly.
    right = last.end()
    while right < len(text) and re.match(r"[" + _NAME_CHAR_CLASS + r"]", text[right]):
        right += 1
    chain_text = text[left:right]
    parts = _ARROW_SPLIT_RE.split(chain_text)
    if len(parts) < 2:
        return []
    names: List[str] = []
    seen: set[str] = set()
    for idx, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if idx == 0:
            # head — take trailing name
            m = _TRAILING_NAME_RE.search(part)
        elif idx == len(parts) - 1:
            # tail — take leading name
            m = _LEADING_NAME_RE.match(part)
        else:
            # middle — entire segment if it fits the name length bounds
            if 2 <= len(part) <= 8:
                m = re.match(r"^(.+)$", part)
            else:
                # fall back to leading name if segment exceeded bounds
                m = _LEADING_NAME_RE.match(part)
        if not m:
            continue
        name = m.group(1).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= _MAX_ROTATION_LEN:
            break
    return names
