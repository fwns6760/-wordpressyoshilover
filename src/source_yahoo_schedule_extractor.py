"""NOMOTOKE-POSTGAME-AUTO-001 — pure offline parser for the Yahoo
Sportsnavi NPB schedule page; finds today's / yesterday's Giants game
ID for autonomous postgame draft creation.

Source: ``https://baseball.yahoo.co.jp/npb/schedule/?date=YYYY-MM-DD``

The schedule page lists each game in a ``bb-score`` block. We only
return games where Giants (読売 / 巨人) appears in the home or away
team field — cross-team mentions inside fan listings or news links
are ignored.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Dict, List, Optional

GIANTS_TEAM_TOKENS = ("巨人", "読売", "TokyoG", "ジャイアンツ")

_SCHEDULE_GAME_BLOCK_RE = re.compile(
    r'(?s)<a[^>]*class="bb-score__content"[^>]*href="(?P<href>/npb/game/(?P<gid>\d+)/[^"]+)"[^>]*>'
    r"(?P<inner>.+?)</a>"
)
_HOME_RE = re.compile(
    r'(?s)<p[^>]*class="bb-score__homeLogo[^"]*"[^>]*>(?P<inner>[^<]+)</p>'
)
_AWAY_RE = re.compile(
    r'(?s)<p[^>]*class="bb-score__awayLogo[^"]*"[^>]*>(?P<inner>[^<]+)</p>'
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_FINAL_MARKER_RE = re.compile(r"試合終了")
_CANCELLED_MARKER_RE = re.compile(r"中止|ノーゲーム")
_GAME_ID_FROM_URL_RE = re.compile(r"/npb/game/(\d+)/")


def _clean_text(raw: str) -> str:
    text = _HTML_TAG_RE.sub("", raw or "")
    text = html_lib.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _is_giants_team(text: str) -> bool:
    if not text:
        return False
    return any(tok in text for tok in GIANTS_TEAM_TOKENS)


def find_giants_games(html: str) -> List[Dict[str, str]]:
    """Return all Giants games on the schedule page.

    Each entry: ``{game_id, url, home, away, is_completed, is_cancelled}``.
    Filter applied:
      - Game block lists Giants as home OR away (cross-team mentions in
        news links don't qualify).

    Use ``find_giants_completed_games`` / ``find_giants_pregame_games``
    for state-narrowed slices.
    """
    if not isinstance(html, str) or not html:
        return []
    out: List[Dict[str, str]] = []
    for m in _SCHEDULE_GAME_BLOCK_RE.finditer(html):
        block = m.group("inner")
        gid = m.group("gid")
        href = m.group("href")
        home_m = _HOME_RE.search(block)
        away_m = _AWAY_RE.search(block)
        home = _clean_text(home_m.group("inner")) if home_m else ""
        away = _clean_text(away_m.group("inner")) if away_m else ""
        if not (_is_giants_team(home) or _is_giants_team(away)):
            continue
        is_cancelled = bool(_CANCELLED_MARKER_RE.search(block))
        is_completed = bool(_FINAL_MARKER_RE.search(block)) and not is_cancelled
        out.append(
            {
                "game_id": gid,
                "url": f"https://baseball.yahoo.co.jp{href}",
                "home": home,
                "away": away,
                "is_completed": is_completed,
                "is_cancelled": is_cancelled,
            }
        )
    return out


def find_giants_completed_games(html: str) -> List[Dict[str, str]]:
    """Return Giants games that have actually finished (試合終了 marker
    present and not cancelled / no-game)."""
    return [g for g in find_giants_games(html) if g["is_completed"]]


def find_giants_pregame_games(html: str) -> List[Dict[str, str]]:
    """Return Giants games that have NOT yet started.

    Excludes both completed (試合終了) and cancelled (中止 / ノーゲーム)
    games — broadcast / lineup work only makes sense for upcoming live
    games.
    """
    return [
        g for g in find_giants_games(html)
        if not g["is_completed"] and not g["is_cancelled"]
    ]
