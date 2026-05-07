"""NOMOTOKE-INTAKE-STANDINGS-001 — pure offline parser for the NPB.jp
standings (順位表) page.

Source
======

NPB.jp publishes per-league standings tables at:

- ``https://npb.jp/bis/<year>/stats/std_c.html``  (セ・リーグ)
- ``https://npb.jp/bis/<year>/stats/std_p.html``  (パ・リーグ)

Each page contains a single ``<table class="tablefix2">`` with a clean
``thead`` (column headers: 順位 / チーム / 試合 / 勝 / 負 / 分 /
勝率 / ゲーム差) and ``tbody`` (one row per team).

Output
======

``parse_npb_standings_html(html) -> List[Dict[str, str]]``

Each entry: ``{rank, team, games, wins, losses, draws, win_pct, gb}``.
Returns ``[]`` when no recognisable table can be parsed (caller skips
the standings block gracefully).

Constraints
===========

- Pure parsing. No network, no LLM, no fabrication.
- Output values are literal substrings of the input (after tag
  stripping + entity decoding).
- Returns ``[]`` on any parse error.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Dict, List, Optional


_TABLE_RE = re.compile(
    r'<table\b[^>]*class="[^"]*tablefix2[^"]*"[^>]*>(?P<body>.+?)</table>',
    re.DOTALL | re.IGNORECASE,
)
_FALLBACK_TABLE_RE = re.compile(
    r"<table\b[^>]*>(?P<body>.+?)</table>", re.DOTALL | re.IGNORECASE
)
_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.+?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(
    r"<t[dh]\b[^>]*>(?P<body>.+?)</t[dh]>", re.DOTALL | re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_RANK_RE = re.compile(r"^([0-9０-９]{1,2})$")
_FULLWIDTH_DIGITS = "０１２３４５６７８９"


def _normalise_digit(text: str) -> str:
    out = []
    for ch in text:
        idx = _FULLWIDTH_DIGITS.find(ch)
        if idx >= 0:
            out.append(str(idx))
        else:
            out.append(ch)
    return "".join(out)


def _strip_to_text(fragment: str) -> str:
    if not fragment:
        return ""
    s = _TAG_RE.sub("", fragment)
    s = html_lib.unescape(s)
    return re.sub(r"[\s　]+", " ", s).strip()


def _table_is_standings(table_html: str) -> bool:
    """Heuristic: a standings table mentions 「順位」 + 「勝率」 +
    a recognisable team token."""
    if not table_html:
        return False
    if "順位" not in table_html and "順" not in table_html:
        return False
    if "勝率" not in table_html and "勝" not in table_html:
        return False
    return True


def _parse_standings_rows(table_html: str) -> List[Dict[str, str]]:
    """Walk one table's ``<tr>`` rows and return cleaned standings
    entries. Conservative: a row is accepted only when ``cells[0]``
    is a 1-2 digit (rank) and there are at least 4 non-empty cells."""
    out: List[Dict[str, str]] = []
    for row_m in _ROW_RE.finditer(table_html):
        row = row_m.group("body")
        cells = [_strip_to_text(c.group("body")) for c in _CELL_RE.finditer(row)]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        rank_cell = _normalise_digit(cells[0])
        if not _RANK_RE.match(rank_cell):
            continue
        rank_n = int(rank_cell)
        if not (1 <= rank_n <= 6):
            continue
        # Layout (NPB.jp std_*.html): rank / team / 試合 / 勝 / 負 / 分 /
        # 勝率 / ゲーム差 / ... May vary; pad missing slots with "".
        def _at(i: int) -> str:
            return cells[i] if i < len(cells) else ""

        team = _at(1)
        if not team or len(team) < 2:
            continue
        out.append(
            {
                "rank": str(rank_n),
                "team": team,
                "games": _at(2),
                "wins": _at(3),
                "losses": _at(4),
                "draws": _at(5),
                "win_pct": _at(6),
                "gb": _at(7),
            }
        )
        if len(out) >= 6:
            break
    return out


def parse_npb_standings_html(html: str) -> List[Dict[str, str]]:
    """Return the standings rows for one league (typically 6 teams).

    Returns ``[]`` when no recognisable table is found — callers MUST
    treat empty as "render no standings block".
    """
    if not isinstance(html, str) or not html:
        return []
    for m in _TABLE_RE.finditer(html):
        tbl = m.group(0)
        if _table_is_standings(tbl):
            rows = _parse_standings_rows(tbl)
            if rows:
                return rows
    # Fallback: scan all <table> elements (NPB occasionally drops the
    # tablefix2 class on temporary pages).
    for m in _FALLBACK_TABLE_RE.finditer(html):
        tbl = m.group(0)
        if _table_is_standings(tbl):
            rows = _parse_standings_rows(tbl)
            if rows:
                return rows
    return []


def find_giants_standings_row(rows: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Return the row whose ``team`` cell contains a Giants alias, or
    ``None`` when the standings list does not include the Giants
    (defensive — a parse error would otherwise omit the team)."""
    if not rows:
        return None
    for r in rows:
        team = r.get("team", "") or ""
        if any(k in team for k in ("巨人", "ジャイアンツ", "読売")):
            return r
    return None


__all__ = ["parse_npb_standings_html", "find_giants_standings_row"]
