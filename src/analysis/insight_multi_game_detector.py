"""INSIGHT-002 module 2 — multi-game detectors.

Operates on the SQLite database produced by :mod:`src.analysis.insight_etl`.
Pure-Python statistical helpers (no numpy/scipy) so the module works in
the existing vendor-only environment.

Detectors implemented in this MVP:

* :func:`detect_batter_recent_window_anomaly`
    z-score of a batter's "recent N games" metric vs a baseline window
    (default: recent 5 vs prior 25). Metric default: simple H/AB ratio,
    fall back to plate-appearance based when AB is missing.
* :func:`detect_batter_hit_streak`
    Consecutive game count where the batter recorded ≥1 hit.
* :func:`detect_pitcher_recent_workload`
    Sum of pitches in a trailing window (default: last 7 days of game
    dates present in the DB). Emits a candidate when > workload_threshold.
* :func:`detect_pitcher_rest_days_anomaly`
    Days between consecutive appearances of the same pitcher; emits a
    candidate when rest <= min_rest_short or >= max_rest_long.

All detectors:

* Require ``window_n`` (or its analogue) of actual data — return
  ``None`` / empty list when insufficient, **never** synthesize values.
* Operate per-player (`player_canonical` joinable).
* Emit dict rows compatible with :func:`insight_etl.insert_candidates`.

Hard constraints:

* Read-only SQL on the existing schema (`games` / `batting_logs` /
  `pitching_logs`). No DDL, no DELETE.
* No live HTTP, no WP I/O, no Gemini, no X API.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ─── statistical helpers (stdlib only) ──────────────────────────────────────


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean: empty input")
    return sum(values) / len(values)


def stddev(values: list[float], *, sample: bool = True) -> float:
    """Standard deviation. Sample (Bessel) by default; population if
    ``sample=False``. Returns 0.0 when len < 2 with sample=True."""
    if len(values) < 2 and sample:
        return 0.0
    if not values:
        return 0.0
    mu = mean(values)
    sq = [(v - mu) ** 2 for v in values]
    denom = (len(values) - 1) if sample else len(values)
    if denom <= 0:
        return 0.0
    return math.sqrt(sum(sq) / denom)


def z_score(value: float, baseline: list[float]) -> Optional[float]:
    if len(baseline) < 2:
        return None
    mu = mean(baseline)
    sd = stddev(baseline, sample=True)
    if sd == 0:
        return None
    return (value - mu) / sd


# ─── per-detector helpers ──────────────────────────────────────────────────


def _fetch_player_batting_history(
    conn: sqlite3.Connection,
    player_canonical: str,
) -> list[dict]:
    """Return per-game batting rows for ``player_canonical``, sorted by
    game_date ascending. Joins batting_logs to games for the date."""
    cur = conn.execute(
        """
        SELECT g.game_id, g.game_date,
               b.AB, b.R, b.H, b.RBI, b.SB,
               b.atbats_json, b.slot_order, b.position
        FROM batting_logs b
        JOIN games g ON g.game_id = b.game_id
        WHERE b.team_role = 'giants'
          AND b.player_canonical = ?
          AND b.AB IS NOT NULL
        ORDER BY g.game_date ASC, b.game_id ASC
        """,
        (player_canonical,),
    )
    return [dict(zip([d[0] for d in cur.description], row)) for row in cur]


def _fetch_player_pitching_history(
    conn: sqlite3.Connection,
    player_canonical: str,
) -> list[dict]:
    cur = conn.execute(
        """
        SELECT g.game_id, g.game_date,
               p.pitches, p.BF, p.IP, p.H_allowed, p.HR_allowed,
               p.BB, p.K, p.R, p.ER,
               p.appearance_order, p.result_mark
        FROM pitching_logs p
        JOIN games g ON g.game_id = p.game_id
        WHERE p.team_role = 'giants'
          AND p.player_canonical = ?
        ORDER BY g.game_date ASC, g.game_id ASC
        """,
        (player_canonical,),
    )
    return [dict(zip([d[0] for d in cur.description], row)) for row in cur]


# ─── detector 1: batter recent-window anomaly ──────────────────────────────


def detect_batter_recent_window_anomaly(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    recent_n: int = 5,
    baseline_min_n: int = 10,
    z_threshold: float = 1.5,
) -> Optional[dict]:
    """Return a candidate dict when the player's recent-N games batting
    average is ``z_threshold`` standard deviations away from the baseline
    of all prior games. ``None`` when insufficient data."""
    history = _fetch_player_batting_history(conn, player_canonical)
    if len(history) < recent_n + baseline_min_n:
        return None
    recent = history[-recent_n:]
    baseline = history[:-recent_n]

    def _ba(rows: list[dict]) -> Optional[float]:
        ab = sum(r["AB"] or 0 for r in rows)
        h = sum(r["H"] or 0 for r in rows)
        return (h / ab) if ab else None

    per_game_baseline = [
        (r["H"] / r["AB"]) for r in baseline if (r["AB"] or 0) > 0
    ]
    recent_ba = _ba(recent)
    if recent_ba is None or len(per_game_baseline) < 2:
        return None
    z = z_score(recent_ba, per_game_baseline)
    if z is None or abs(z) < z_threshold:
        return None
    direction = "hot" if z > 0 else "cold"
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": f"batter_recent_{direction}",
        "magnitude": round(z, 2),
        "baseline_value": f"baseline_ba={round(mean(per_game_baseline), 3)} n={len(per_game_baseline)}",
        "current_value": f"recent_ba={round(recent_ba, 3)} n={recent_n}",
        "window_label": f"last_{recent_n}_games",
        "comparison_target": "self_prior_games",
        "evidence": {
            "z_score": z,
            "recent_games": [r["game_id"] for r in recent],
            "baseline_n": len(per_game_baseline),
        },
        "priority": 1 if abs(z) >= 2.0 else 2,
        "notes": (
            f"直近{recent_n}試合の打率が自己過去 {len(per_game_baseline)}試合と比べ "
            f"z={round(z,2)} の{direction} ({direction=='hot' and '異常高値' or '異常低値'})"
        ),
    }


# ─── detector 2: batter hit streak ─────────────────────────────────────────


def detect_batter_hit_streak(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    min_streak: int = 5,
) -> Optional[dict]:
    """Count consecutive trailing games with ≥1 hit. Emit when ≥
    ``min_streak``."""
    history = _fetch_player_batting_history(conn, player_canonical)
    if not history:
        return None
    streak = 0
    streak_games: list[str] = []
    for row in reversed(history):
        if (row["H"] or 0) >= 1:
            streak += 1
            streak_games.append(row["game_id"])
        else:
            break
    if streak < min_streak:
        return None
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": "batter_hit_streak",
        "magnitude": float(streak),
        "baseline_value": None,
        "current_value": f"{streak}試合連続安打",
        "window_label": f"trailing_{streak}_games",
        "comparison_target": "consecutive",
        "evidence": {"streak_game_ids": list(reversed(streak_games))},
        "priority": 1 if streak >= 8 else 2,
        "notes": f"安打連続{streak}試合 (≥{min_streak} で起票)",
    }


# ─── detector 3: pitcher recent workload ───────────────────────────────────


def detect_pitcher_recent_workload(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    window_days: int = 7,
    pitch_threshold: int = 150,
) -> Optional[dict]:
    """Sum of pitches in trailing ``window_days`` (game date span).
    Emits when total > ``pitch_threshold``."""
    history = _fetch_player_pitching_history(conn, player_canonical)
    if not history:
        return None
    last_date = dt.date.fromisoformat(history[-1]["game_date"])
    cutoff = last_date - dt.timedelta(days=window_days)
    recent = [
        r for r in history
        if dt.date.fromisoformat(r["game_date"]) >= cutoff
    ]
    total_pitches = sum(r["pitches"] or 0 for r in recent)
    appearances = len(recent)
    if total_pitches <= pitch_threshold:
        return None
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": "pitcher_workload_warning",
        "magnitude": float(total_pitches),
        "baseline_value": f"threshold={pitch_threshold}",
        "current_value": f"{total_pitches}球 / {appearances}登板 / {window_days}日窓",
        "window_label": f"last_{window_days}_days",
        "comparison_target": "workload_threshold",
        "evidence": {
            "appearances": appearances,
            "game_ids": [r["game_id"] for r in recent],
            "total_pitches": total_pitches,
        },
        "priority": 1 if total_pitches >= pitch_threshold * 1.5 else 2,
        "notes": f"{window_days}日間球数{total_pitches}球(閾値{pitch_threshold}超過、勝ちパターン負荷集中の警告)",
    }


# ─── detector 4: pitcher rest-days anomaly ─────────────────────────────────


def detect_pitcher_rest_days_anomaly(
    conn: sqlite3.Connection,
    *,
    player_canonical: str,
    min_rest_short: int = 1,
    max_rest_long: int = 14,
) -> Optional[dict]:
    """Detect either a very short rest (≤ ``min_rest_short`` days)
    between consecutive appearances **or** a long rest (≥ ``max_rest_long``)
    that may signal injury / role change."""
    history = _fetch_player_pitching_history(conn, player_canonical)
    if len(history) < 2:
        return None
    last = history[-1]
    prev = history[-2]
    try:
        rest = (dt.date.fromisoformat(last["game_date"])
                - dt.date.fromisoformat(prev["game_date"])).days
    except Exception:
        return None
    if rest <= min_rest_short:
        flavor = "back_to_back"
        priority = 1
        notes = f"前回登板から{rest}日 — 連投警告 (≤{min_rest_short})"
    elif rest >= max_rest_long:
        flavor = "extended_layoff"
        priority = 2
        notes = f"前回登板から{rest}日 — 不在期間警告 (≥{max_rest_long})"
    else:
        return None
    return {
        "player_canonical": player_canonical,
        "player_display": player_canonical,
        "signal_type": f"pitcher_rest_days_{flavor}",
        "magnitude": float(rest),
        "baseline_value": None,
        "current_value": f"間隔{rest}日",
        "window_label": "last_2_appearances",
        "comparison_target": "rest_days",
        "evidence": {
            "prev_game_id": prev["game_id"],
            "last_game_id": last["game_id"],
            "prev_date": prev["game_date"],
            "last_date": last["game_date"],
        },
        "priority": priority,
        "notes": notes,
    }


# ─── orchestration ─────────────────────────────────────────────────────────


def all_giants_players_in_db(conn: sqlite3.Connection) -> tuple[list[str], list[str]]:
    """Return ``(batters, pitchers)`` of player_canonical values that
    appear in giants logs. Excludes NULL canonicals (uncanonicalized
    display names) since detectors need a stable key."""
    batters = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT player_canonical FROM batting_logs "
            "WHERE team_role='giants' AND player_canonical IS NOT NULL"
        )
    ]
    pitchers = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT player_canonical FROM pitching_logs "
            "WHERE team_role='giants' AND player_canonical IS NOT NULL"
        )
    ]
    return batters, pitchers


def run_all_detectors(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    created_at: str,
) -> list[dict]:
    """Run every detector for every Giants player canonical in the DB.
    Returns a list of candidate dicts ready for
    :func:`insight_etl.insert_candidates`."""
    candidates: list[dict] = []
    batters, pitchers = all_giants_players_in_db(conn)

    for p in batters:
        for fn in (detect_batter_recent_window_anomaly, detect_batter_hit_streak):
            res = fn(conn, player_canonical=p)
            if res:
                candidates.append(_finalize(res, run_id=run_id, created_at=created_at))

    for p in pitchers:
        for fn in (detect_pitcher_recent_workload, detect_pitcher_rest_days_anomaly):
            res = fn(conn, player_canonical=p)
            if res:
                candidates.append(_finalize(res, run_id=run_id, created_at=created_at))

    return candidates


def _finalize(row: dict, *, run_id: str, created_at: str) -> dict:
    evidence = row.pop("evidence", None)
    out = {
        "run_id": run_id,
        "game_id": None,  # multi-game signals are not tied to a single game
        "player_canonical": row.get("player_canonical"),
        "player_display": row.get("player_display"),
        "signal_type": row["signal_type"],
        "magnitude": row.get("magnitude"),
        "baseline_value": row.get("baseline_value"),
        "current_value": row.get("current_value"),
        "window_label": row.get("window_label"),
        "comparison_target": row.get("comparison_target"),
        "evidence_json": json.dumps(evidence, ensure_ascii=False) if evidence is not None else None,
        "priority": row.get("priority", 3),
        "status": "NEW",
        "created_at": created_at,
        "notes": row.get("notes"),
    }
    return out
