"""Tests for src.analysis.insight_lineup_history.

Uses the 5/10 NPB box fixture + synthetic earlier-game lineups so the
slot-change detectors have ≥2 starts per player to compare.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.analysis import insight_etl, insight_lineup_history as lh

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "data" / "insight" / "schema.sql"
FIXTURE = REPO / "tests" / "fixtures" / "npb_score_2026_0510_d-g-08_box.html"


def _new_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def _seed_game(conn, *, game_id, date):
    conn.execute(
        "INSERT OR REPLACE INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, league_label, one_line_summary, "
        "winning_pitcher, losing_pitcher, save_pitcher, source_url, source_kind, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, date, "中日", "home", 0, 0, "unknown", None, None, None, None, None,
         None, "test", "2026-05-13T00:00:00+00:00"),
    )


def _seed_lineup(conn, *, game_id, slot, display, canonical, position="中"):
    conn.execute(
        "INSERT OR REPLACE INTO lineups (game_id, team_role, slot_order, player_display, "
        "player_canonical, position, batting_side) VALUES (?,?,?,?,?,?,?)",
        (game_id, "giants", slot, display, canonical, position, None),
    )


# ─── upsert from parsed box ────────────────────────────────────────────────


def test_upsert_lineup_from_parsed_box_with_real_fixture():
    from src.source_npb_postgame_extractor import parse_npb_box_html

    conn = _new_conn()
    _seed_game(conn, game_id="2026-05-10:d-g-08", date="2026-05-10")
    parsed = parse_npb_box_html(FIXTURE.read_text(encoding="utf-8"))
    assert parsed is not None
    n = lh.upsert_lineup_from_parsed_box(
        conn, game_id="2026-05-10:d-g-08", parsed=parsed,
    )
    # Giants starters in this game = 9 unique slots
    assert n == 9
    rows = list(conn.execute(
        "SELECT slot_order, player_display FROM lineups WHERE team_role='giants' "
        "ORDER BY slot_order"
    ))
    slots = [r[0] for r in rows]
    assert slots == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_upsert_lineup_excludes_subs():
    """is_sub rows must never be inserted as lineup."""
    from src.source_npb_postgame_extractor import parse_npb_box_html
    parsed = parse_npb_box_html(FIXTURE.read_text(encoding="utf-8"))
    conn = _new_conn()
    _seed_game(conn, game_id="g", date="2026-05-10")
    lh.upsert_lineup_from_parsed_box(conn, game_id="g", parsed=parsed)
    # giants_batters had > 9 entries (subs included); lineup table has only 9.
    n_lineup = conn.execute(
        "SELECT COUNT(*) FROM lineups WHERE team_role='giants'"
    ).fetchone()[0]
    n_batters = len(parsed.get("giants_batters") or [])
    assert n_lineup == 9
    assert n_batters >= 9


# ─── slot change jump ──────────────────────────────────────────────────────


def test_slot_jump_returns_none_when_only_one_start():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-10")
    _seed_lineup(conn, game_id="g1", slot=6, display="X", canonical="佐々木俊輔")
    assert lh.detect_slot_change_jump(conn, player_canonical="佐々木俊輔") is None


def test_slot_jump_detects_big_change():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-08")
    _seed_game(conn, game_id="g2", date="2026-05-10")
    _seed_lineup(conn, game_id="g1", slot=6, display="X", canonical="佐々木俊輔")
    _seed_lineup(conn, game_id="g2", slot=2, display="X", canonical="佐々木俊輔")
    res = lh.detect_slot_change_jump(
        conn, player_canonical="佐々木俊輔", min_jump=3,
    )
    assert res is not None
    assert res["signal_type"] == "lineup_slot_jump_up"  # 6 → 2 is "up"
    assert res["magnitude"] == 4.0


def test_slot_jump_ignored_when_below_min():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-08")
    _seed_game(conn, game_id="g2", date="2026-05-10")
    _seed_lineup(conn, game_id="g1", slot=3, display="X", canonical="岡本和真")
    _seed_lineup(conn, game_id="g2", slot=4, display="X", canonical="岡本和真")
    assert lh.detect_slot_change_jump(
        conn, player_canonical="岡本和真", min_jump=3,
    ) is None


# ─── first appearance in slot ──────────────────────────────────────────────


def test_first_appearance_detects_novel_slot():
    conn = _new_conn()
    for i, slot in enumerate([6, 7, 6, 1]):
        gid = f"g{i}"
        _seed_game(conn, game_id=gid, date=f"2026-05-{i+1:02d}")
        _seed_lineup(conn, game_id=gid, slot=slot, display="X", canonical="平山功太")
    res = lh.detect_first_appearance_in_slot(conn, player_canonical="平山功太")
    assert res is not None
    assert res["current_value"] == "今試合1番"
    # raw detector returns ``evidence`` dict; finalize converts to evidence_json
    assert res["evidence"]["prior_slots"] == [6, 7]
    assert res["evidence"]["current_slot"] == 1


def test_first_appearance_returns_none_when_slot_seen_before():
    conn = _new_conn()
    for i, slot in enumerate([1, 1, 1]):
        gid = f"g{i}"
        _seed_game(conn, game_id=gid, date=f"2026-05-{i+1:02d}")
        _seed_lineup(conn, game_id=gid, slot=slot, display="X", canonical="平山功太")
    assert lh.detect_first_appearance_in_slot(conn, player_canonical="平山功太") is None


# ─── orchestration ────────────────────────────────────────────────────────


def test_run_all_lineup_detectors_emits_insertable_rows():
    conn = _new_conn()
    _seed_game(conn, game_id="g1", date="2026-05-08")
    _seed_game(conn, game_id="g2", date="2026-05-10")
    _seed_lineup(conn, game_id="g1", slot=6, display="X", canonical="佐々木俊輔")
    _seed_lineup(conn, game_id="g2", slot=1, display="X", canonical="佐々木俊輔")
    conn.execute(
        "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates, notes) "
        "VALUES (?,?,?,?,?,?)",
        ("r1", "2026-05-13T00:00:00+00:00", "2026-05-08", "2026-05-10", 0, "test"),
    )
    candidates = lh.run_all_lineup_detectors(
        conn, run_id="r1", created_at="2026-05-13T00:00:00+00:00",
    )
    assert candidates
    # row shape compatible with insert_candidates
    insight_etl.insert_candidates(conn, candidates)
    n = conn.execute("SELECT COUNT(*) FROM article_candidates").fetchone()[0]
    assert n == len(candidates)
