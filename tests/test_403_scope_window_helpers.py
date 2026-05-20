"""Tests for 403 Stage A: scope window helpers (game-count / PA / appearance / IP cumsum).

新 scope vocabulary (last_N_games / last_N_pa / last_N_appearances / last_N_ip)
を ``_scope_window`` に additive dispatch。 既存 scope (last_7d / last_30d /
season / monthly / weekly) は不変。

実 wiring (aggregate_* 呼出側で新 scope を使う cutover) は別 commit。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_etl, ranking_article_publisher as rap


def _open_db(tmp_path: Path) -> sqlite3.Connection:
    return insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )


def _seed_giants_games(conn: sqlite3.Connection, dates: list[str]) -> list[str]:
    """巨人試合を seed、 各 date 1 試合、 game_ids 返す。"""
    insight_etl.seed_teams(conn)
    game_ids = []
    for i, d in enumerate(dates):
        gid = f"g-{d}-{i}"
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
            "opp_score, result, source_url, source_kind, ingested_at) "
            "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', ?)",
            (gid, d, f"{d}T00:00:00Z"),
        )
        # 巨人 batting_logs row も入れる (game を「巨人試合」と認識させるため)
        conn.execute(
            "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
            "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
            "atbats_json, team_name) "
            "VALUES (?, 'home', 1, '中', 'seed', 'seed', 0, 4, 0, 0, 0, 0, '[]', '巨人')",
            (gid,),
        )
        game_ids.append(gid)
    conn.commit()
    return game_ids


def test_scope_window_existing_last_7d_unchanged():
    """既存 scope `last_7d` は conn なしでも従来通り動く。"""
    today = dt.date(2026, 5, 20)
    start, end = rap._scope_window("last_7d", today=today)
    assert start == dt.date(2026, 5, 14)
    assert end == today


def test_scope_window_existing_season_unchanged():
    today = dt.date(2026, 5, 20)
    start, end = rap._scope_window("season", today=today)
    assert start == dt.date(2026, 1, 1)
    assert end == today


def test_scope_window_last_3_games(tmp_path):
    """last_3_games で巨人直近3試合の最古 game_date を start とする。"""
    conn = _open_db(tmp_path)
    try:
        _seed_giants_games(conn, [
            "2026-05-13", "2026-05-15", "2026-05-17",
            "2026-05-18", "2026-05-19",
        ])
        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window("last_3_games", today=today, conn=conn)
        # 直近3試合 = 5/17, 5/18, 5/19 → start=5/17
        assert start == dt.date(2026, 5, 17)
        assert end == today
    finally:
        conn.close()


def test_scope_window_last_5_games_with_more_games(tmp_path):
    """last_5_games: 7 試合あれば直近5試合の最古 = 5/15。"""
    conn = _open_db(tmp_path)
    try:
        _seed_giants_games(conn, [
            "2026-05-11", "2026-05-12", "2026-05-15",
            "2026-05-16", "2026-05-17", "2026-05-18", "2026-05-19",
        ])
        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window("last_5_games", today=today, conn=conn)
        # 直近5試合 = 5/15, 5/16, 5/17, 5/18, 5/19 → start=5/15
        assert start == dt.date(2026, 5, 15)
    finally:
        conn.close()


def test_scope_window_last_games_no_games_returns_today(tmp_path):
    """巨人試合が DB に無い場合、 today 単日を返す。"""
    conn = _open_db(tmp_path)
    try:
        insight_etl.seed_teams(conn)
        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window("last_3_games", today=today, conn=conn)
        assert start == today
        assert end == today
    finally:
        conn.close()


def test_scope_window_last_30_pa(tmp_path):
    """last_30_pa: 指定選手の atbats_json から PA cumsum で 30 PA を満たす日付を start とする。"""
    conn = _open_db(tmp_path)
    try:
        insight_etl.seed_teams(conn)
        # 5 試合に分散 6 PA / 試合 = 30 PA、 直近 5 試合で達成
        dates = ["2026-05-13", "2026-05-15", "2026-05-17", "2026-05-18", "2026-05-19"]
        for i, d in enumerate(dates):
            gid = f"g-pa-{d}-{i}"
            conn.execute(
                "INSERT INTO games (game_id, game_date, opponent, home_away, "
                "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
                "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
                (gid, d),
            )
            # 6 PA / 試合
            atbats = ["中安", "三振", "四球", "中安", "中安", "二飛"]
            conn.execute(
                "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
                "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
                "atbats_json, team_name) "
                "VALUES (?, 'home', 1, '中', '岡本', '岡本', 0, 6, 0, 3, 0, 0, ?, '巨人')",
                (gid, json.dumps(atbats)),
            )
        conn.commit()

        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window(
            "last_30_pa", today=today, conn=conn, focus_player="岡本",
        )
        # 30 PA = 5 試合分、 最古は 5/13
        assert start == dt.date(2026, 5, 13)
        assert end == today
    finally:
        conn.close()


def test_scope_window_last_pa_insufficient_returns_earliest(tmp_path):
    """PA cumsum が n_pa に届かない場合、 取得できた最古 row まで返す。"""
    conn = _open_db(tmp_path)
    try:
        insight_etl.seed_teams(conn)
        # 1 試合 3 PA のみ
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
            "opp_score, result, source_url, source_kind, ingested_at) "
            "VALUES ('g-pa-low', '2026-05-19', 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
        )
        conn.execute(
            "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
            "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
            "atbats_json, team_name) "
            "VALUES ('g-pa-low', 'home', 1, '中', '岡本', '岡本', 0, 3, 0, 1, 0, 0, ?, '巨人')",
            (json.dumps(["中安", "三振", "四球"]),),
        )
        conn.commit()

        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window(
            "last_50_pa", today=today, conn=conn, focus_player="岡本",
        )
        # 3 PA しかない、 5/19 を返す (50 PA 未達)
        assert start == dt.date(2026, 5, 19)
    finally:
        conn.close()


def test_scope_window_last_5_appearances(tmp_path):
    """last_5_appearances: 投手の直近5登板を含む game_date 範囲。"""
    conn = _open_db(tmp_path)
    try:
        insight_etl.seed_teams(conn)
        # 7 登板を seed
        dates = ["2026-05-08", "2026-05-10", "2026-05-12",
                 "2026-05-14", "2026-05-16", "2026-05-18", "2026-05-19"]
        for i, d in enumerate(dates):
            gid = f"g-app-{d}-{i}"
            conn.execute(
                "INSERT INTO games (game_id, game_date, opponent, home_away, "
                "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
                "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
                (gid, d),
            )
            conn.execute(
                "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
                "player_display, player_canonical, result_mark, pitches, BF, IP, "
                "H_allowed, HR_allowed, BB, HBP, K, R, ER, team_name) "
                "VALUES (?, 'home', 1, '戸郷', '戸郷', '', 100, 25, 6.0, 5, 0, 2, 0, 5, 1, 1, '巨人')",
                (gid,),
            )
        conn.commit()

        today = dt.date(2026, 5, 20)
        start, end = rap._scope_window(
            "last_5_appearances", today=today, conn=conn, focus_player="戸郷",
        )
        # 直近5登板 = 5/12, 5/14, 5/16, 5/18, 5/19 → start=5/12
        assert start == dt.date(2026, 5, 12)
    finally:
        conn.close()


def test_scope_window_last_10_ip(tmp_path):
    """last_10_ip: IP cumsum で 10 IP に達する日付を start。"""
    conn = _open_db(tmp_path)
    try:
        insight_etl.seed_teams(conn)
        # 3 試合: 5.0 + 4.0 + 2.0 IP, 直近 2 試合で 6.0、 3 試合目で 11 → start = 最古
        dates_ips = [
            ("2026-05-15", 5.0),
            ("2026-05-17", 4.0),
            ("2026-05-19", 2.0),
        ]
        for i, (d, ip) in enumerate(dates_ips):
            gid = f"g-ip-{d}-{i}"
            conn.execute(
                "INSERT INTO games (game_id, game_date, opponent, home_away, "
                "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
                "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
                (gid, d),
            )
            conn.execute(
                "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
                "player_display, player_canonical, result_mark, pitches, BF, IP, "
                "H_allowed, HR_allowed, BB, HBP, K, R, ER, team_name) "
                "VALUES (?, 'home', 1, '戸郷', '戸郷', '', 100, 25, ?, 5, 0, 2, 0, 5, 1, 1, '巨人')",
                (gid, ip),
            )
        conn.commit()

        today = dt.date(2026, 5, 20)
        # 2 + 4 = 6 IP (5/19, 5/17)、 +5 = 11 IP で 5/15 達成 → start=5/15
        start, end = rap._scope_window(
            "last_10_ip", today=today, conn=conn, focus_player="戸郷",
        )
        assert start == dt.date(2026, 5, 15)
    finally:
        conn.close()


def test_scope_window_new_scope_requires_conn():
    """game-count / PA / appearance / IP scope は conn なしで ValueError。"""
    today = dt.date(2026, 5, 20)
    with pytest.raises(ValueError, match="requires conn"):
        rap._scope_window("last_3_games", today=today)
    with pytest.raises(ValueError, match="requires conn"):
        rap._scope_window("last_30_pa", today=today, focus_player="岡本")
    with pytest.raises(ValueError, match="requires conn"):
        rap._scope_window("last_5_appearances", today=today, focus_player="戸郷")


def test_scope_window_pa_scope_requires_focus_player(tmp_path):
    """PA / appearance / IP scope は focus_player なしで ValueError。"""
    conn = _open_db(tmp_path)
    try:
        today = dt.date(2026, 5, 20)
        with pytest.raises(ValueError, match="requires conn \\+ focus_player"):
            rap._scope_window("last_30_pa", today=today, conn=conn)
        with pytest.raises(ValueError, match="requires conn \\+ focus_player"):
            rap._scope_window("last_5_appearances", today=today, conn=conn)
        with pytest.raises(ValueError, match="requires conn \\+ focus_player"):
            rap._scope_window("last_10_ip", today=today, conn=conn)
    finally:
        conn.close()


def test_scope_window_unknown_scope_raises():
    """完全に未知の scope 名は ValueError。"""
    today = dt.date(2026, 5, 20)
    with pytest.raises(ValueError, match="unsupported scope"):
        rap._scope_window("nonsense_scope", today=today)
