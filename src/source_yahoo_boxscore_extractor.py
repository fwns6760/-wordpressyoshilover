"""NOMOTOKE-POSTGAME-FROM-NPB-BOXSCORE-001 — pure offline parser for the
Yahoo Sportsnavi NPB game-detail page.

Phase scope (this module)
=========================

- Parse a Yahoo Sportsnavi game-detail page (e.g.
  ``https://baseball.yahoo.co.jp/npb/game/<game_id>/index``) into the
  minimal facts ``render_postgame_card`` requires:
    - team_name (Giants when present)
    - score (final, e.g. ``5-3``)
    - result (win / loss / draw — derived from score from the Giants' POV)
    - date_label (e.g. ``2026年5月4日``)
    - league_label (e.g. ``セ・リーグ 7回戦``)
    - home / away (full team names)
    - inning_score (per-team list of {label, innings, total})
- NO network. The string parser is pure; the caller (CLI) supplies the
  raw HTML. Production rss_fetcher.py is NOT auto-connected — the only
  caller today is the operator-driven CLI.
- NO Gemini. Source-only fact extraction.

Scope NOT covered (deferred to follow-up tickets)
=================================================

- ``atbat_results`` / ``pitching_results`` rows. Yahoo encodes these in
  separate tabbed views; the renderer treats them as optional, and the
  postgame card renders cleanly with score + inning_score alone.
- ``opponent_lineup``. Optional in renderer.
- Multi-game date pages — the parser expects a single game's HTML.

The parser is conservative: when any required field is missing it
returns ``None``, the CLI then skips the URL with a structured reason
instead of producing a broken card.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

GIANTS_TEAM_TOKENS = ("読売ジャイアンツ", "巨人")


@dataclass(frozen=True)
class YahooBoxscoreFacts:
    home: str  # full team name
    away: str  # full team name
    home_short: str  # short label used inside inning table
    away_short: str
    home_total: int
    away_total: int
    inning_score: List[Dict[str, Any]]  # render-ready
    date_label: str  # 「2026年5月4日」
    league_label: str  # 「セ・リーグ 7回戦」
    one_line_summary: str

    def giants_facts(self) -> Dict[str, Any]:
        """Return the renderer-shaped data_preview for Giants POV.

        Maps the parsed teams to ``team_name=巨人`` plus a derived
        win/loss/draw result from the Giants' total vs the opponent's.
        """
        if any(tok in self.home for tok in GIANTS_TEAM_TOKENS):
            giants_total, opp_total = self.home_total, self.away_total
        elif any(tok in self.away for tok in GIANTS_TEAM_TOKENS):
            giants_total, opp_total = self.away_total, self.home_total
        else:
            return {}
        if giants_total > opp_total:
            result = "win"
        elif giants_total < opp_total:
            result = "loss"
        else:
            result = "draw"
        return {
            "team_name": "巨人",
            "score": f"{giants_total}-{opp_total}",
            "result": result,
            "date_label": self.date_label,
            "league_label": self.league_label,
            "home": self.home,
            "away": self.away,
            "inning_score": self.inning_score,
            "one_line_summary": self.one_line_summary,
        }


# ---------------------------------------------------------------------------
# Internal regexes (kept narrow to the observed Yahoo HTML structure)
# ---------------------------------------------------------------------------


_TITLE_RE = re.compile(
    r"<title>\s*(?P<date>\d{4}年\d{1,2}月\d{1,2}日)\s*"
    r"(?P<home>[^v\s]+?)vs\.(?P<away>[^\s\-]+?)\s*-",
    re.DOTALL,
)
_GAME_ROUND_RE = re.compile(
    r'<p class="bb-gameRound">\s*([^<]+?)\s*</p>',
    re.DOTALL,
)
_INNING_TABLE_RE = re.compile(
    r'<table id="ing_brd"[^>]*>(?P<body>.+?)</table>',
    re.DOTALL,
)
_INNING_HEADER_TH_RE = re.compile(r"<th[^>]*>([^<]*)</th>", re.DOTALL)
_INNING_ROW_RE = re.compile(
    r'<tr class="bb-gameScoreTable__row">(?P<row>.+?)</tr>', re.DOTALL
)
_INNING_TEAM_RE = re.compile(
    r'<a[^>]*class="bb-gameScoreTable__team"[^>]*>([^<]+)</a>',
    re.DOTALL,
)
# Match an inning cell — explicitly exclude the team cell (which carries
# the ``bb-gameScoreTable__data--team`` modifier). The score itself is
# wrapped in an anchor (``<a class="bb-gameScoreTable__score">N</a>``);
# fall back to a bare digit if the anchor is absent (extra-inning empty
# cells render as ``-``).
_INNING_CELL_RE = re.compile(
    r'<td class="bb-gameScoreTable__data(?![^"]*--team)[^"]*"[^>]*>'
    r'\s*(?:<a[^>]*class="bb-gameScoreTable__score"[^>]*>([^<]+)</a>|([0-9０-９]+|-|x))\s*</td>',
    re.DOTALL,
)
_INNING_TOTAL_RE = re.compile(
    r'<td[^>]*class="bb-gameScoreTable__total[^"]*"[^>]*>'
    r"\s*([0-9０-９]+|-|x)\s*</td>",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_yahoo_game_html(html: str) -> Optional[YahooBoxscoreFacts]:
    """Return parsed facts or ``None`` when any required field is missing.

    Conservative on purpose — partial extraction would produce a
    half-broken postgame card. The caller (CLI) skips with a
    diagnostic when this returns ``None``.
    """
    if not isinstance(html, str) or not html:
        return None

    # 1. title → date / teams.
    m = _TITLE_RE.search(html)
    if not m:
        return None
    date_label = m.group("date").strip()
    home_full = html_lib.unescape(m.group("home").strip())
    away_full = html_lib.unescape(m.group("away").strip())
    if not (date_label and home_full and away_full):
        return None

    # 2. league_label.
    m = _GAME_ROUND_RE.search(html)
    league_label = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    if not league_label:
        return None

    # 3. inning table.
    m = _INNING_TABLE_RE.search(html)
    if not m:
        return None
    table_body = m.group("body")

    headers = [
        re.sub(r"\s+", "", h or "")
        for h in _INNING_HEADER_TH_RE.findall(table_body)
    ]
    if not headers:
        return None
    # Drop leading empty header (team column) and trailing 安/失 columns.
    inning_headers = [h for h in headers if h.isdigit()]
    if not inning_headers:
        return None

    rows = list(_INNING_ROW_RE.finditer(table_body))
    if len(rows) < 2:
        return None

    parsed_rows: List[Tuple[str, List[str], int]] = []
    for row in rows[:2]:
        row_html = row.group("row")
        team_match = _INNING_TEAM_RE.search(row_html)
        if not team_match:
            return None
        team_short = team_match.group(1).strip()
        # Per-inning numbers (anchor or plain text)
        innings: List[str] = []
        for cell_match in _INNING_CELL_RE.finditer(row_html):
            val = cell_match.group(1) or cell_match.group(2) or ""
            val = re.sub(r"\s+", "", val)
            if val:
                innings.append(val)
        # Trim to the inning header count.
        innings = innings[: len(inning_headers)]
        if not innings:
            return None
        # Total cells (計 + 安 + 失). Expect at least 計 first.
        totals = [
            re.sub(r"\s+", "", t or "")
            for t in _INNING_TOTAL_RE.findall(row_html)
        ]
        if not totals:
            return None
        try:
            total_runs = int(totals[0])
        except ValueError:
            return None
        parsed_rows.append((team_short, innings, total_runs))

    away_short, away_innings, away_total = parsed_rows[0]
    home_short, home_innings, home_total = parsed_rows[1]

    # Inning_score in renderer-friendly shape.
    # ``name`` key matches the postgame renderer's _render_inning_table
    # contract (it pulls the leftmost column from t.get('name')).
    inning_score = [
        {
            "name": away_short,
            "innings": away_innings,
            "total": away_total,
        },
        {
            "name": home_short,
            "innings": home_innings,
            "total": home_total,
        },
    ]

    one_line_summary = _build_one_line_summary(
        home_full=home_full,
        away_full=away_full,
        home_total=home_total,
        away_total=away_total,
    )

    return YahooBoxscoreFacts(
        home=home_full,
        away=away_full,
        home_short=home_short,
        away_short=away_short,
        home_total=home_total,
        away_total=away_total,
        inning_score=inning_score,
        date_label=date_label,
        league_label=league_label,
        one_line_summary=one_line_summary,
    )


# ---------------------------------------------------------------------------
# Broadcast (放送予定) parser — same Yahoo `/top` page carries a static
# 放送予定 table when the game has not started yet.
# ---------------------------------------------------------------------------


_BROADCAST_TABLE_RE = re.compile(
    r'(?s)<table[^>]*class="[^"]*bb-tableLeft--broadcast[^"]*"[^>]*>(?P<inner>.+?)</table>',
)
_BROADCAST_ROW_RE = re.compile(
    r"(?s)<tr[^>]*>"
    r"\s*<th[^>]*>(?P<media>[^<]+)</th>"
    r"\s*<td[^>]*>(?P<body>.+?)</td>"
    r"\s*</tr>"
)
_BROADCAST_CREDIT_BLOCK_RE = re.compile(
    r'(?s)<div[^>]*class="bb-tableLeft__broadcast"[^>]*>.*?</div>'
)
_BROADCAST_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BROADCAST_WS_RE = re.compile(r"\s+")


def parse_yahoo_broadcast_html(html: str) -> Optional[Dict[str, Any]]:
    """Parse the 放送予定 table on a Yahoo Sportsnavi `/top` page.

    Returns ``{rows: [{media, channel, ...}, ...], home, away, date_label,
    league_label}`` or ``None`` when the broadcast block isn't present
    (game already started — the section is replaced by live score).

    Reuses :func:`parse_yahoo_game_html` for the title / round metadata
    so the broadcast card has full game context.
    """
    if not isinstance(html, str) or not html:
        return None
    table_match = _BROADCAST_TABLE_RE.search(html)
    if not table_match:
        return None
    rows: List[Dict[str, str]] = []
    for row_match in _BROADCAST_ROW_RE.finditer(table_match.group("inner")):
        media_label = _BROADCAST_WS_RE.sub("", row_match.group("media")).strip()
        body_html = row_match.group("body")
        # Drop the credit footer block before stripping tags.
        body_clean = _BROADCAST_CREDIT_BLOCK_RE.sub("", body_html)
        body_text = _BROADCAST_HTML_TAG_RE.sub("", body_clean)
        body_text = html_lib.unescape(body_text)
        body_text = _BROADCAST_WS_RE.sub(" ", body_text).strip()
        if not media_label or not body_text:
            continue
        rows.append(
            {
                "media": media_label,
                "channel": body_text,
                "time": "",
                "commentator": "",
                "play_by_play": "",
            }
        )
    if not rows:
        return None

    # Reuse the title / round parser so the card carries date / teams /
    # league context. parse_yahoo_game_html returns None when the inning
    # table is absent (pre-game state). Fall back to parsing the title
    # block directly when that happens.
    facts = parse_yahoo_game_html(html)
    if facts is not None:
        date_label = facts.date_label
        league_label = facts.league_label
        home = facts.home
        away = facts.away
    else:
        title_m = _TITLE_RE.search(html)
        round_m = _GAME_ROUND_RE.search(html)
        if not title_m:
            return None
        date_label = title_m.group("date").strip()
        home = html_lib.unescape(title_m.group("home").strip())
        away = html_lib.unescape(title_m.group("away").strip())
        league_label = (
            re.sub(r"\s+", " ", round_m.group(1)).strip() if round_m else ""
        )
    return {
        "rows": rows,
        "home": home,
        "away": away,
        "date_label": date_label,
        "league_label": league_label,
    }


def broadcast_card_payload(
    *,
    parsed: Dict[str, Any],
    source_url: str,
    source_label: str = "Yahoo!スポーツ NPB",
    source_name: str = "Yahoo!スポーツ",
) -> Dict[str, object]:
    return {
        "date_label": parsed["date_label"],
        "league_label": parsed["league_label"],
        "home": parsed["home"],
        "away": parsed["away"],
        "broadcasts": parsed["rows"],
        "source_url": source_url,
        "source_label": source_label,
        "source_name": source_name,
    }


def _build_one_line_summary(
    *,
    home_full: str,
    away_full: str,
    home_total: int,
    away_total: int,
) -> str:
    """Return a short Japanese summary line suitable for the postgame
    title appendix. Source-only — no LLM, no synthesis beyond combining
    the parsed facts."""
    if home_total > away_total:
        return f"{home_full}が{home_total}-{away_total}で勝利"
    if home_total < away_total:
        return f"{away_full}が{away_total}-{home_total}で勝利"
    return f"{home_full}と{away_full}が{home_total}-{away_total}で引き分け"
