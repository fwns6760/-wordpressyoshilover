"""Tests for src.analysis.insight_multi_game_detector.

Uses synthetic multi-game SQLite data so detectors can be exercised in
isolation — INSIGHT-001 has only one fixture game, which is not enough
to assert anomaly detection. Each test seeds an in-memory SQLite from
``data/insight/schema.sql`` and asserts the detector output.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_etl, insight_multi_game_detector as det

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"


# ─── seeding helpers ────────────────────────────────────────────────────────


def _new_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def _seed_game(conn, *, game_id, date, opp="中日"):
    conn.execute(
        "INSERT OR REPLACE INTO games "
        "(game_id, game_date, opponent, home_away, giants_score, opp_score, result, "
        " league_label, one_line_summary, winning_pitcher, losing_pitcher, save_pitcher, "
        " source_url, source_kind, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, date, opp, "home", 0, 0, "unknown", None, None, None, None, None,
         None, "test", "2026-05-13T00:00:00+00:00"),
    )


def _seed_batting(conn, *, game_id, slot, display, canonical, AB, H,
                  HR=False, atbats=None):
    conn.execute(
        "INSERT OR REPLACE INTO batting_logs "
        "(game_id, team_role, slot_order, position, player_display, "
        " player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, "giants", slot, "中", display, canonical, 0,
         AB, 0, H, 0, 0, "[]"),
    )


def _seed_pitching(conn, *, game_id, order, display, canonical,
                   pitches=None, IP=None):
    conn.execute(
        "INSERT OR REPLACE INTO pitching_logs "
        "(game_id, team_role, appearance_order, player_display, player_canonical, "
        " result_mark, pitches, BF, IP, H_allowed, HR_allowed, BB, HBP, K, WP, BK, R, ER) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, "giants", order, display, canonical, None,
         pitches, None, IP, None, None, None, None, None, None, None, None, None),
    )


# ─── statistical helpers ───────────────────────────────────────────────────


def test_mean_stddev_basic():
    assert det.mean([1.0, 2.0, 3.0]) == 2.0
    assert det.stddev([1.0, 1.0]) == 0.0
    assert det.stddev([0.0]) == 0.0  # too small for sample → 0


def test_z_score_returns_none_for_tiny_baseline():
    assert det.z_score(5.0, []) is None
    assert det.z_score(5.0, [3.0]) is None  # n<2 → None


def test_z_score_returns_none_for_zero_variance():
    assert det.z_score(5.0, [3.0, 3.0, 3.0]) is None


def test_z_score_computes_expected_value():
    z = det.z_score(0.5, [0.2, 0.21, 0.22, 0.19, 0.20])
    assert z is not None
    assert z > 5  # clearly anomalous


# ─── detector 1: batter recent-window anomaly ──────────────────────────────


def test_batter_recent_anomaly_returns_none_when_insufficient():
    conn = _new_conn()
    # only 3 games, need recent_n + baseline_min_n = 5 + 10 = 15 by default
    for i in range(3):
        _seed_game(conn, game_id=f"g{i}", date=f"2026-04-{i+1:02d}")
        _seed_batting(conn, game_id=f"g{i}", slot=4, display="X", canonical="佐々木俊輔",
                      AB=4, H=1)
    res = det.detect_batter_recent_window_anomaly(conn, player_canonical="佐々木俊輔")
    assert res is None


def test_batter_recent_anomaly_detects_hot_streak():
    """baseline = .200 平均でばらつきあり、recent = .800 で z>1.5"""
    conn = _new_conn()
    # baseline 25 games at varied BA centered ~.200 (variance > 0)
    baseline_hits = [1, 0, 2, 1, 0, 1, 2, 0, 1, 1, 1, 0, 2, 1, 0,
                     1, 2, 0, 1, 1, 0, 2, 1, 0, 1]
    for i in range(25):
        gid = f"g{i:02d}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{(i % 28) + 1:02d}")
        _seed_batting(conn, game_id=gid, slot=4, display="X",
                      canonical="佐々木俊輔", AB=5, H=baseline_hits[i])
    for i in range(25, 30):
        gid = f"g{i:02d}"
        _seed_game(conn, game_id=gid, date=f"2026-05-{(i - 25) + 1:02d}")
        _seed_batting(conn, game_id=gid, slot=4, display="X",
                      canonical="佐々木俊輔", AB=5, H=4)
    res = det.detect_batter_recent_window_anomaly(conn, player_canonical="佐々木俊輔")
    assert res is not None
    assert res["signal_type"] == "batter_recent_hot"
    assert res["magnitude"] > 1.5
    assert res["priority"] in {1, 2}


def test_batter_recent_anomaly_detects_cold_streak():
    """baseline = .400 ばらつきあり、recent = .000 で z<-1.5"""
    conn = _new_conn()
    baseline_hits = [2, 1, 3, 2, 1, 2, 2, 3, 1, 2, 2, 1, 3, 2, 1,
                     2, 3, 1, 2, 2, 1, 3, 2, 1, 2]
    for i in range(25):
        gid = f"g{i:02d}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{(i % 28) + 1:02d}")
        _seed_batting(conn, game_id=gid, slot=3, display="X",
                      canonical="岡本和真", AB=4, H=baseline_hits[i])
    for i in range(25, 30):
        gid = f"g{i:02d}"
        _seed_game(conn, game_id=gid, date=f"2026-05-{(i - 25) + 1:02d}")
        _seed_batting(conn, game_id=gid, slot=3, display="X",
                      canonical="岡本和真", AB=4, H=0)  # .000 recent
    res = det.detect_batter_recent_window_anomaly(conn, player_canonical="岡本和真")
    assert res is not None
    assert res["signal_type"] == "batter_recent_cold"
    assert res["magnitude"] < -1.5


# ─── detector 2: batter hit streak ─────────────────────────────────────────


def test_batter_hit_streak_returns_none_when_no_streak():
    conn = _new_conn()
    for i in range(6):
        gid = f"g{i}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{i+1:02d}")
        # alternating hit / no-hit pattern
        _seed_batting(conn, game_id=gid, slot=1, display="平山", canonical="平山功太",
                      AB=4, H=1 if i % 2 == 0 else 0)
    res = det.detect_batter_hit_streak(conn, player_canonical="平山功太", min_streak=3)
    # trailing 1 game: i=5 has H=0 → streak=0
    assert res is None


def test_batter_hit_streak_detects_trailing_streak():
    conn = _new_conn()
    for i in range(7):
        gid = f"g{i}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{i+1:02d}")
        h = 1 if i >= 2 else 0  # last 5 games all have hits
        _seed_batting(conn, game_id=gid, slot=1, display="平山", canonical="平山功太",
                      AB=4, H=h)
    res = det.detect_batter_hit_streak(conn, player_canonical="平山功太", min_streak=4)
    assert res is not None
    assert res["signal_type"] == "batter_hit_streak"
    assert res["magnitude"] == 5.0


# ─── detector 3: pitcher workload ──────────────────────────────────────────


def test_pitcher_workload_returns_none_when_below_threshold():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-10")
    _seed_pitching(conn, game_id="g1", order=1, display="戸郷", canonical="戸郷翔征",
                   pitches=100, IP=6.0)
    res = det.detect_pitcher_recent_workload(
        conn, player_canonical="戸郷翔征", window_days=7, pitch_threshold=150,
    )
    assert res is None


def test_pitcher_workload_emits_warning_when_over_threshold():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-08")
    _seed_game(conn, game_id="g2", date="2026-05-10")
    _seed_game(conn, game_id="g3", date="2026-05-12")
    for gid, p in [("g1", 80), ("g2", 60), ("g3", 50)]:
        _seed_pitching(conn, game_id=gid, order=1, display="マルティネス",
                       canonical="ライデル・マルティネス", pitches=p, IP=1.0)
    res = det.detect_pitcher_recent_workload(
        conn, player_canonical="ライデル・マルティネス",
        window_days=7, pitch_threshold=150,
    )
    assert res is not None
    assert res["signal_type"] == "pitcher_workload_warning"
    assert res["magnitude"] == 190.0


# ─── detector 4: rest days anomaly ─────────────────────────────────────────


def test_rest_days_back_to_back():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-10")
    _seed_game(conn, game_id="g2", date="2026-05-11")
    for gid in ("g1", "g2"):
        _seed_pitching(conn, game_id=gid, order=1, display="中川",
                       canonical="中川皓太", pitches=15, IP=1.0)
    res = det.detect_pitcher_rest_days_anomaly(
        conn, player_canonical="中川皓太", min_rest_short=1, max_rest_long=14,
    )
    assert res is not None
    assert res["signal_type"] == "pitcher_rest_days_back_to_back"
    assert res["magnitude"] == 1.0


def test_rest_days_extended_layoff():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-04-20")
    _seed_game(conn, game_id="g2", date="2026-05-12")
    for gid in ("g1", "g2"):
        _seed_pitching(conn, game_id=gid, order=1, display="X", canonical="高梨雄平",
                       pitches=15, IP=1.0)
    res = det.detect_pitcher_rest_days_anomaly(
        conn, player_canonical="高梨雄平", min_rest_short=1, max_rest_long=14,
    )
    assert res is not None
    assert res["signal_type"] == "pitcher_rest_days_extended_layoff"
    assert res["magnitude"] == 22.0


def test_rest_days_normal_range_returns_none():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-05")
    _seed_game(conn, game_id="g2", date="2026-05-10")
    for gid in ("g1", "g2"):
        _seed_pitching(conn, game_id=gid, order=1, display="X", canonical="井上温大",
                       pitches=80, IP=5.0)
    res = det.detect_pitcher_rest_days_anomaly(conn, player_canonical="井上温大")
    assert res is None


# ─── orchestration ────────────────────────────────────────────────────────


def test_run_all_detectors_emits_finalized_rows():
    conn = _new_conn()
    # batters
    for i in range(7):
        gid = f"b{i}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{i+1:02d}")
        _seed_batting(conn, game_id=gid, slot=1, display="平山", canonical="平山功太",
                      AB=4, H=1)
    # pitchers
    _seed_game(conn, game_id="p1", date="2026-05-10")
    _seed_game(conn, game_id="p2", date="2026-05-11")
    for gid in ("p1", "p2"):
        _seed_pitching(conn, game_id=gid, order=1, display="中川",
                       canonical="中川皓太", pitches=15, IP=1.0)

    candidates = det.run_all_detectors(
        conn, run_id="r1", created_at="2026-05-13T00:00:00+00:00"
    )
    assert candidates
    # each candidate must conform to insert shape
    for c in candidates:
        assert c["run_id"] == "r1"
        assert "signal_type" in c
        assert c["status"] == "NEW"


def test_finalized_rows_insertable_via_insight_etl(tmp_path):
    """Output schema compatibility — rows must be insertable through
    insight_etl.insert_candidates."""
    conn = _new_conn()
    for i in range(7):
        gid = f"b{i}"
        _seed_game(conn, game_id=gid, date=f"2026-04-{i+1:02d}")
        _seed_batting(conn, game_id=gid, slot=1, display="平山", canonical="平山功太",
                      AB=4, H=1)
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates, notes) "
        "VALUES (?,?,?,?,?,?)",
        ("r1", "2026-05-13T00:00:00+00:00", "2026-04-01", "2026-05-13", 0, "test"),
    )
    candidates = det.run_all_detectors(conn, run_id="r1", created_at="2026-05-13T00:00:00+00:00")
    ids = insight_etl.insert_candidates(conn, candidates)
    assert len(ids) == len(candidates)
    n = conn.execute("SELECT COUNT(*) FROM article_candidates").fetchone()[0]
    assert n == len(candidates)
