"""NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2D — pure offline parser for
報知 / スポニチ / 巨人公式X postgame articles and tweets.

Production sample id=66565 (2026-05-12, hochi.news 2軍 postgame):

  title: 【巨人】"スミ１"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦
  body:  巨人２軍はＤｅＮＡに１―０で勝利した。

Phase 2D-A scope (this module): prose extraction of
- score (``X-Y`` / ``X―Y`` / ``X対Y`` variants, NFKC-normalised)
- winning pitcher name (matched against ``config/giants_roster.json``)
- result-type (勝利 / 敗戦 / 引き分け)
- league (1軍 / 2軍) — surface so the renderer can pick the heading
- opponent team name (reuses hochi extractor's helper)

Phase 2D-B (deferred follow-up): Yahoo boxscore integration for 1軍
postgame, providing inning-by-inning + at-bat + pitching tables. The
current module returns just the prose facts; the renderer can switch
to a richer block when Yahoo data is available.

Conservative parser — returns ``None`` when:
- Source is outside the allowlist.
- No postgame result keyword (勝利 / 敗戦 / 完封 / 完投 / 引き分け).
- No 巨人 mention or score pattern.
- Winning pitcher (when claimed) does not match the roster.
"""

from __future__ import annotations

import html as html_lib
import re
import unicodedata
from typing import Any, Dict, List, Optional

from src.source_hochi_compact_lineup_extractor import (
    extract_opponent_team_name as _extract_opponent_team_name,
    is_giants_player as _is_giants_player,
)


# ---------------------------------------------------------------------------
# Source allowlist (mirrors hochi / sponichi family)
# ---------------------------------------------------------------------------

POSTGAME_SOURCE_NAMES: frozenset[str] = frozenset(
    {
        "スポーツ報知巨人班X",
        "スポーツ報知X",
        "報知野球X",
        "スポーツ報知 巨人 tag",
        "スポニチ野球記者X",
        "巨人公式X",
        "読売ジャイアンツX",
        "TokyoGiants",
        "hochi_giants",
        "hochi_baseball",
        "SportsHochi",
        "SponichiYakyu",
    }
)
_POSTGAME_URL_SUBSTRINGS: tuple[str, ...] = (
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

# Score patterns — accept ``X-Y`` / ``X―Y`` / ``X－Y`` / ``X対Y``. After
# NFKC the full-width digits are ASCII, but we still accept any digit
# class on both sides.
_SCORE_RE = re.compile(
    r"(?<![0-9])(\d{1,2})\s*(?:[\-－―ー~対])\s*(\d{1,2})(?![0-9])"
)

# Result-type keywords that signal a postgame article. Order matters
# for keyword preference.
_RESULT_KEYWORDS: tuple[str, ...] = (
    "完封勝利",
    "サヨナラ勝利",
    "逆転勝利",
    "完投勝利",
    "勝利",
    "敗戦",
    "完封負け",
    "引き分け",
    "ドロー",
)

# Strict name char class (kanji / katakana / UPPER latin — no hiragana
# so prose particles don't bleed into the name).
_NAME_STRICT_CHAR_CLASS = r"一-龥々ァ-ヴーA-Z・．\.\-‐ー"

# Winning-pitcher prose patterns. Each captures the player surname /
# full name in ``g1``. The pitcher is then roster-validated.
_WIN_PITCHER_PATTERNS: tuple[re.Pattern, ...] = (
    # ``又木鉄平が... 勝利``
    re.compile(r"([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})\s*が\s*[^。、]*?勝利"),
    # ``又木鉄平が ... ３勝目``
    re.compile(r"([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})\s*が\s*[^。、]*?\d+\s*勝目"),
    # ``又木鉄平が ... 勝ち星``
    re.compile(r"([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})\s*が\s*[^。、]*?勝ち星"),
    # ``勝利投手 又木鉄平``
    re.compile(r"勝利投手\s*[:：]?\s*([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})"),
    # ``X投手が好投``(weak — keep last so stronger patterns win)
    re.compile(r"([" + _NAME_STRICT_CHAR_CLASS + r"]{2,8})\s*投手\s*が\s*[^。、]*?好投"),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_postgame_source(source_name: str = "", source_url: str = "") -> bool:
    name = (source_name or "").strip()
    if name in POSTGAME_SOURCE_NAMES:
        return True
    if "報知" in name or "スポニチ" in name or "巨人公式" in name:
        return True
    url_lower = (source_url or "").lower()
    for fragment in _POSTGAME_URL_SUBSTRINGS:
        if fragment in url_lower:
            return True
    return False


def parse_postgame_facts(
    title: str,
    summary: str,
    source_name: str = "",
    source_url: str = "",
) -> Optional[Dict[str, Any]]:
    """Return parsed postgame facts or ``None`` when the gates fail.

    Shape::

        {
          "score": "1-0",
          "winning_pitcher": "又木鉄平" | "",
          "result_type": "勝利" | "敗戦" | "引き分け",
          "league_level": "farm" | "first",
          "opponent_team_name": "DeNA",
        }

    Gates (ALL required):

    1. Source belongs to 報知 / スポニチ / 巨人公式X allowlist.
    2. Result keyword (``勝利`` / ``敗戦`` / etc.) present.
    3. Score pattern present.
    4. ``巨人`` keyword present (avoid firing on other-team postgame).
    """
    if not is_postgame_source(source_name, source_url):
        return None
    text = _normalize_text(f"{title or ''}\n{summary or ''}")
    if not text:
        return None

    # Must mention 巨人 to qualify as a Giants postgame.
    if "巨人" not in text:
        return None

    # Result keyword gate.
    result_type = ""
    for kw in _RESULT_KEYWORDS:
        if kw in text:
            # Normalise to one of the three rendered labels.
            if "勝" in kw:
                result_type = "勝利"
            elif "敗" in kw or "負け" in kw:
                result_type = "敗戦"
            else:
                result_type = "引き分け"
            break
    if not result_type:
        return None

    # Score gate.
    score_match = _SCORE_RE.search(text)
    if not score_match:
        return None
    score = f"{int(score_match.group(1))}-{int(score_match.group(2))}"

    # Winning-pitcher extraction (best-effort, roster-validated).
    winning_pitcher = ""
    for pat in _WIN_PITCHER_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        candidate = m.group(1).strip()
        if _is_giants_player(candidate):
            winning_pitcher = candidate
            break

    # League level: 2軍 / ファーム markers → farm, otherwise first.
    if any(m in text for m in ("二軍", "2軍", "ファーム", "ウエスタン", "イースタン")):
        league_level = "farm"
    else:
        league_level = "first"

    opponent_team_name = _extract_opponent_team_name(text)

    return {
        "score": score,
        "winning_pitcher": winning_pitcher,
        "result_type": result_type,
        "league_level": league_level,
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
