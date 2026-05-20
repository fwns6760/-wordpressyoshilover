"""Tests for 403 Stage B: 打順別 publisher (band 化: 上位 / クリーンナップ / 下位).

新規 publisher (aggregate / render / publish) を追加、 batting_logs.slot_order
を split key に band 化集計。 既存 split publisher (home_away / opponent) と
独立。
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


def _seed_game(conn, *, game_id, game_date):
    insight_etl.seed_teams(conn)
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
        (game_id, game_date),
    )


def _seed_batter(conn, *, game_id, player, team, slot_order, h_count, is_sub=0,
                 rbi=0):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
        "atbats_json, team_name) "
        "VALUES (?, 'home', ?, '中', ?, ?, ?, 4, 0, ?, ?, 0, '[]', ?)",
        (game_id, slot_order, player, player, is_sub, h_count, rbi, team),
    )


def test_slot_band_dict_defines_3_bands():
    """3 band の定義確認 (top / cleanup / bottom)."""
    assert set(rap._SLOT_BANDS.keys()) == {"top", "cleanup", "bottom"}
    assert rap._SLOT_BANDS["top"] == ((1, 2), "上位打線")
    assert rap._SLOT_BANDS["cleanup"] == ((3, 4, 5), "クリーンナップ")
    assert rap._SLOT_BANDS["bottom"] == ((6, 7, 8, 9), "下位打線")


def test_aggregate_by_slot_band_top_filters_correctly(tmp_path):
    """slot_band='top': slot_order ∈ {1, 2} の集計のみ。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        # 1番: 巨人A 3 H
        _seed_batter(conn, game_id="g1", player="巨人A", team="巨人",
                     slot_order=1, h_count=3)
        # 2番: 巨人B 2 H
        _seed_batter(conn, game_id="g1", player="巨人B", team="巨人",
                     slot_order=2, h_count=2)
        # 4番: 巨人C 5 H (cleanup、 top には含まれない)
        _seed_batter(conn, game_id="g1", player="巨人C", team="巨人",
                     slot_order=4, h_count=5)
        # 阪神 1番: 阪神D 4 H
        _seed_batter(conn, game_id="g1", player="阪神D", team="阪神",
                     slot_order=1, h_count=4)
        conn.commit()

        rows = rap.aggregate_player_counting_stat_by_slot_band(
            conn, stat_col="H", scope="last_5_games", slot_band="top",
            today=dt.date(2026, 5, 19), top_n=10, league="central",
        )
        names = {r["player"] for r in rows}
        assert "巨人A" in names
        assert "巨人B" in names
        assert "阪神D" in names  # セ・リーグ filter で含まれる
        assert "巨人C" not in names  # cleanup band、 除外
    finally:
        conn.close()


def test_aggregate_by_slot_band_cleanup_filters(tmp_path):
    """slot_band='cleanup': slot_order ∈ {3, 4, 5} の集計のみ。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        _seed_batter(conn, game_id="g1", player="巨人3番", team="巨人",
                     slot_order=3, h_count=2)
        _seed_batter(conn, game_id="g1", player="巨人4番", team="巨人",
                     slot_order=4, h_count=3)
        _seed_batter(conn, game_id="g1", player="巨人5番", team="巨人",
                     slot_order=5, h_count=1)
        _seed_batter(conn, game_id="g1", player="巨人2番", team="巨人",
                     slot_order=2, h_count=5)  # cleanup には含まれない
        conn.commit()

        rows = rap.aggregate_player_counting_stat_by_slot_band(
            conn, stat_col="H", scope="last_5_games", slot_band="cleanup",
            today=dt.date(2026, 5, 19), top_n=10, league="central",
        )
        names = {r["player"] for r in rows}
        assert "巨人3番" in names
        assert "巨人4番" in names
        assert "巨人5番" in names
        assert "巨人2番" not in names  # top band、 除外
    finally:
        conn.close()


def test_aggregate_by_slot_band_excludes_sub(tmp_path):
    """is_sub=1 は除外 (先発打順のみ集計)."""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        _seed_batter(conn, game_id="g1", player="先発A", team="巨人",
                     slot_order=4, h_count=3, is_sub=0)
        _seed_batter(conn, game_id="g1", player="代打B", team="巨人",
                     slot_order=4, h_count=2, is_sub=1)  # 代打、 除外
        conn.commit()

        rows = rap.aggregate_player_counting_stat_by_slot_band(
            conn, stat_col="H", scope="last_5_games", slot_band="cleanup",
            today=dt.date(2026, 5, 19), top_n=10, league="central",
        )
        names = {r["player"] for r in rows}
        assert "先発A" in names
        assert "代打B" not in names
    finally:
        conn.close()


def test_aggregate_by_slot_band_invalid_band_raises():
    """unknown slot_band は ValueError。"""
    with pytest.raises(ValueError, match="unsupported slot_band"):
        rap.aggregate_player_counting_stat_by_slot_band(
            conn=None,  # type: ignore
            stat_col="H", scope="last_5_games", slot_band="nonsense",
        )


def test_aggregate_by_slot_band_hr_returns_empty(tmp_path):
    """HR は batting_logs に列なし、 slot 別 HR は未対応で空 list 返却。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        _seed_batter(conn, game_id="g1", player="岡本", team="巨人",
                     slot_order=4, h_count=3)
        conn.commit()

        rows = rap.aggregate_player_counting_stat_by_slot_band(
            conn, stat_col="HR", scope="last_5_games", slot_band="cleanup",
            today=dt.date(2026, 5, 19), league="central",
        )
        assert rows == []
    finally:
        conn.close()


def test_aggregate_by_slot_band_rejects_sql_injection():
    """unsafe stat_col は ValueError。"""
    with pytest.raises(ValueError, match="unsafe stat_col"):
        rap.aggregate_player_counting_stat_by_slot_band(
            conn=None,  # type: ignore
            stat_col="H; DROP TABLE games --",
            scope="last_5_games", slot_band="top",
        )


def test_render_by_slot_band_title_format(tmp_path):
    """render が `(直近5試合)` label + band label を含む title を生成する。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        _seed_batter(conn, game_id="g1", player="巨人クリーン王", team="巨人",
                     slot_order=4, h_count=5, rbi=3)
        _seed_batter(conn, game_id="g1", player="阪神比較", team="阪神",
                     slot_order=4, h_count=2)
        conn.commit()

        article = rap.render_player_counting_by_slot_band_article(
            conn, stat_col="H", metric_label_jp="安打数",
            scope="last_5_games", slot_band="cleanup", top_n=10,
        )
        assert article is not None
        assert "巨人クリーン王" in article["title"]
        assert "クリーンナップ" in article["title"]
        assert "(直近5試合)" in article["title"] or "（直近5試合）" in article["title"]
        # body にも band label が含まれる
        assert "クリーンナップ" in article["body_md"]
    finally:
        conn.close()


def test_render_by_slot_band_returns_none_if_no_giants(tmp_path):
    """巨人 row が無ければ None。"""
    conn = _open_db(tmp_path)
    try:
        _seed_game(conn, game_id="g1", game_date="2026-05-19")
        _seed_batter(conn, game_id="g1", player="阪神のみ", team="阪神",
                     slot_order=4, h_count=3)
        conn.commit()

        article = rap.render_player_counting_by_slot_band_article(
            conn, stat_col="H", metric_label_jp="安打数",
            scope="last_5_games", slot_band="cleanup", top_n=10,
        )
        assert article is None
    finally:
        conn.close()
