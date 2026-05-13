"""Tests for src.analysis.insight_etl — INSIGHT-001 prototype.

Covers:
  * schema.sql is valid SQLite (parses and creates expected tables)
  * roster alias resolution (surname → canonical for unique surnames)
  * IP parser (5.1 → 5.333, 5.2 → 5.667, malformed → None)
  * etl_fixture end-to-end on the 5/10 NPB box fixture
  * idempotent re-ETL (running twice yields same row counts, not duplicates)
  * チーム計 aggregate row is excluded from pitcher logs
  * single-game detectors emit expected candidate rows
  * CSV export shape matches CSV_COLUMNS
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_etl

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "npb_score_2026_0510_d-g-08_box.html"


# ─── schema ────────────────────────────────────────────────────────────────


def test_schema_sql_creates_expected_tables(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {
            "games", "inning_scores", "batting_logs", "pitching_logs",
            "lineups", "fielding_logs", "standings_snapshots",
            "insight_runs", "article_candidates",
        }
        assert expected.issubset(names)
    finally:
        conn.close()


# ─── parse_ip ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5", 5.0),
        ("5.0", 5.0),
        ("5.1", 5.333),
        ("5.2", 5.667),
        ("0", 0.0),
        ("0.1", 0.333),
        ("", None),
        (None, None),
        ("5.3", None),  # 3/3 はあり得ない (繰り上がるので invalid)
        ("abc", None),
    ],
)
def test_parse_ip(raw, expected):
    assert insight_etl.parse_ip(raw) == expected


# ─── roster aliases ────────────────────────────────────────────────────────


def test_load_roster_aliases_includes_known_canonicals():
    aliases = insight_etl._load_roster_aliases()
    assert aliases.get("阿部慎之助") == "阿部慎之助"
    assert aliases.get("阿部監督") == "阿部慎之助"


def test_resolve_canonical_handles_unique_surname():
    aliases = insight_etl._load_roster_aliases()
    canon = insight_etl.resolve_canonical("浦田", aliases)
    # 浦田 is a unique 2-char surname for an active player → maps to 浦田俊輔
    assert canon == "浦田俊輔"


def test_resolve_canonical_returns_none_for_unknown():
    aliases = insight_etl._load_roster_aliases()
    assert insight_etl.resolve_canonical("カリステ", aliases) is None
    assert insight_etl.resolve_canonical("", aliases) is None
    assert insight_etl.resolve_canonical("無名選手", aliases) is None


# ─── derive_result ─────────────────────────────────────────────────────────


def test_derive_result_branches():
    assert insight_etl.derive_result(5, 3) == "win"
    assert insight_etl.derive_result(2, 7) == "loss"
    assert insight_etl.derive_result(4, 4) == "draw"
    assert insight_etl.derive_result(None, 0) == "unknown"


# ─── end-to-end ETL ────────────────────────────────────────────────────────


def _run_etl(tmp_path: Path):
    db = tmp_path / "insight.db"
    csv_path = tmp_path / "article_candidates.csv"
    summary = insight_etl.etl_fixture(
        FIXTURE,
        game_id="2026-05-10:d-g-08",
        game_date="2026-05-10",
        db_path=db,
        schema_path=insight_etl.DEFAULT_SCHEMA,
        csv_path=csv_path,
    )
    return summary, db, csv_path


def test_etl_fixture_inserts_game_and_logs(tmp_path):
    summary, db, csv_path = _run_etl(tmp_path)
    assert summary["batters_giants"] == 9
    assert summary["batters_opponent"] == 9
    # チーム計 集計行は除外されるので、6 投手のみ
    assert summary["pitchers_giants"] == 6
    assert summary["candidates_inserted"] >= 1
    assert csv_path.exists()


def test_etl_aggregate_pitcher_row_is_excluded(tmp_path):
    _, db, _ = _run_etl(tmp_path)
    conn = sqlite3.connect(str(db))
    rows = list(
        conn.execute(
            "SELECT player_display FROM pitching_logs WHERE team_role = 'giants'"
        )
    )
    conn.close()
    names = {r[0] for r in rows}
    assert "チーム計" not in names
    assert "計" not in names


def test_etl_idempotent_re_run(tmp_path):
    """Re-running ETL on the same fixture must not duplicate rows in
    games / batting_logs / pitching_logs (PK upsert)."""
    summary_1, db, csv_path = _run_etl(tmp_path)
    summary_2 = insight_etl.etl_fixture(
        FIXTURE,
        game_id="2026-05-10:d-g-08",
        game_date="2026-05-10",
        db_path=db,
        schema_path=insight_etl.DEFAULT_SCHEMA,
        csv_path=csv_path,
    )
    conn = sqlite3.connect(str(db))
    n_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    n_bat = conn.execute(
        "SELECT COUNT(*) FROM batting_logs WHERE team_role = 'giants'"
    ).fetchone()[0]
    n_pit = conn.execute(
        "SELECT COUNT(*) FROM pitching_logs WHERE team_role = 'giants'"
    ).fetchone()[0]
    conn.close()
    assert n_games == 1
    assert n_bat == summary_1["batters_giants"]
    assert n_pit == summary_1["pitchers_giants"]
    # Two runs → article_candidates has rows from both runs (different run_id)
    assert summary_2["candidates_inserted"] >= 1


# ─── single-game detectors ─────────────────────────────────────────────────


def test_etl_detects_homerun_and_multihit_for_darbeck(tmp_path):
    _, db, _ = _run_etl(tmp_path)
    conn = sqlite3.connect(str(db))
    rows = list(
        conn.execute(
            """
            SELECT signal_type, player_display, player_canonical, current_value
            FROM article_candidates
            ORDER BY candidate_id
            """
        )
    )
    conn.close()
    signal_types = {r[0] for r in rows}
    # ダルベックは HR 1本 + 3安打 → batter_homerun + batter_multi_hit
    assert "batter_homerun" in signal_types
    assert "batter_multi_hit" in signal_types
    # ダルベックのHR行が存在する
    assert any(
        r[0] == "batter_homerun" and "ダルベック" in (r[1] or "")
        for r in rows
    )


def test_csv_exports_with_expected_columns(tmp_path):
    _, _, csv_path = _run_etl(tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert list(reader.fieldnames) == list(insight_etl.CSV_COLUMNS)
        rows = list(reader)
    assert len(rows) >= 1
    # JOIN で run_ts が埋まる
    assert rows[0]["run_ts"]
    # status は NEW で開始
    assert rows[0]["status"] == "NEW"


# ─── CLI smoke ─────────────────────────────────────────────────────────────


def test_cli_dry_run(capsys, tmp_path):
    rc = insight_etl.main(
        [
            "--fixture", str(FIXTURE),
            "--game-id", "2026-05-10:d-g-08",
            "--game-date", "2026-05-10",
            "--dry-run",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "dry_run" in captured.out
    assert "giants_batters" in captured.out or "n_giants_batters" in captured.out
