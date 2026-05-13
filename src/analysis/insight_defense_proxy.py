"""INSIGHT-007 step 7d — defense_opportunities aggregation + Range Factor proxy.

True UZR requires per-batted-ball hit charts (x/y coordinates), which
NPB does not publish for free. We approximate by aggregating each
at-bat's *fielding position marker* from the box-score atbats text
(parsed by :mod:`insight_atbats_parser`) and computing two ranks per
``(player_canonical, position)``:

* ``RF_proxy``  = converted_outs / opportunities — what fraction of
  balls hit at this position the fielder turned into outs.
* ``UZR_proxy`` = RF_proxy − league_avg(RF_proxy at this position) —
  signed deviation from the league baseline.

Caveats (explicitly stated to the UI):

* This is **not** real UZR. We have no info about ball trajectory,
  exit velocity, or where the fielder was positioned. Two fielders
  with identical RF_proxy could differ wildly in real defensive value.
* Position attribution comes from text markers ("二ゴロ" → 二) which
  encode *where the ball ended up*, not always *who fielded it*. A
  fly to shallow left fielded by the LF and a deep fly to LF that
  the CF cut off both register as "左飛". Acceptable for crude rank.
* The fielder identity tracking depends on the lineup table; if a
  game's lineup wasn't ingested we attribute opportunities to the
  team but not the individual.

Hard constraints:

* DB read + ``defense_opportunities`` upsert only; no WP / Gemini / X.
* Idempotent: re-running for a game replaces (not appends) that game's
  rows for that team_code, so re-ingest after parser bug-fixes is safe.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.analysis import insight_atbats_parser as parser


@dataclass
class DefenseStats:
    opportunities: int = 0
    converted_outs: int = 0
    hits_allowed: int = 0
    errors: int = 0

    @property
    def rf_proxy(self) -> Optional[float]:
        if self.opportunities <= 0:
            return None
        return round(self.converted_outs / self.opportunities, 4)


def rebuild_defense_for_game(
    conn: sqlite3.Connection,
    *,
    game_id: str,
) -> dict[str, int]:
    """Re-derive ``defense_opportunities`` rows for the given game from
    its ``batting_logs.atbats_json`` rows.

    Returns counts: ``{"giants_positions": N, "opponent_positions": M}``.
    Idempotent — deletes existing rows for this game first.
    """
    import json
    # Wipe previous rows for the game (idempotent re-run safe).
    conn.execute("DELETE FROM defense_opportunities WHERE game_id = ?", (game_id,))

    # Resolve team codes / names for the game so the opposing-side
    # defense gets attributed correctly. We rely on the ``games`` row
    # plus aliases stored in config/all_teams_roster.json.
    team_codes = _team_codes_for_game(conn, game_id)
    if team_codes is None:
        return {"giants_positions": 0, "opponent_positions": 0}

    # Iterate Giants batters → opportunities go to opponent's defense.
    # Iterate opponent batters → opportunities go to Giants' defense.
    counts = {"giants_positions": 0, "opponent_positions": 0}
    for batter_role, defense_role in (
        ("giants", "opponent"),
        ("opponent", "giants"),
    ):
        defense_team_code = team_codes[defense_role]
        rows = conn.execute(
            "SELECT atbats_json FROM batting_logs "
            "WHERE game_id = ? AND team_role = ?",
            (game_id, batter_role),
        )
        agg: dict[str, parser.aggregate_for_defense] = {}  # type: ignore[name-defined]
        per_position: dict[str, DefenseStats] = {}
        for (atbats_json,) in rows:
            try:
                atbats = json.loads(atbats_json or "[]")
            except json.JSONDecodeError:
                continue
            position_agg = parser.aggregate_for_defense(atbats)
            for pos, slot in position_agg.items():
                acc = per_position.setdefault(pos, DefenseStats())
                acc.opportunities += slot["opportunities"]
                acc.converted_outs += slot["converted_outs"]
                acc.hits_allowed += slot["hits_allowed"]
                acc.errors += slot["errors"]
        for pos, stats in per_position.items():
            conn.execute(
                "INSERT OR REPLACE INTO defense_opportunities "
                "(game_id, team_code, position, player_canonical, "
                " opportunities, converted_outs, hits_allowed, errors) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    game_id,
                    defense_team_code,
                    pos,
                    _player_at_position(conn, game_id, defense_role, pos),
                    stats.opportunities,
                    stats.converted_outs,
                    stats.hits_allowed,
                    stats.errors,
                ),
            )
            counts[f"{defense_role}_positions"] += 1
    return counts


def _team_codes_for_game(conn: sqlite3.Connection, game_id: str) -> Optional[dict]:
    """Derive both sides' team_code for a game.

    INSIGHT-007: batting_logs.team_name 列を直接読む。両 team_role
    (giants / opponent) について team_name を取得し、それぞれ resolve
    して team_code に。Giants が試合に居なくても動く (label 'giants' は
    parse_npb_box_html allow_non_giants の名残で、実体は team_name 経由)。
    """
    rows = list(conn.execute(
        "SELECT DISTINCT team_role, team_name FROM batting_logs "
        "WHERE game_id = ?",
        (game_id,),
    ))
    role_to_code = {"giants": "unknown", "opponent": "unknown"}
    for r in rows or []:
        role = r[0] if not hasattr(r, "keys") else r["team_role"]
        name = r[1] if not hasattr(r, "keys") else r["team_name"]
        if role in role_to_code:
            role_to_code[role] = _resolve_team_code(name or "")
    # Fallback: rebuild from games.opponent for legacy / partial seeds.
    if role_to_code["opponent"] == "unknown":
        game_row = conn.execute(
            "SELECT opponent FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        if game_row:
            opp_name = game_row[0] if not hasattr(game_row, "keys") else game_row["opponent"]
            role_to_code["opponent"] = _resolve_team_code(opp_name or "")
    if role_to_code["giants"] == "unknown":
        role_to_code["giants"] = "g"
    return role_to_code


_TEAM_NAME_TO_CODE = {
    "巨人": "g", "読売": "g", "ジャイアンツ": "g",
    "阪神": "t", "タイガース": "t",
    "ヤクルト": "s", "スワローズ": "s",
    "広島": "c", "カープ": "c",
    "DeNA": "db", "横浜": "db", "ベイスターズ": "db",
    "中日": "d", "ドラゴンズ": "d",
    "ソフトバンク": "h", "ホークス": "h",
    "西武": "l", "ライオンズ": "l",
    "ロッテ": "m", "マリーンズ": "m",
    "楽天": "e", "イーグルス": "e",
    "オリックス": "b", "バファローズ": "b",
    "日本ハム": "f", "ファイターズ": "f",
}


def _resolve_team_code(name: str) -> str:
    if not name:
        return "unknown"
    for token, code in _TEAM_NAME_TO_CODE.items():
        if token in name:
            return code
    return "unknown"


def _player_at_position(
    conn: sqlite3.Connection,
    game_id: str,
    team_role: str,
    position_kanji: str,
) -> Optional[str]:
    """Best-effort lookup: who started this position for this team in
    this game? Reads ``lineups`` table; returns None when the lineup
    isn't ingested yet (the opportunities still get bucketed by
    team_code + position, just without a player attribution)."""
    row = conn.execute(
        "SELECT player_canonical FROM lineups "
        "WHERE game_id = ? AND team_role = ? AND position LIKE ?",
        (game_id, team_role, f"%{position_kanji}%"),
    ).fetchone()
    if not row:
        return None
    return row[0] if not hasattr(row, "keys") else row["player_canonical"]


def position_summary_for_player(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    position: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> DefenseStats:
    """Sum opportunities / converted_outs / hits / errors over the
    given window for a single player at a position."""
    sql = (
        "SELECT SUM(opportunities), SUM(converted_outs), SUM(hits_allowed), SUM(errors) "
        "FROM defense_opportunities d "
        "JOIN games g ON g.game_id = d.game_id "
        "WHERE d.player_canonical = ? AND d.position = ?"
    )
    params: list = [player_canonical, position]
    if since:
        sql += " AND g.game_date >= ?"
        params.append(since)
    if until:
        sql += " AND g.game_date <= ?"
        params.append(until)
    row = conn.execute(sql, params).fetchone()
    if not row or row[0] is None:
        return DefenseStats()
    return DefenseStats(
        opportunities=int(row[0] or 0),
        converted_outs=int(row[1] or 0),
        hits_allowed=int(row[2] or 0),
        errors=int(row[3] or 0),
    )


def league_position_baseline(
    conn: sqlite3.Connection,
    *,
    position: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Optional[float]:
    """League average RF_proxy at the given position."""
    sql = (
        "SELECT SUM(opportunities), SUM(converted_outs) "
        "FROM defense_opportunities d "
        "JOIN games g ON g.game_id = d.game_id "
        "WHERE d.position = ?"
    )
    params: list = [position]
    if since:
        sql += " AND g.game_date >= ?"
        params.append(since)
    if until:
        sql += " AND g.game_date <= ?"
        params.append(until)
    row = conn.execute(sql, params).fetchone()
    if not row or row[0] is None or int(row[0]) == 0:
        return None
    return round(int(row[1] or 0) / int(row[0]), 4)


def uzr_proxy_for_player(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    position: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Optional[float]:
    """Player's RF_proxy − league baseline. Positive = above average."""
    stats = position_summary_for_player(
        conn,
        player_canonical=player_canonical,
        position=position,
        since=since,
        until=until,
    )
    rf = stats.rf_proxy
    baseline = league_position_baseline(conn, position=position, since=since, until=until)
    if rf is None or baseline is None:
        return None
    return round(rf - baseline, 4)
