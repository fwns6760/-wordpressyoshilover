"""Tests for src.analysis.insight_defense_proxy."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_defense_proxy as defense

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"


def _new_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def _seed_game(conn, *, game_id, date, opponent="中日"):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, league_label, one_line_summary, "
        "winning_pitcher, losing_pitcher, save_pitcher, source_url, "
        "source_kind, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, date, opponent, "home", 5, 3, "win", None, None, None, None, None,
         None, "test", "2026-05-13T00:00:00+00:00"),
    )


def _seed_batting(conn, *, game_id, team_role, player, atbats, team_name=None):
    # default team_name follows the giants/opponent convention used by the
    # existing tests (Giants vs 中日 fixture)
    if team_name is None:
        team_name = "巨人" if team_role == "giants" else "中日"
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, player_display, "
        "player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json, team_name) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, team_role, 1, player, player, 0, 4, 0, 1, 0, 0,
         json.dumps(atbats, ensure_ascii=False), team_name),
    )


def _seed_lineup(conn, *, game_id, team_role, slot, player, position):
    conn.execute(
        "INSERT INTO lineups (game_id, team_role, slot_order, player_display, "
        "player_canonical, position, batting_side) VALUES (?,?,?,?,?,?,?)",
        (game_id, team_role, slot, player, player, position, None),
    )


# ─── _resolve_team_code ───────────────────────────────────────────────────


def test_resolve_team_code_matches_known_aliases():
    assert defense._resolve_team_code("中日ドラゴンズ") == "d"
    assert defense._resolve_team_code("阪神タイガース") == "t"
    assert defense._resolve_team_code("広島") == "c"
    assert defense._resolve_team_code("DeNA") == "db"


def test_resolve_team_code_unknown_returns_unknown():
    assert defense._resolve_team_code("") == "unknown"
    assert defense._resolve_team_code("メジャーリーグ") == "unknown"


# ─── rebuild_defense_for_game ─────────────────────────────────────────────


def test_rebuild_creates_rows_for_both_sides():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12", opponent="中日")
    # Giants batters hit balls to opponent defense
    _seed_batting(conn, game_id="g1", team_role="giants", player="X",
                  atbats=["中前安", "二ゴロ", "右越本①"])
    # Opponent batters hit balls to Giants defense
    _seed_batting(conn, game_id="g1", team_role="opponent", player="Y",
                  atbats=["左飛", "遊ゴロ"])
    counts = defense.rebuild_defense_for_game(conn, game_id="g1")
    assert counts["giants_positions"] > 0
    assert counts["opponent_positions"] > 0
    rows = list(conn.execute(
        "SELECT team_code, position, opportunities, converted_outs, hits_allowed "
        "FROM defense_opportunities ORDER BY team_code, position"
    ))
    # Opponent (中日 = 'd') defense receives Giants batters' contact
    d_rows = [r for r in rows if r[0] == "d"]
    assert d_rows, "中日 defense rows missing"
    # 二ゴロ → 二 position, converted_out
    assert any(r[1] == "二" and r[3] >= 1 for r in d_rows)
    # 中前安 → 中, hit_allowed
    assert any(r[1] == "中" and r[4] >= 1 for r in d_rows)


def test_rebuild_idempotent():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12")
    _seed_batting(conn, game_id="g1", team_role="giants", player="X",
                  atbats=["二ゴロ", "二ゴロ"])
    defense.rebuild_defense_for_game(conn, game_id="g1")
    defense.rebuild_defense_for_game(conn, game_id="g1")  # re-run
    n = conn.execute(
        "SELECT SUM(opportunities) FROM defense_opportunities WHERE position = '二'"
    ).fetchone()[0]
    # 2 二ゴロ from Giants → 2 opportunities for opponent at 二 (idempotent: same)
    assert n == 2


def test_rebuild_lookup_player_via_lineup():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12", opponent="中日")
    # Opponent has 二塁手 in lineup
    _seed_lineup(conn, game_id="g1", team_role="opponent", slot=4,
                 player="田中", position="二")
    # Giants batter hits to second base
    _seed_batting(conn, game_id="g1", team_role="giants", player="X",
                  atbats=["二ゴロ"])
    defense.rebuild_defense_for_game(conn, game_id="g1")
    row = conn.execute(
        "SELECT player_canonical FROM defense_opportunities "
        "WHERE position = '二' AND team_code = 'd'"
    ).fetchone()
    assert row[0] == "田中"


# ─── position_summary_for_player ──────────────────────────────────────────


def test_position_summary_aggregates_across_games():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-10", opponent="中日")
    _seed_game(conn, game_id="g2", date="2026-05-12", opponent="中日")
    for gid in ("g1", "g2"):
        _seed_lineup(conn, game_id=gid, team_role="opponent", slot=4,
                     player="田中", position="二")
        _seed_batting(conn, game_id=gid, team_role="giants", player="X",
                      atbats=["二ゴロ", "二ゴロ", "二前安"])
        defense.rebuild_defense_for_game(conn, game_id=gid)
    stats = defense.position_summary_for_player(
        conn, player_canonical="田中", position="二",
    )
    # 2 games × 3 opportunities = 6
    assert stats.opportunities == 6
    assert stats.converted_outs == 4  # 4 ゴロ (out), 2 安 (hits)
    assert stats.hits_allowed == 2


def test_position_summary_returns_zeros_when_no_data():
    conn = _new_db()
    stats = defense.position_summary_for_player(
        conn, player_canonical="ghost", position="二",
    )
    assert stats.opportunities == 0
    assert stats.rf_proxy is None


# ─── league_position_baseline ─────────────────────────────────────────────


def test_league_baseline_aggregates_all_teams():
    conn = _new_db()
    _seed_game(conn, game_id="g1", date="2026-05-12", opponent="中日")
    _seed_batting(conn, game_id="g1", team_role="giants", player="X",
                  atbats=["二ゴロ", "二ゴロ", "二前安"])
    defense.rebuild_defense_for_game(conn, game_id="g1")
    baseline = defense.league_position_baseline(conn, position="二")
    # 3 opportunities, 2 outs → baseline = 2/3 ≈ .6667
    assert baseline == round(2 / 3, 4)


def test_league_baseline_none_when_no_opportunities():
    conn = _new_db()
    assert defense.league_position_baseline(conn, position="二") is None


# ─── uzr_proxy_for_player ─────────────────────────────────────────────────


def test_uzr_proxy_is_player_minus_league():
    conn = _new_db()
    # Two players at 二, one converts 3/3, one converts 1/3
    _seed_game(conn, game_id="g1", date="2026-05-10")
    _seed_game(conn, game_id="g2", date="2026-05-11")
    # Player A (Giants 二) converts 3/3 (in opponent batters' contact)
    _seed_lineup(conn, game_id="g1", team_role="giants", slot=4,
                 player="A", position="二")
    _seed_batting(conn, game_id="g1", team_role="opponent", player="X",
                  atbats=["二ゴロ", "二ゴロ", "二ゴロ"])
    defense.rebuild_defense_for_game(conn, game_id="g1")
    # Player B (Giants 二) converts 1/3
    _seed_lineup(conn, game_id="g2", team_role="giants", slot=4,
                 player="B", position="二")
    _seed_batting(conn, game_id="g2", team_role="opponent", player="Y",
                  atbats=["二ゴロ", "二前安", "二前安"])
    defense.rebuild_defense_for_game(conn, game_id="g2")

    baseline = defense.league_position_baseline(conn, position="二")
    # 6 opportunities, 4 outs → 4/6 = .6667
    assert baseline == round(4 / 6, 4)

    a = defense.uzr_proxy_for_player(conn, player_canonical="A", position="二")
    b = defense.uzr_proxy_for_player(conn, player_canonical="B", position="二")
    assert a is not None and a > 0
    assert b is not None and b < 0
