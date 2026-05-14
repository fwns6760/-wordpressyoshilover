"""Tests for src.analysis.insight_etl.seed_players_from_logs (343-INSIGHT-007).

batting_logs / pitching_logs から (player_canonical, team_name) を induce、
team_name → team_code 変換 + role 推定 (player / pitcher) を verify。
"""

from __future__ import annotations

from src.analysis import insight_etl


def _insert_batting(conn, *, game_id, player_canonical, team_name):
    # INSERT OR IGNORE で games を再 insert しない (REPLACE は CASCADE DELETE で
    # 関連 logs を巻き添えにするため、test helper では IGNORE が安全)
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
        "VALUES (?, '2026-05-10', '中日', 'home', '2026-05-11T00:00:00Z')",
        (game_id,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO batting_logs "
        "(game_id, team_role, slot_order, player_display, player_canonical, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, ?)",
        (game_id, player_canonical, player_canonical, team_name),
    )


def _insert_pitching(conn, *, game_id, player_canonical, team_name):
    # INSERT OR IGNORE で games を再 insert しない (REPLACE は CASCADE DELETE で
    # 関連 logs を巻き添えにするため、test helper では IGNORE が安全)
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
        "VALUES (?, '2026-05-10', '中日', 'home', '2026-05-11T00:00:00Z')",
        (game_id,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO pitching_logs "
        "(game_id, team_role, appearance_order, player_display, player_canonical, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, ?)",
        (game_id, player_canonical, player_canonical, team_name),
    )


def test_seed_players_inserts_batter_with_role_player(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        _insert_batting(conn, game_id="2026-05-10:d-g-08", player_canonical="岡本和真", team_name="巨人")
        conn.commit()

        inserted = insight_etl.seed_players_from_logs(conn)
        assert inserted == 1

        row = conn.execute(
            "SELECT player_canonical, team_code, role, active FROM players "
            "WHERE player_canonical = '岡本和真'"
        ).fetchone()
        assert row is not None
        assert row[0] == "岡本和真"
        assert row[1] == "g"
        assert row[2] == "player"
        assert row[3] == 1
    finally:
        conn.close()


def test_seed_players_inserts_pitcher_with_role_pitcher(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        _insert_pitching(conn, game_id="2026-05-10:d-g-08", player_canonical="戸郷翔征", team_name="巨人")
        conn.commit()

        inserted = insight_etl.seed_players_from_logs(conn)
        assert inserted == 1

        row = conn.execute(
            "SELECT player_canonical, team_code, role FROM players WHERE player_canonical = '戸郷翔征'"
        ).fetchone()
        assert row is not None
        assert row[1] == "g"
        assert row[2] == "pitcher"
    finally:
        conn.close()


def test_seed_players_two_way_player_resolves_to_player_role(tmp_path):
    """打者 + 投手 両方に出現 (大谷型) は role='player' で induce される。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        _insert_batting(conn, game_id="2026-05-10:d-g-08", player_canonical="二刀流選手", team_name="日本ハム")
        _insert_pitching(conn, game_id="2026-05-10:d-g-08", player_canonical="二刀流選手", team_name="日本ハム")
        conn.commit()

        insight_etl.seed_players_from_logs(conn)
        row = conn.execute(
            "SELECT role, team_code FROM players WHERE player_canonical = '二刀流選手'"
        ).fetchone()
        assert row is not None
        assert row[0] == "player"  # 打者優先
        assert row[1] == "f"
    finally:
        conn.close()


def test_seed_players_idempotent(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        insight_etl.seed_teams(conn)
        _insert_batting(conn, game_id="2026-05-10:d-g-08", player_canonical="坂本勇人", team_name="巨人")
        conn.commit()

        first = insight_etl.seed_players_from_logs(conn)
        second = insight_etl.seed_players_from_logs(conn)
        assert first == 1
        assert second == 0
    finally:
        conn.close()


def test_seed_players_skips_unknown_team(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _insert_batting(conn, game_id="2026-05-10:d-g-08", player_canonical="謎選手", team_name="架空チーム")
        conn.commit()

        inserted = insight_etl.seed_players_from_logs(conn)
        assert inserted == 0

        row = conn.execute(
            "SELECT * FROM players WHERE player_canonical = '謎選手'"
        ).fetchone()
        assert row is None
    finally:
        conn.close()


def test_seed_players_skips_null_canonical(tmp_path):
    """player_canonical=NULL の row は induce 対象外。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('g1', '2026-05-10', '中日', 'home', '2026-05-11T00:00:00Z')",
        )
        conn.execute(
            "INSERT OR REPLACE INTO batting_logs "
            "(game_id, team_role, slot_order, player_display, player_canonical, team_name) "
            "VALUES ('g1', 'giants', 1, '?', NULL, '巨人')"
        )
        conn.commit()

        inserted = insight_etl.seed_players_from_logs(conn)
        assert inserted == 0
    finally:
        conn.close()


def test_seed_players_skips_null_team_name(tmp_path):
    """team_name=NULL の row は induce 対象外。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
            "VALUES ('g1', '2026-05-10', '中日', 'home', '2026-05-11T00:00:00Z')",
        )
        conn.execute(
            "INSERT OR REPLACE INTO batting_logs "
            "(game_id, team_role, slot_order, player_display, player_canonical, team_name) "
            "VALUES ('g1', 'giants', 1, '岡本和真', '岡本和真', NULL)"
        )
        conn.commit()

        inserted = insight_etl.seed_players_from_logs(conn)
        assert inserted == 0
    finally:
        conn.close()
