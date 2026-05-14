"""Tests for src.analysis.insight_etl.compute_advanced_metric_snapshots
(343-INSIGHT-007).

batting_logs + atbats_json から OPS / wOBA 等の打者 metric snapshot 作成、
pitching_logs から ERA / FIP 等の投手 metric snapshot 作成、
scope 別 sample 閾値、league_rank 計算を verify。
"""

from __future__ import annotations

import json

from src.analysis import insight_etl


def _seed_game(conn, *, game_id, game_date):
    conn.execute(
        "INSERT OR REPLACE INTO games (game_id, game_date, opponent, home_away, ingested_at) "
        "VALUES (?, ?, '中日', 'home', '2026-05-11T00:00:00Z')",
        (game_id, game_date),
    )


def _seed_batting(conn, *, game_id, player_canonical, team_name, AB, H, atbats):
    """slot_order を player_canonical 由来 hash で散らして PRIMARY KEY 衝突を避ける。"""
    slot = abs(hash(player_canonical)) % 9 + 1
    conn.execute(
        "INSERT OR REPLACE INTO batting_logs "
        "(game_id, team_role, slot_order, player_display, player_canonical, "
        "is_sub, AB, H, atbats_json, team_name) "
        "VALUES (?, 'giants', ?, ?, ?, 0, ?, ?, ?, ?)",
        (game_id, slot, player_canonical, player_canonical, AB, H, json.dumps(atbats), team_name),
    )


def _seed_pitching(conn, *, game_id, player_canonical, team_name, IP, H_allowed, BB, K, ER, BF, HR_allowed=0):
    appearance = abs(hash(player_canonical)) % 9 + 1
    conn.execute(
        "INSERT OR REPLACE INTO pitching_logs "
        "(game_id, team_role, appearance_order, player_display, player_canonical, "
        "IP, H_allowed, HR_allowed, BB, HBP, K, R, ER, BF, team_name) "
        "VALUES (?, 'giants', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
        (game_id, appearance, player_canonical, player_canonical,
         IP, H_allowed, HR_allowed, BB, K, ER, ER, BF, team_name),
    )


def _seed_player(conn, *, player_canonical, team_code, role="player"):
    # players.team_code → teams.team_code FK 制約を満たすため先に teams を seed
    # (idempotent INSERT OR IGNORE なので複数回呼んでも安全)
    insight_etl.seed_teams(conn)
    conn.execute(
        "INSERT OR REPLACE INTO players (player_canonical, team_code, role, active) "
        "VALUES (?, ?, ?, 1)",
        (player_canonical, team_code, role),
    )


def test_compute_returns_zero_when_no_players(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        inserted = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        assert inserted == 0
    finally:
        conn.close()


def test_compute_skips_players_below_min_pa(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-10")
        _seed_player(conn, player_canonical="少打席選手", team_code="g")
        # PA = 3 (AB=3、atbats 3 つ全部 hit)、min_pa=30 なので skip される
        _seed_batting(
            conn, game_id="g1", player_canonical="少打席選手", team_name="巨人",
            AB=3, H=2, atbats=["中前安", "右越本①", "三 振"],
        )
        conn.commit()

        inserted = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        assert inserted == 0
    finally:
        conn.close()


def test_compute_emits_batter_snapshots_when_pa_meets_threshold(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-10")
        _seed_player(conn, player_canonical="主力打者", team_code="g")
        # PA を 30 以上にするため、HR / 安打 / 三振 / 四球 を mix した atbats を用意
        atbats = (["右越本①"] * 5 + ["中前安"] * 8 + ["二中安"] * 3
                  + ["三 振"] * 8 + ["四 球"] * 6)
        _seed_batting(
            conn, game_id="g1", player_canonical="主力打者", team_name="巨人",
            AB=24, H=16, atbats=atbats,
        )
        conn.commit()

        inserted = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        assert inserted >= 1

        rows = list(conn.execute(
            "SELECT metric_name, metric_value, sample_size, league_rank, league_total "
            "FROM advanced_metric_snapshots WHERE player_canonical = '主力打者'"
        ))
        metric_names = {r[0] for r in rows}
        # all_batter_metrics の主要 metric が出ていること (key 命名は大文字)
        assert "OPS" in metric_names
        # rank 1/1 (1 人だけなので)
        for r in rows:
            assert r[3] == 1
            assert r[4] == 1
    finally:
        conn.close()


def test_compute_emits_pitcher_snapshots_when_ip_meets_threshold(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-10")
        _seed_player(conn, player_canonical="先発投手", team_code="g", role="pitcher")
        _seed_pitching(
            conn, game_id="g1", player_canonical="先発投手", team_name="巨人",
            IP=12.0, H_allowed=8, BB=3, K=10, ER=2, BF=45,
        )
        conn.commit()

        inserted = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        assert inserted >= 1

        rows = list(conn.execute(
            "SELECT metric_name FROM advanced_metric_snapshots WHERE player_canonical = '先発投手'"
        ))
        metric_names = {r[0] for r in rows}
        assert "ERA" in metric_names
        assert "K_per_9" in metric_names
        assert "WHIP" in metric_names
    finally:
        conn.close()


def test_compute_returns_zero_for_last_5_games_scope(tmp_path):
    """last_5_games は per-player scope で本 function 未対応、return 0。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        inserted = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_5_games", snapshot_date="2026-05-14",
        )
        assert inserted == 0
    finally:
        conn.close()


def test_compute_idempotent_replace_on_second_call(tmp_path):
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-10")
        _seed_player(conn, player_canonical="主力打者", team_code="g")
        atbats = (["右越本①"] * 5 + ["中前安"] * 8 + ["二中安"] * 3
                  + ["三 振"] * 8 + ["四 球"] * 6)
        _seed_batting(
            conn, game_id="g1", player_canonical="主力打者", team_name="巨人",
            AB=24, H=16, atbats=atbats,
        )
        conn.commit()

        first = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        second = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30d", snapshot_date="2026-05-14",
        )
        # INSERT OR REPLACE なので 2 回目も同じ row count、duplicate ではない
        cnt = conn.execute(
            "SELECT COUNT(*) FROM advanced_metric_snapshots WHERE player_canonical = '主力打者'"
        ).fetchone()[0]
        assert cnt == first
        # second は replace なので rowcount は同じ insert 数を返す (sqlite OR REPLACE 仕様)
        assert second >= 1
    finally:
        conn.close()


def test_compute_window_scope_filters_old_games(tmp_path):
    """last_7d で snapshot_date より 8 日以上前の game は集計対象外。"""
    db = tmp_path / "insight.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        # snapshot_date = 2026-05-14、last_7d = 2026-05-08〜05-14
        _seed_game(conn, game_id="recent", game_date="2026-05-10")
        _seed_game(conn, game_id="old", game_date="2026-04-01")
        _seed_player(conn, player_canonical="主力打者", team_code="g")
        atbats_full = (["右越本①"] * 5 + ["中前安"] * 8 + ["二中安"] * 3
                       + ["三 振"] * 8 + ["四 球"] * 6)
        _seed_batting(
            conn, game_id="recent", player_canonical="主力打者", team_name="巨人",
            AB=24, H=16, atbats=atbats_full,
        )
        # old game は別 game_id なので別 row として inserted、PRIMARY KEY 衝突なし
        _seed_batting(
            conn, game_id="old", player_canonical="主力打者", team_name="巨人",
            AB=100, H=100, atbats=["右越本①"] * 100,
        )
        conn.commit()

        # last_7d で集計 → recent の 24 PA 分しか含まれないはず (old は除外)
        insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_7d", snapshot_date="2026-05-14",
        )
        rows = list(conn.execute(
            "SELECT metric_name, sample_size FROM advanced_metric_snapshots "
            "WHERE player_canonical = '主力打者' AND scope = 'last_7d'"
        ))
        # sample_size は PA、recent のみで 30 PA、old を含めると 130
        assert rows
        for r in rows:
            assert r[1] <= 35  # recent 分のみ (PA=30 程度)
    finally:
        conn.close()
