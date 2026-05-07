"""NOMOTOKE-PLAYER-STATS-FROM-NPB-001 — pure offline parser for the
NPB.jp team-stat tables (read-only).

Data source
===========

NPB.jp publishes per-team batting and pitching tables at:
- ``https://npb.jp/bis/<year>/stats/idb1_g.html``  (Giants batting)
- ``https://npb.jp/bis/<year>/stats/idp1_g.html``  (Giants pitching)

Each page contains a single ``<table class="tablefix2">`` with a clean
``thead`` (column headers) and ``tbody`` (one row per player). This
parser extracts the table into ``{player_name: {column: value, ...}}``
so a higher-level CLI can render a ``nomotoke_card_player_stats_v1``
card for any specific player.

Cost / safety
=============

- Pure parser, NO network. Caller fetches HTML and passes it in.
- Source-only fact extraction — never adds tokens.
- Player name normalization: NPB renders names with a fullwidth space
  ("石塚 裕惺"); we collapse to ASCII space for matching but preserve
  the rendered form for the card.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Dict, List, Optional, Tuple

# NPB tables use class="tablefix2" for stat tables.
_TABLE_RE = re.compile(
    r'<table[^>]*class="tablefix2"[^>]*>(?P<body>.+?)</table>',
    re.DOTALL,
)
_THEAD_RE = re.compile(r"<thead[^>]*>(?P<inner>.+?)</thead>", re.DOTALL)
_TBODY_RE = re.compile(r"<tbody[^>]*>(?P<inner>.+?)</tbody>", re.DOTALL)
_TH_RE = re.compile(r"<th[^>]*>(?:<span>)?(?P<text>[^<]+?)(?:</span>)?</th>", re.DOTALL)
_TR_RE = re.compile(r"<tr[^>]*>(?P<inner>.+?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(?P<text>.*?)</td>", re.DOTALL)
_HTML_TAG_STRIP = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _clean_cell(raw: str) -> str:
    text = _HTML_TAG_STRIP.sub("", raw or "")
    text = html_lib.unescape(text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def _normalize_player_name(rendered: str) -> str:
    """Collapse ``石塚 裕惺`` → ``石塚裕惺`` for allowlist / search match.

    The original full-width-space form is preserved separately for
    rendering.
    """
    return re.sub(r"\s+", "", rendered or "").strip()


def parse_npb_team_stats_html(html: str) -> Optional[Dict[str, Dict[str, str]]]:
    """Parse an NPB team-stat HTML page.

    Returns ``{player_name: {column: value}}`` keyed by the
    space-stripped player name. Returns ``None`` when the structure
    doesn't match (no tablefix2 / no thead / no tbody / no rows).
    """
    if not isinstance(html, str) or not html:
        return None
    table_m = _TABLE_RE.search(html)
    if not table_m:
        return None
    table_body = table_m.group("body")

    thead_m = _THEAD_RE.search(table_body)
    tbody_m = _TBODY_RE.search(table_body)
    if not (thead_m and tbody_m):
        return None

    columns = [
        _clean_cell(m.group("text"))
        for m in _TH_RE.finditer(thead_m.group("inner"))
    ]
    if not columns:
        return None

    rows: Dict[str, Dict[str, str]] = {}
    for tr in _TR_RE.finditer(tbody_m.group("inner")):
        cells = [
            _clean_cell(m.group("text"))
            for m in _TD_RE.finditer(tr.group("inner"))
        ]
        if not cells or len(cells) != len(columns):
            continue
        rendered_name = cells[0]
        normalized = _normalize_player_name(rendered_name)
        if not normalized:
            continue
        record = {col: val for col, val in zip(columns, cells)}
        record["__rendered_name__"] = rendered_name
        rows[normalized] = record

    if not rows:
        return None
    return rows


def find_player_row(
    parsed: Dict[str, Dict[str, str]], query: str
) -> Optional[Tuple[str, Dict[str, str]]]:
    """Lookup by name. Accepts space-collapsed or fullwidth-space form."""
    if not parsed or not query:
        return None
    norm = _normalize_player_name(query)
    if norm in parsed:
        return norm, parsed[norm]
    # Fallback: prefix match (unique)
    matches = [k for k in parsed if k.startswith(norm) or norm in k]
    if len(matches) == 1:
        return matches[0], parsed[matches[0]]
    return None


def stats_card_payload(
    *,
    rendered_name: str,
    record: Dict[str, str],
    stat_kind: str,
    date_label: str,
    source_url: str,
    source_name: str = "NPB公式",
    source_label: str = "NPB.jp",
    team_name: str = "巨人",
) -> Dict[str, object]:
    """Build the renderer-shaped data_preview for player_stats_v1.

    The renderer expects:
      team_name, player_name, stat_kind ("batting"/"pitching"),
      stats_columns (list of column headers),
      stats_rows (list of dicts with keys matching stats_columns),
      date_label.
    """
    columns = [k for k in record.keys() if k != "__rendered_name__"]
    return {
        "team_name": team_name,
        "player_name": rendered_name.strip(),
        "stat_kind": stat_kind,
        "stats_columns": columns,
        "stats_rows": [
            {col: record.get(col, "") for col in columns},
        ],
        "date_label": date_label,
        "source_url": source_url,
        "source_name": source_name,
        "source_label": source_label,
    }
