"""Tests for src.analysis.insight_rank_query."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_rank_query as rq
from src.analysis import insight_defense_proxy as defense

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"


def _new_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def _seed_game(conn, *, game_id, date):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, league_label, one_line_summary, "
        "winning_pitcher, losing_pitcher, save_pitcher, source_url, "
        "source_kind, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, date, "中日", "home", 0, 0, "unknown", None, None, None, None, None,
         None, "test", "2026-05-13T00:00:00+00:00"),
    )


def _seed_batting(conn, *, game_id, player, AB, H, position="一"):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, "giants", 1, position, player, player, 0, AB, 0, H, 0, 0, "[]"),
    )


def _seed_pitching(conn, *, game_id, player, IP, ER=0, K=0, BB=0, HR=0, H=0):
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, pitches, BF, IP, "
        "H_allowed, HR_allowed, BB, HBP, K, WP, BK, R, ER) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, "giants", 1, player, player, None, None, None, IP,
         H, HR, BB, 0, K, 0, 0, ER, ER),
    )


# ─── known metrics ────────────────────────────────────────────────────────


def test_known_metrics_includes_all_categories():
    assert "OPS" in rq.KNOWN_METRICS
    assert "FIP" in rq.KNOWN_METRICS
    assert "RF_proxy" in rq.KNOWN_METRICS
    assert rq.KNOWN_METRICS["ERA"][1] is False  # lower is better
    assert rq.KNOWN_METRICS["OPS"][1] is True


def test_unknown_metric_returns_empty():
    conn = _new_db()
    assert rq.rank_players(conn, metric_name="WAR") == []


# ─── batting rank ─────────────────────────────────────────────────────────


def test_rank_players_orders_by_AVG_desc():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", player="A", AB=4, H=3)  # .750
    _seed_batting(conn, game_id="g1", player="B", AB=4, H=2)  # .500
    _seed_batting(conn, game_id="g1", player="C", AB=4, H=0)  # .000
    rows = rq.rank_players(conn, metric_name="AVG")
    assert [r.player_canonical for r in rows] == ["A", "B", "C"]
    assert rows[0].rank == 1
    assert rows[0].total == 3


def test_rank_players_respects_min_sample():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", player="A", AB=4, H=4)
    _seed_batting(conn, game_id="g1", player="B", AB=1, H=1)
    rows = rq.rank_players(conn, metric_name="AVG", min_sample=2)
    assert {r.player_canonical for r in rows} == {"A"}


def test_rank_players_filters_by_position():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", player="二者", AB=4, H=3, position="二")
    _seed_batting(conn, game_id="g1", player="一者", AB=4, H=3, position="一")
    rows = rq.rank_players(conn, metric_name="AVG", position_filter="二")
    assert {r.player_canonical for r in rows} == {"二者"}


# ─── pitching rank (lower is better) ──────────────────────────────────────


def test_rank_pitching_ERA_lower_is_better():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_pitching(conn, game_id="g1", player="ace", IP=9.0, ER=1)  # 1.00 ERA
    _seed_pitching(conn, game_id="g1", player="mid", IP=9.0, ER=3)  # 3.00 ERA
    _seed_pitching(conn, game_id="g1", player="bp", IP=9.0, ER=9)   # 9.00 ERA
    rows = rq.rank_players(conn, metric_name="ERA")
    assert [r.player_canonical for r in rows] == ["ace", "mid", "bp"]


def test_rank_pitching_K_per_9_higher_is_better():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_pitching(conn, game_id="g1", player="high", IP=9.0, K=12)
    _seed_pitching(conn, game_id="g1", player="low", IP=9.0, K=3)
    rows = rq.rank_players(conn, metric_name="K_per_9")
    assert rows[0].player_canonical == "high"


# ─── defense rank ─────────────────────────────────────────────────────────


def test_rank_defense_RF_proxy_requires_position_filter():
    conn = _new_db()
    rows = rq.rank_players(conn, metric_name="RF_proxy")
    assert rows == []


def test_rank_defense_RF_proxy_higher_better():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_game(conn, game_id="g2", date="2026-05-13")
    # Seed lineups + batting that produce defense_opportunities
    conn.execute(
        "INSERT INTO lineups (game_id, team_role, slot_order, player_display, "
        "player_canonical, position, batting_side) VALUES (?,?,?,?,?,?,?)",
        ("g1", "giants", 4, "A", "A", "二", None),
    )
    conn.execute(
        "INSERT INTO lineups (game_id, team_role, slot_order, player_display, "
        "player_canonical, position, batting_side) VALUES (?,?,?,?,?,?,?)",
        ("g2", "giants", 4, "B", "B", "二", None),
    )
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("g1", "opponent", 1, "中", "X", "X", 0, 4, 0, 1, 0, 0,
         json.dumps(["二ゴロ", "二ゴロ", "二ゴロ"], ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("g2", "opponent", 1, "中", "Y", "Y", 0, 4, 0, 2, 0, 0,
         json.dumps(["二前安", "二前安", "二ゴロ"], ensure_ascii=False)),
    )
    defense.rebuild_defense_for_game(conn, game_id="g1")
    defense.rebuild_defense_for_game(conn, game_id="g2")
    rows = rq.rank_players(conn, metric_name="RF_proxy", position_filter="二")
    # A converts 3/3, B converts 1/3 → A wins
    assert rows[0].player_canonical == "A"
    assert rows[0].metric_value == 1.0
    assert rows[-1].player_canonical == "B"


# ─── get_player_rank ──────────────────────────────────────────────────────


def test_get_player_rank_returns_specific_row():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", player="A", AB=4, H=3)
    _seed_batting(conn, game_id="g1", player="B", AB=4, H=2)
    r = rq.get_player_rank(conn, metric_name="AVG", player_canonical="B")
    assert r is not None
    assert r.rank == 2
    assert r.total == 2
    assert r.metric_value == 0.5


def test_get_player_rank_returns_none_for_missing_player():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", player="A", AB=4, H=3)
    assert rq.get_player_rank(conn, metric_name="AVG", player_canonical="ghost") is None
