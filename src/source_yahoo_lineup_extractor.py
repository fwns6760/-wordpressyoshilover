"""NOMOTOKE-INTAKE-LINEUP-001 — Yahoo Sportsnavi NPB game preview /
lineup HTML parser. Pure offline parser, no network call here.

Goal
====

Lift the starting lineup tables (1番〜9番 batting order + 守備位置 +
選手名) out of the Yahoo Sportsnavi game preview HTML. The caller
fetches the preview page (typically
``https://baseball.yahoo.co.jp/npb/game/<id>/preview``) separately and
hands the raw HTML to this module.

Source-only contract: every name in the output is a literal substring
of the input HTML after tag stripping + entity decoding. The parser
NEVER infers a missing slot.

Output
======

``parse_yahoo_lineup_html(html) -> Tuple[List[Dict], List[Dict]]``

Each list entry: ``{"order": "1", "position": "中", "name": "○○ ○○"}``.
Returns ``([], [])`` when no recognisable lineup table is found, so
the caller can skip the lineup block gracefully.

Strategy
========

1. Find every ``<table>...</table>`` block that contains 「打順」 and
   either 「選手」 or 「打者」 in its body. These are the lineup
   tables Yahoo uses across all 12 NPB clubs.
2. For each candidate table, walk the ``<tr>`` rows; rows whose first
   cell is a 1-9 digit are treated as lineup rows.
3. Return up to 2 tables (one per team). Order: home team first when
   identifiable, otherwise the order Yahoo emits them.

Constraints
===========

- No LLM, no Gemini, no network call.
- No fabrication: skipped row when any of order / position / name is
  missing or contains tags after stripping.
- ``""`` / ``None`` inputs return ``([], [])``.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Dict, List, Optional, Tuple


_TABLE_RE = re.compile(r"<table\b[^>]*>(?P<body>.+?)</table>", re.DOTALL | re.IGNORECASE)
_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.+?)</tr>", re.DOTALL | re.IGNORECASE)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(?P<body>.+?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_DIGIT_RE = re.compile(r"^[0-9０-９]{1,2}$")
_FULLWIDTH_DIGITS = "０１２３４５６７８９"


def _normalize_digit(text: str) -> str:
    """Map a fullwidth-digit string to halfwidth. Returns the input
    unchanged when no fullwidth chars are present."""
    out = []
    for ch in text:
        idx = _FULLWIDTH_DIGITS.find(ch)
        if idx >= 0:
            out.append(str(idx))
        else:
            out.append(ch)
    return "".join(out)


def _strip_to_text(fragment: str) -> str:
    """Strip tags + decode entities + collapse whitespace."""
    if not fragment:
        return ""
    s = _TAG_RE.sub("", fragment)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _table_contains_lineup_markers(table_html: str) -> bool:
    """Heuristic: a Yahoo lineup table mentions 打順 + (選手 OR 打者)."""
    if not table_html:
        return False
    if "打順" not in table_html:
        return False
    return ("選手" in table_html) or ("打者" in table_html)


def _parse_lineup_rows(table_html: str) -> List[Dict[str, str]]:
    """Walk one table's ``<tr>`` rows and return cleaned lineup rows.

    Conservative: a row is accepted only when ``cells[0]`` is a 1-9
    digit (the batting order) and at least one of cells[1:] looks like
    a position label and one looks like a name.
    """
    out: List[Dict[str, str]] = []
    for row_m in _ROW_RE.finditer(table_html):
        row = row_m.group("body")
        cells_raw = [_strip_to_text(c.group("body")) for c in _CELL_RE.finditer(row)]
        cells = [c for c in cells_raw if c]
        if len(cells) < 3:
            continue
        order_cell = _normalize_digit(cells[0])
        if not _DIGIT_RE.match(order_cell):
            continue
        order_n = int(order_cell)
        if not (1 <= order_n <= 9):
            continue
        position = ""
        name = ""
        for cell in cells[1:]:
            if not position and (1 <= len(cell) <= 4) and any(
                k in cell for k in ("中", "右", "左", "一", "二", "三", "遊", "捕", "投", "DH", "打", "Ｄ")
            ):
                position = cell
                continue
            if not name and len(cell) >= 2 and not _DIGIT_RE.match(cell):
                # Drop trailing 「打/投」 marker if Yahoo concatenates it.
                cleaned = re.sub(r"\s*[（(].*?[)）]\s*$", "", cell)
                if cleaned and not cleaned.isdigit():
                    name = cleaned
        if not (position and name):
            continue
        out.append({"order": str(order_n), "position": position, "name": name})
    # Yahoo often emits 9 rows per team; keep the first 9 to drop any
    # benchmember spillover.
    return out[:9]


def parse_yahoo_lineup_html(
    html: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Return (home_lineup, away_lineup). Each list is up to 9 rows.

    Either or both may be empty when the parser cannot find a lineup
    table — callers MUST treat empty lists as "render no lineup block".
    """
    if not isinstance(html, str) or not html:
        return [], []
    candidates: List[List[Dict[str, str]]] = []
    for m in _TABLE_RE.finditer(html):
        tbl = m.group(0)
        if not _table_contains_lineup_markers(tbl):
            continue
        rows = _parse_lineup_rows(tbl)
        if rows:
            candidates.append(rows)
        if len(candidates) >= 2:
            break
    if not candidates:
        return [], []
    if len(candidates) == 1:
        return candidates[0], []
    return candidates[0], candidates[1]


__all__ = ["parse_yahoo_lineup_html"]
