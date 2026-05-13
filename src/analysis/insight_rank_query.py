"""INSIGHT-007 step 7d — cross-team rank query (12 NPB teams).

Given a metric + scope + (optional) position filter, return all
players ranked, plus the focus player's rank if specified.

This is the API the manual-intake-service "データ要望" tab calls when
the operator selects a player and asks "巨人の吉川は 2B 内で何位".

The module is **read-only** SQL against the local insight DB and does
not pull from GCS itself — callers supply the cached DB path (the
manual_intake_insight_query module already manages the GCS cache).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.analysis import insight_advanced_metrics as metrics
from src.analysis import insight_defense_proxy as defense

# Metrics we know how to rank. The values describe (kind, direction)
# where kind picks the aggregation backend and direction is whether
# higher = better (True) or lower = better (False, e.g. ERA / FIP).
KNOWN_METRICS: dict[str, tuple[str, bool]] = {
    # batting (higher = better)
    "AVG": ("batting", True),
    "OBP": ("batting", True),
    "SLG": ("batting", True),
    "OPS": ("batting", True),
    "ISO": ("batting", True),
    "wOBA": ("batting", True),
    "BB_pct": ("batting", True),
    "K_pct": ("batting", False),  # lower K% better for hitters
    "BABIP": ("batting", True),
    # pitching (lower = better unless noted)
    "ERA": ("pitching", False),
    "WHIP": ("pitching", False),
    "K_per_9": ("pitching", True),
    "BB_per_9": ("pitching", False),
    "HR_per_9": ("pitching", False),
    "K_BB": ("pitching", True),
    "FIP": ("pitching", False),
    "xFIP": ("pitching", False),
    # defense (higher = better, computed via insight_defense_proxy)
    "RF_proxy": ("defense", True),
    "UZR_proxy": ("defense", True),
}


@dataclass
class RankedRow:
    player_canonical: str
    team_code: Optional[str]
    metric_value: Optional[float]
    sample_size: int
    rank: int
    total: int


def _aggregate_batting(
    conn: sqlite3.Connection,
    *,
    since: Optional[str],
    until: Optional[str],
    position_filter: Optional[str],
) -> dict[str, tuple[metrics.BattingLine, Optional[str]]]:
    """Sum batting_logs into a BattingLine per player key.

    INSIGHT-007: player_canonical が NULL の非 Giants 選手 (roster
    未登録) も対象に含めるため、key は COALESCE(canonical, display)。
    team_name 列も一緒に拾って team_code 表示用に保持する。
    """
    sql = (
        "SELECT COALESCE(b.player_canonical, b.player_display) AS player_key, "
        "       b.team_name, "
        "       SUM(b.AB) AS ab, SUM(b.H) AS h "
        "FROM batting_logs b "
        "JOIN games g ON g.game_id = b.game_id "
        "WHERE COALESCE(b.player_canonical, b.player_display) IS NOT NULL "
        "  AND COALESCE(b.player_canonical, b.player_display) != ''"
    )
    params: list = []
    if since:
        sql += " AND g.game_date >= ?"
        params.append(since)
    if until:
        sql += " AND g.game_date <= ?"
        params.append(until)
    if position_filter:
        sql += " AND b.position LIKE ?"
        params.append(f"%{position_filter}%")
    sql += " GROUP BY player_key, b.team_name"

    out: dict[str, tuple[metrics.BattingLine, Optional[str]]] = {}
    for row in conn.execute(sql, params):
        key = row[0]
        team_name = row[1]
        line = metrics.BattingLine(
            AB=int(row[2] or 0),
            H=int(row[3] or 0),
        )
        # 同 key で複数 team_name (移籍等) があれば最後勝ち
        out[key] = (line, team_name)
    return out


def _aggregate_pitching(
    conn: sqlite3.Connection,
    *,
    since: Optional[str],
    until: Optional[str],
) -> dict[str, tuple[metrics.PitchingLine, Optional[str]]]:
    sql = (
        "SELECT COALESCE(p.player_canonical, p.player_display) AS player_key, "
        "       p.team_name, "
        "       SUM(p.IP) AS ip, SUM(p.H_allowed) AS h, "
        "       SUM(p.HR_allowed) AS hr, SUM(p.BB) AS bb, "
        "       SUM(p.HBP) AS hbp, SUM(p.K) AS k, SUM(p.ER) AS er, "
        "       SUM(p.R) AS r "
        "FROM pitching_logs p "
        "JOIN games g ON g.game_id = p.game_id "
        "WHERE COALESCE(p.player_canonical, p.player_display) IS NOT NULL "
        "  AND COALESCE(p.player_canonical, p.player_display) != ''"
    )
    params: list = []
    if since:
        sql += " AND g.game_date >= ?"
        params.append(since)
    if until:
        sql += " AND g.game_date <= ?"
        params.append(until)
    sql += " GROUP BY player_key, p.team_name"

    out: dict[str, tuple[metrics.PitchingLine, Optional[str]]] = {}
    for row in conn.execute(sql, params):
        key = row[0]
        team_name = row[1]
        line = metrics.PitchingLine(
            IP=float(row[2] or 0),
            H=int(row[3] or 0),
            HR=int(row[4] or 0),
            BB=int(row[5] or 0),
            HBP=int(row[6] or 0),
            SO=int(row[7] or 0),
            ER=int(row[8] or 0),
            R=int(row[9] or 0),
        )
        out[key] = (line, team_name)
    return out


def _compute_metric(
    metric_name: str,
    line,
) -> Optional[float]:
    """Dispatch to advanced_metrics function. Returns None on failure."""
    fn_map = {
        "AVG": metrics.avg,
        "OBP": metrics.obp,
        "SLG": metrics.slg,
        "OPS": metrics.ops,
        "ISO": metrics.iso,
        "wOBA": metrics.woba,
        "BB_pct": metrics.bb_pct,
        "K_pct": metrics.k_pct,
        "BABIP": metrics.babip,
        "ERA": metrics.era,
        "WHIP": metrics.whip,
        "K_per_9": metrics.k_per_9,
        "BB_per_9": metrics.bb_per_9,
        "HR_per_9": metrics.hr_per_9,
        "K_BB": metrics.k_bb_ratio,
        "FIP": metrics.fip,
        "xFIP": metrics.xfip,
    }
    fn = fn_map.get(metric_name)
    if fn is None:
        return None
    return fn(line)


def rank_players(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
    position_filter: Optional[str] = None,
    min_sample: int = 1,
) -> list[RankedRow]:
    """Return all qualifying players ranked by ``metric_name``."""
    if metric_name not in KNOWN_METRICS:
        return []
    kind, higher_is_better = KNOWN_METRICS[metric_name]

    rows: list[RankedRow] = []
    if kind == "batting":
        aggs = _aggregate_batting(
            conn, since=since, until=until, position_filter=position_filter,
        )
        for canonical, (line, team_name) in aggs.items():
            line = line.coerce()
            if line.AB < min_sample:
                continue
            value = _compute_metric(metric_name, line)
            if value is None:
                continue
            rows.append(RankedRow(
                player_canonical=canonical,
                team_code=team_name,
                metric_value=value,
                sample_size=line.AB,
                rank=0,
                total=0,
            ))
    elif kind == "pitching":
        aggs = _aggregate_pitching(conn, since=since, until=until)
        for canonical, (line, team_name) in aggs.items():
            if line.IP < min_sample:
                continue
            value = _compute_metric(metric_name, line)
            if value is None:
                continue
            rows.append(RankedRow(
                player_canonical=canonical,
                team_code=team_name,
                metric_value=value,
                sample_size=int(line.IP),
                rank=0,
                total=0,
            ))
    elif kind == "defense":
        rows = _rank_defense(
            conn,
            metric_name=metric_name,
            since=since,
            until=until,
            position_filter=position_filter,
            min_sample=min_sample,
        )

    # Sort + assign rank
    rows.sort(
        key=lambda r: (
            r.metric_value if higher_is_better else -r.metric_value
        ),
        reverse=True,
    )
    total = len(rows)
    for i, r in enumerate(rows, start=1):
        r.rank = i
        r.total = total
    return rows


def _rank_defense(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    since: Optional[str],
    until: Optional[str],
    position_filter: Optional[str],
    min_sample: int,
) -> list[RankedRow]:
    if not position_filter:
        return []  # defense rank only meaningful per position
    sql = (
        "SELECT d.player_canonical, d.team_code, "
        "       SUM(d.opportunities), SUM(d.converted_outs) "
        "FROM defense_opportunities d "
        "JOIN games g ON g.game_id = d.game_id "
        "WHERE d.position = ? AND d.player_canonical IS NOT NULL"
    )
    params: list = [position_filter]
    if since:
        sql += " AND g.game_date >= ?"
        params.append(since)
    if until:
        sql += " AND g.game_date <= ?"
        params.append(until)
    sql += " GROUP BY d.player_canonical, d.team_code"

    raw_rows = list(conn.execute(sql, params))
    if not raw_rows:
        return []

    league_total_opps = sum(int(r[2] or 0) for r in raw_rows)
    league_total_outs = sum(int(r[3] or 0) for r in raw_rows)
    if league_total_opps == 0:
        return []
    league_baseline = league_total_outs / league_total_opps

    out: list[RankedRow] = []
    for canonical, team_code, opps, outs in raw_rows:
        opps = int(opps or 0)
        if opps < min_sample:
            continue
        outs = int(outs or 0)
        rf_proxy = outs / opps
        if metric_name == "RF_proxy":
            value = round(rf_proxy, 4)
        else:  # UZR_proxy
            value = round(rf_proxy - league_baseline, 4)
        out.append(RankedRow(
            player_canonical=canonical,
            team_code=team_code,
            metric_value=value,
            sample_size=opps,
            rank=0,
            total=0,
        ))
    return out


def get_player_rank(
    conn: sqlite3.Connection,
    *,
    metric_name: str,
    player_canonical: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
    position_filter: Optional[str] = None,
    min_sample: int = 1,
) -> Optional[RankedRow]:
    """Convenience: rank everyone, return the row for ``player_canonical``."""
    rows = rank_players(
        conn,
        metric_name=metric_name,
        since=since,
        until=until,
        position_filter=position_filter,
        min_sample=min_sample,
    )
    for r in rows:
        if r.player_canonical == player_canonical:
            return r
    return None
