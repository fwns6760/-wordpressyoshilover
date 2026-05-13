"""NOMOTOKE-LINEUP-FROM-POSTGAME-001 Phase 2F — pure offline parser for
NPB公式 ``/scores/<YYYY>/<MMDD>/<away>-<home>-<N>/box.html`` static HTML.

Unlike Yahoo Sportsnavi, the NPB box page ships the full per-batter
打席結果 grid (打数 / 得点 / 安打 / 打点 / 盗塁 + 1-9 inning at-bat
results) and the per-pitcher line (投球数 / 打者 / 投球回 / 安打 /
本塁打 / 四球 / 死球 / 三振 / 暴投 / ボーク / 失点 / 自責点) as plain
HTML tables — no JavaScript rendering required, no API key, no rate-
limited endpoint. This module parses both teams' batter/pitcher tables
plus the inning grid and surfaces them in renderer-friendly dicts.

The page layout (verified against the 2026-05-10 中日 vs 巨人 fixture
committed to ``tests/fixtures/``):

  Table 1  — visual "VS" banner (skipped)
  Table 2  — inning grid (away then home, 9 innings + 計/H/E)
  Table 3  — away-team batter rows
  Table 4  — away-team pitcher rows
  Tables 5–10 — per-pitcher inning splits (small tables, skipped)
  Table 11 — home-team batter rows
  Table 12 — home-team pitcher rows
  Tables 13–17 — per-pitcher inning splits (skipped)

Returns ``None`` if the layout doesn't match — the calling fetcher
treats that as "no NPB box available, fall back to Yahoo or prose".

This module is purely text-in / dict-out, no I/O.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any, Dict, List, Optional


GIANTS_TEAM_TOKENS = ("読売ジャイアンツ", "巨人")


_TABLE_OPEN_RE = re.compile(r"<table\b[^>]*>", re.DOTALL)
_TABLE_CLOSE_RE = re.compile(r"</table\s*>", re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(?P<row>.+?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<(?:th|td)[^>]*>(?P<cell>.*?)</(?:th|td)>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NBSP_RE = re.compile(r"&nbsp;| ")


def _iter_outer_tables(html: str):
    """Yield (open_tag, inner_body) for each TOP-LEVEL ``<table>`` block.

    Stack-aware so nested tables (NPB's ``table_inning`` inside the
    pitcher 投球回 cell) don't terminate the outer match early.
    """
    pos = 0
    while True:
        m = _TABLE_OPEN_RE.search(html, pos)
        if not m:
            return
        open_start = m.start()
        body_start = m.end()
        depth = 1
        scan = body_start
        while depth > 0:
            next_open = _TABLE_OPEN_RE.search(html, scan)
            next_close = _TABLE_CLOSE_RE.search(html, scan)
            if not next_close:
                return  # malformed; bail
            if next_open and next_open.start() < next_close.start():
                depth += 1
                scan = next_open.end()
            else:
                depth -= 1
                if depth == 0:
                    inner_body = html[body_start:next_close.start()]
                    yield (m.group(0), inner_body)
                    pos = next_close.end()
                    break
                scan = next_close.end()


def _clean(value: str) -> str:
    if not isinstance(value, str):
        return ""
    text = _NBSP_RE.sub(" ", value)
    text = _HTML_TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _flatten_inner_tables(body: str) -> str:
    """Replace each fully-nested ``<table>...</table>`` block inside
    a row cell with its plain-text content (joined, no whitespace) so
    the outer row's ``<tr>...</tr>`` regex can still terminate cleanly.

    Uses the same stack-aware scan as ``_iter_outer_tables`` but
    REPLACES each top-level (at the current scope) table with its
    flattened text, which lets the outer row parser see a single value
    where the pitcher 投球回 cell used to embed ``<th>4</th><td>.1</td>``.
    """
    out: List[str] = []
    pos = 0
    while True:
        m = _TABLE_OPEN_RE.search(body, pos)
        if not m:
            out.append(body[pos:])
            return "".join(out)
        out.append(body[pos:m.start()])
        body_start = m.end()
        depth = 1
        scan = body_start
        while depth > 0:
            n_open = _TABLE_OPEN_RE.search(body, scan)
            n_close = _TABLE_CLOSE_RE.search(body, scan)
            if not n_close:
                out.append(body[m.start():])
                return "".join(out)
            if n_open and n_open.start() < n_close.start():
                depth += 1
                scan = n_open.end()
            else:
                depth -= 1
                if depth == 0:
                    inner = body[body_start:n_close.start()]
                    flat = _HTML_TAG_RE.sub(" ", inner)
                    flat = _WS_RE.sub("", flat)
                    out.append(flat)
                    pos = n_close.end()
                    break
                scan = n_close.end()


def _split_rows(table_body: str) -> List[List[str]]:
    # Flatten any nested <table> blocks first so the outer row's
    # non-greedy </tr> match doesn't terminate on an inner row.
    flat = _flatten_inner_tables(table_body)
    rows: List[List[str]] = []
    for m in _ROW_RE.finditer(flat):
        cells = [_clean(c) for c in _CELL_RE.findall(m.group("row"))]
        rows.append(cells)
    return rows


_INNING_HEADER = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "計")
_BATTER_HEADER = ("守備", "選手", "打数", "得点", "安打", "打点", "盗塁")
_PITCHER_HEADER = ("投手", "投球数", "打者", "投球回", "安打", "本塁打")


def _is_inning_table(rows: List[List[str]]) -> bool:
    return bool(rows) and all(tok in rows[0] for tok in _INNING_HEADER[:5])


def _is_batter_table(rows: List[List[str]]) -> bool:
    return bool(rows) and all(tok in rows[0] for tok in _BATTER_HEADER[:5])


def _is_pitcher_table(rows: List[List[str]]) -> bool:
    return bool(rows) and all(tok in rows[0] for tok in _PITCHER_HEADER[:5])


def _parse_inning_table(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Header + 2 team rows (away first, home second)."""
    result: List[Dict[str, Any]] = []
    for row in rows[1:3]:
        if len(row) < 11:
            continue
        team_label = row[0]
        innings = row[1:10]
        total_str = row[10] if len(row) > 10 else ""
        try:
            total = int(total_str)
        except ValueError:
            try:
                total = int(re.sub(r"[^\d]", "", total_str) or "0")
            except ValueError:
                total = 0
        short = team_label.split()[-1] if team_label else ""
        result.append(
            {
                "name": short or team_label,
                "full_name": team_label,
                "innings": innings,
                "total": total,
            }
        )
    return result


def _parse_batter_rows(rows: List[List[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) < 8:
            continue
        order = row[0]
        position = row[1]
        name = row[2]
        if not name:
            continue
        atbats = row[8:17] if len(row) >= 17 else row[8:]
        atbats = atbats + [""] * (9 - len(atbats))
        # NPB renders the defensive position with surrounding ``()``
        # (e.g. ``(二)``); strip them so downstream renderers and
        # tests see the bare position character (``二``).
        position_clean = re.sub(r"^\(([^)]+)\)$", r"\1", position or "")
        out.append(
            {
                "順": order or "",
                "守備": position_clean,
                "選手": name,
                "打数": row[3] if len(row) > 3 else "",
                "得点": row[4] if len(row) > 4 else "",
                "安打": row[5] if len(row) > 5 else "",
                "打点": row[6] if len(row) > 6 else "",
                "盗塁": row[7] if len(row) > 7 else "",
                "atbats": atbats[:9],
                "is_sub": not bool(order),
            }
        )
    return out


def _parse_pitcher_rows(rows: List[List[str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) < 8:
            continue
        name = row[1] if len(row) > 1 else ""
        if not name:
            continue
        # Phase 2H: row[0] carries the W/L/S/H indicator NPB box places
        # in the leading micro-column (``○`` win, ``●`` loss, ``S`` save,
        # ``H`` hold). Surface it so callers can derive a W/L/S summary
        # without a second HTTP fetch to Yahoo.
        result_mark = (row[0] or "").strip()
        out.append(
            {
                "選手": name,
                "result_mark": result_mark,
                "投球数": row[2] if len(row) > 2 else "",
                "打者": row[3] if len(row) > 3 else "",
                "投球回": row[4] if len(row) > 4 else "",
                "安打": row[5] if len(row) > 5 else "",
                "本塁打": row[6] if len(row) > 6 else "",
                "四球": row[7] if len(row) > 7 else "",
                "死球": row[8] if len(row) > 8 else "",
                "三振": row[9] if len(row) > 9 else "",
                "暴投": row[10] if len(row) > 10 else "",
                "ボーク": row[11] if len(row) > 11 else "",
                "失点": row[12] if len(row) > 12 else "",
                "自責点": row[13] if len(row) > 13 else "",
            }
        )
    return out


def _derive_wls_summary(
    giants_pitchers: List[Dict[str, Any]],
    opponent_pitchers: List[Dict[str, Any]],
    giants_name: str,
    opponent_name: str,
) -> Dict[str, Dict[str, str]]:
    """Phase 2H: collapse result_mark across both teams into the same
    ``{winning_pitcher, losing_pitcher, save_pitcher}`` dict shape that
    Yahoo facts produce. ``record`` is left empty because NPB box rows
    don't include the season cumulative tally.
    """
    out = {
        "winning_pitcher": {},
        "losing_pitcher": {},
        "save_pitcher": {},
    }
    pairs = (
        (giants_pitchers, giants_name),
        (opponent_pitchers, opponent_name),
    )
    for pitchers, team in pairs:
        for p in pitchers:
            mark = (p.get("result_mark") or "").strip()
            name = (p.get("選手") or "").strip()
            if not mark or not name:
                continue
            if mark == "○" and not out["winning_pitcher"]:
                out["winning_pitcher"] = {"team": team, "name": name, "record": ""}
            elif mark == "●" and not out["losing_pitcher"]:
                out["losing_pitcher"] = {"team": team, "name": name, "record": ""}
            elif mark == "S" and not out["save_pitcher"]:
                out["save_pitcher"] = {"team": team, "name": name, "record": ""}
    return out


def parse_npb_box_html(html: str, *, allow_non_giants: bool = False) -> Optional[Dict[str, Any]]:
    """Parse NPB公式 box.html into a renderer-friendly dict.

    Returns ``{giants_batters, giants_pitchers, opponent_batters,
    opponent_pitchers, opponent_team_name, inning_score}`` or ``None``
    when the table layout doesn't match or 巨人 is not in this game.
    """
    if not isinstance(html, str) or not html:
        return None

    inning: List[Dict[str, Any]] = []
    batter_tables: List[List[List[str]]] = []
    pitcher_tables: List[List[List[str]]] = []

    for open_tag, body in _iter_outer_tables(html):
        rows = _split_rows(body)
        if not rows:
            continue
        if _is_inning_table(rows) and not inning:
            inning = _parse_inning_table(rows)
        elif _is_batter_table(rows):
            batter_tables.append(rows)
        elif _is_pitcher_table(rows):
            pitcher_tables.append(rows)

    if not inning or len(batter_tables) < 2 or len(pitcher_tables) < 2:
        return None

    teams = [row.get("full_name", "") for row in inning[:2]]
    if any(tok in teams[0] for tok in GIANTS_TEAM_TOKENS):
        giants_idx = 0
        opp_idx = 1
    elif any(tok in teams[1] for tok in GIANTS_TEAM_TOKENS):
        giants_idx = 1
        opp_idx = 0
    elif allow_non_giants:
        # INSIGHT-007: 全 12 球団 ingest 用 fallback。Giants 不在試合では
        # team_role 'giants' / 'opponent' は単なるラベル扱い (team_name で
        # 識別する設計に切り替え済み)。inning_score の先頭を 'giants_*'
        # スロットに、2 番目を 'opponent_*' スロットに割り当てる。
        giants_idx = 0
        opp_idx = 1
    else:
        return None

    opponent_name = inning[opp_idx].get("name") or inning[opp_idx].get("full_name", "")
    giants_name = inning[giants_idx].get("name") or inning[giants_idx].get("full_name", "")

    giants_pitchers = _parse_pitcher_rows(pitcher_tables[giants_idx])
    opponent_pitchers = _parse_pitcher_rows(pitcher_tables[opp_idx])
    wls = _derive_wls_summary(
        giants_pitchers, opponent_pitchers, giants_name, opponent_name
    )

    return {
        "giants_batters":   _parse_batter_rows(batter_tables[giants_idx]),
        "giants_pitchers":  giants_pitchers,
        "opponent_batters": _parse_batter_rows(batter_tables[opp_idx]),
        "opponent_pitchers": opponent_pitchers,
        "opponent_team_name": opponent_name,
        "giants_team_name": giants_name,
        "inning_score": inning,
        "winning_pitcher": wls["winning_pitcher"],
        "losing_pitcher": wls["losing_pitcher"],
        "save_pitcher": wls["save_pitcher"],
    }
