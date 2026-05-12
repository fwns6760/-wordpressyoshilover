"""NOMOTOKE-LINEUP-FROM-EMOJI-001 Phase 2B — pure offline parser for
emoji-form lineup tweets (巨人公式X 2軍 / sponichi 系).

Typical tweet shape (production sample 2026-05-10, source ``巨人公式X``):

  【二軍】巨人 vs ロッテ オーエンススタジアム江戸川🏟️ 13時試合開始⚾
  1️⃣ 三塚(D) 2️⃣ 小濱⑹ 3️⃣ 皆川⑼ 4️⃣ 萩尾⑺ 5️⃣ 荒巻⑶ 6️⃣ 浅野⑻
  7️⃣ 山瀬⑵ 8️⃣ 郡⑸ 9️⃣ 湯浅⑷ 🅿️ マタ

Format rules
------------

- Keycap emoji ``1️⃣..9️⃣`` (U+0031..U+0039 + optional U+FE0F + U+20E3)
  encodes the batting order.
- Player name follows the keycap (kanji / katakana / hiragana / UPPERCASE
  latin, 1-8 chars).
- Defensive position is appended as either:
  - ``(D)`` for DH (rendered as ``指``)
  - circled-number emoji ``⑴-⑼`` for 投/捕/一/二/三/遊/左/中/右
- The pitcher uses a separate ``🅿️ <name>`` (or unicode ``\U0001F17F``)
  pattern with no batting order — appended as ``投``.

Pattern is shared between 巨人公式X (TokyoGiants) 2軍 tweets and any
スポニチ tweets that use the same emoji convention. Source allowlist
covers both.

Same conservative gates as ``source_hochi_compact_lineup_extractor``:
- Source allowlist (name + URL substring).
- Minimum row count.
- Defer to ``source_x_lineup_extractor`` when the 巨人公式X clean form
  ``1番（中）<name>`` is detected.

Roster classification + opponent-team extraction is **reused** from
``source_hochi_compact_lineup_extractor`` so the two parsers stay
consistent in single-source-of-truth fashion.
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from typing import Any, Dict, List, Optional

# Reuse roster + opponent helpers from the hochi parser so both phases
# share a single roster source-of-truth and identical semantics.
from src.source_hochi_compact_lineup_extractor import (
    extract_opponent_team_name as _extract_opponent_team_name,
    is_giants_player as _is_giants_player,
)


# ---------------------------------------------------------------------------
# Source allowlist (emoji-format tweet sources)
# ---------------------------------------------------------------------------

EMOJI_LINEUP_SOURCE_NAMES: frozenset[str] = frozenset(
    {
        # 巨人公式X (TokyoGiants) — emoji format used for 2軍 lineup tweets.
        "巨人公式X",
        "読売ジャイアンツX",
        "TokyoGiants",
        # スポニチ 野球記者X — may use the same emoji convention.
        "スポニチ野球記者X",
        "SponichiYakyu",
    }
)

_EMOJI_LINEUP_URL_SUBSTRINGS: tuple[str, ...] = (
    "/tokyogiants",
    "/sponichiyakyu",
    "/yomiurigiants",
)


# ---------------------------------------------------------------------------
# Emoji code-point tables
# ---------------------------------------------------------------------------

# Parenthesised digit position markers (after NFKC normalisation the
# circled emoji ⑴ ⑵ … ⑼ collapse to ``(1)`` … ``(9)``; both forms are
# accepted here so the parser works both pre- and post-NFKC).
# Mapped to Japanese defensive position kanji:
#   1=投 / 2=捕 / 3=一 / 4=二 / 5=三 / 6=遊 / 7=左 / 8=中 / 9=右
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
    "H": "指",
    "指": "指",
}

# Pitcher squared-letter emoji 🅿 (U+1F17F) followed optionally by VS-16.
_PITCHER_EMOJI_RE = re.compile(r"\U0001F17F️?")

# Keycap digit emoji 1️⃣..9️⃣ — digit + optional VS-16 + Combining Enclosing
# Keycap (U+20E3). The digit is captured for downstream batting-order use.
_KEYCAP_DIGIT_RE = re.compile(r"([1-9])️?⃣")


# ---------------------------------------------------------------------------
# Token regex
# ---------------------------------------------------------------------------

# Name char class (mirrors the hochi parser): kanji / katakana / hiragana
# / UPPERCASE Latin / dot variants. Lowercase Latin intentionally excluded
# to avoid mis-parsing English team-name fragments.
_NAME_CHAR_CLASS = r"一-龥々ァ-ヴーぁ-んA-Z・．\.\-‐ー"

# Batter token: keycap digit + name + optional position marker.
# After NFKC normalisation, both ``(D)`` and the formerly circled ⑴..⑼
# emojis have collapsed to ``(D)``..``(9)`` paren form — match either.
_BATTER_TOKEN_RE = re.compile(
    r"([1-9])️?⃣"  # batting-order keycap (group 1 = digit)
    r"\s*"
    r"(?P<name>[" + _NAME_CHAR_CLASS + r"]{1,8})"
    r"\s*"
    r"(?:\((?P<pos_token>[DH指1-9])\))?"
)

# Pitcher token: 🅿️ + name (no batting order).
_PITCHER_TOKEN_RE = re.compile(
    r"\U0001F17F️?"
    r"\s*"
    r"(?P<name>[" + _NAME_CHAR_CLASS + r"]{1,8})"
)

# 巨人公式X clean form (``1番（中）ヘルナンデス``) — when present, this
# parser yields the field to ``source_x_lineup_extractor``.
_OFFICIAL_X_CLEAN_FORM_RE = re.compile(
    r"[1-9]番\s*[（(]\s*[投捕一二三遊左中右指]\s*[）)]"
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_ROW_COUNT = 8        # 8 fielders + DH (DH game) or 8 fielders + pitcher
_MAX_ROW_COUNT = 22       # bound runaway extraction
_MIN_KEYCAP_DENSITY = 5   # minimum distinct keycap digits to look like a lineup

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_emoji_lineup_source(source_name: str = "", source_url: str = "") -> bool:
    """Return True when source belongs to the emoji-format allowlist."""
    name = (source_name or "").strip()
    if name in EMOJI_LINEUP_SOURCE_NAMES:
        return True
    if "巨人公式" in name or "スポニチ" in name:
        return True
    url_lower = (source_url or "").lower()
    for fragment in _EMOJI_LINEUP_URL_SUBSTRINGS:
        if fragment in url_lower:
            return True
    return False


def parse_emoji_lineup(
    title: str,
    summary: str,
    source_name: str = "",
    source_url: str = "",
) -> Optional[Dict[str, Any]]:
    """Parse an emoji-format lineup tweet.

    Returns the same shape as
    ``source_hochi_compact_lineup_extractor.parse_hochi_compact_lineup``::

        {
          "lineup":             [{"order","position","name","team"}, ...],
          "keyword":            "<matched lineup keyword>",
          "raw_position_count": <int>,
          "opponent_team_name": "<team name from 【XXX】 or <team>戦>",
        }

    Returns ``None`` when the input doesn't look like an emoji-format
    lineup we can safely extract.

    Gate conditions (ALL required):

    1. ``source_name`` / ``source_url`` belongs to the emoji-format allowlist.
    2. Combined ``title + summary`` has ≥ ``_MIN_KEYCAP_DENSITY`` distinct
       keycap digits.
    3. 巨人公式X clean-form (``1番（中）...``) is NOT present (defer to
       ``source_x_lineup_extractor``).
    4. ≥ ``_MIN_ROW_COUNT`` extractable rows (batters + pitcher).
    """
    if not is_emoji_lineup_source(source_name, source_url):
        return None

    title_norm = _normalize_text(title or "")
    summary_norm = _normalize_text(summary or "")
    # X tweets typically pass identical (or near-identical) title+summary;
    # take whichever is longer to avoid double-counting.
    if len(summary_norm) >= len(title_norm):
        text = summary_norm or title_norm
    else:
        text = title_norm
    if not text:
        return None

    keycap_digits = _KEYCAP_DIGIT_RE.findall(text)
    if len(set(keycap_digits)) < _MIN_KEYCAP_DENSITY:
        return None

    if _OFFICIAL_X_CLEAN_FORM_RE.search(text):
        return None

    rows: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Batter rows (keycap + name + position marker).
    for m in _BATTER_TOKEN_RE.finditer(text):
        name = (m.group("name") or "").strip()
        if not name:
            continue
        pos_token = m.group("pos_token")
        if pos_token:
            position = _POSITION_MAP.get(pos_token, "")
        else:
            # Token without explicit position marker. Skip — these rows
            # cannot be classified by defensive position and would clutter
            # the rendered table. Keep the parser conservative.
            continue
        if not position:
            continue
        key = (position, name)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"position": position, "name": name})
        if len(rows) >= _MAX_ROW_COUNT:
            break

    # Pitcher row (🅿️ + name, no batting order).
    if len(rows) < _MAX_ROW_COUNT:
        for m in _PITCHER_TOKEN_RE.finditer(text):
            name = (m.group("name") or "").strip()
            if not name:
                continue
            key = ("投", name)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"position": "投", "name": name})
            if len(rows) >= _MAX_ROW_COUNT:
                break

    if len(rows) < _MIN_ROW_COUNT:
        return None

    final_rows: List[Dict[str, str]] = [
        {
            "order": str(index),
            "position": row["position"],
            "name": row["name"],
            "team": "巨人" if _is_giants_player(row["name"]) else "相手",
        }
        for index, row in enumerate(rows, start=1)
    ]

    keyword = "スタメン" if "スタメン" in text else "lineup"
    opponent_team_name = _extract_opponent_team_name(text)
    return {
        "lineup": final_rows,
        "keyword": keyword,
        "raw_position_count": len(rows),
        "opponent_team_name": opponent_team_name,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_text(raw: str) -> str:
    """Decode entities, strip HTML tags, and NFKC-normalise so half/full-
    width digits / parens compare cleanly. Whitespace is preserved (the
    token regex anchors on emojis, not whitespace).

    NOTE: NFKC is intentionally NOT applied to the **emoji portion** — it
    would dissolve VS-16 combinators and ZWJ sequences. We apply NFKC to
    the surrounding text only by letting NFKC run on the whole string and
    relying on emoji sequences being NFKC-stable (they are: keycap and
    enclosed-number sequences are not normalised away).
    """
    if not isinstance(raw, str) or not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return text
