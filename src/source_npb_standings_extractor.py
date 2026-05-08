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


_TEAM_TOKENS = (
    "巨人", "ジャイアンツ", "読売",
    "阪神", "タイガース",
    "DeNA", "横浜", "ベイスターズ",
    "中日", "ドラゴンズ",
    "広島", "東洋", "カープ",
    "ヤクルト", "スワローズ",
    "ロッテ", "マリーンズ",
    "ソフトバンク", "ホークス",
    "西武", "ライオンズ",
    "オリックス", "バファローズ",
    "日本ハム", "ファイターズ",
    "楽天", "イーグルス",
)


def _table_is_standings(table_html: str) -> bool:
    """Heuristic: a standings table mentions 「勝率」 / 「勝」 + 「順位」 OR
    a recognisable team token.

    2026 NPB.jp は 順位 column を削除して team を行先頭に置く layout に
    変わったため、順位 keyword 必須にせず team token でも代替可能とする。
    """
    if not table_html:
        return False
    if "勝率" not in table_html and "勝" not in table_html:
        return False
    has_rank_col = "順位" in table_html or "順" in table_html
    has_team = any(t in table_html for t in _TEAM_TOKENS)
    return has_rank_col or has_team


def _parse_standings_rows(table_html: str) -> List[Dict[str, str]]:
    """Walk one table's ``<tr>`` rows and return cleaned standings
    entries.

    Supports two NPB.jp layouts:
      - Legacy: cells[0]=rank(1-6) / cells[1]=team / cells[2..]=stats
      - New (2026-): cells[0]=team / cells[1..]=stats、rank は行順から算出
        (header 行 cells[1]="試合" は数字でないので skip される)

    Conservative: 4+ non-empty cells が必要、team name >= 2 chars 必要。
    """
    out: List[Dict[str, str]] = []
    rank_counter = 0
    for row_m in _ROW_RE.finditer(table_html):
        row = row_m.group("body")
        cells = [_strip_to_text(c.group("body")) for c in _CELL_RE.finditer(row)]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue

        rank_cell = _normalise_digit(cells[0])
        if _RANK_RE.match(rank_cell) and 1 <= int(rank_cell) <= 6:
            # Legacy layout: cells[0]=rank, cells[1]=team, cells[2..]=stats
            rank_n = int(rank_cell)
            team = cells[1] if len(cells) > 1 else ""
            offset = 2
        else:
            # New layout: cells[0]=team, cells[1..]=stats, rank=行順
            team = cells[0]
            if len(team) < 2:
                continue
            # Header 行を skip: cells[1] が数字 (試合数) でなければ header
            games_check = _normalise_digit(cells[1] if len(cells) > 1 else "")
            if not games_check or not games_check.isdigit():
                continue
            rank_counter += 1
            rank_n = rank_counter
            offset = 1

        if not (1 <= rank_n <= 6):
            continue
        if not team or len(team) < 2:
            continue

        def _at(i: int) -> str:
            return cells[i] if i < len(cells) else ""

        out.append(
            {
                "rank": str(rank_n),
                "team": team,
                "games": _at(offset + 0),
                "wins": _at(offset + 1),
                "losses": _at(offset + 2),
                "draws": _at(offset + 3),
                "win_pct": _at(offset + 4),
                "gb": _at(offset + 5),
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
