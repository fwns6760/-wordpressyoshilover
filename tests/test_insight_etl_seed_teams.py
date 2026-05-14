"""Tests for src.analysis.insight_etl.seed_teams (343-INSIGHT-007).

12 球団 fixed roster の idempotent insert と、insert 後の row 内容を verify。
"""

from __future__ import annotations

from src.analysis import insight_etl


def test_seed_teams_first_call_inserts_12_rows(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        inserted = insight_etl.seed_teams(conn)
        assert inserted == 12

        rows = list(conn.execute("SELECT team_code FROM teams ORDER BY team_code"))
        codes = {r[0] for r in rows}
        assert codes == {"b", "c", "d", "db", "e", "f", "g", "h", "l", "m", "s", "t"}
    finally:
        conn.close()


def test_seed_teams_idempotent_second_call_inserts_zero(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        first = insight_etl.seed_teams(conn)
        second = insight_etl.seed_teams(conn)
        assert first == 12
        assert second == 0

        # 行数も合計 12 のまま
        cnt = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        assert cnt == 12
    finally:
        conn.close()


def test_seed_teams_central_pacific_split_six_each(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        rows = list(conn.execute("SELECT league, COUNT(*) FROM teams GROUP BY league"))
        league_counts = dict(rows)
        assert league_counts == {"central": 6, "pacific": 6}
    finally:
        conn.close()


def test_seed_teams_giants_row_has_expected_fields(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        row = conn.execute(
            "SELECT team_code, team_name, league, home_park FROM teams WHERE team_code = 'g'"
        ).fetchone()
        assert row is not None
        assert row[0] == "g"
        assert row[1] == "巨人"
        assert row[2] == "central"
        assert row[3] == "東京ドーム"
    finally:
        conn.close()
