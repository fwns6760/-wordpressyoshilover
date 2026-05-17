"""Tests for issue #44 B: 1 試合系 detector skip.

Bug: ``insight_anomaly_detector.run_all_anomaly_detectors`` が
``detect_game_hero_batter`` / ``detect_game_pitcher_performance`` を呼んでおり、
浦田 3 安打 1 打点 / マルティネス 1 イニング 0 自責 等の 1 試合 postgame
data 記事を連発していた (user 削除 3 件 / 残 2 件、 2026-05-17 lock)。

Fix: 上記 2 detector の呼び出しを skip (関数本体 + renderer 残置、 再有効化
余地確保)。 結果 dict には key を維持し、 値 = 空 list。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.analysis import insight_anomaly_detector as det
from src.analysis import insight_etl


REPO = Path(__file__).resolve().parents[1]


def _open_seed_db(tmp_path: Path) -> sqlite3.Connection:
    conn = insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )
    insight_etl.seed_teams(conn)
    return conn


def _seed_giants_game_with_multi_hit_batter(
    conn: sqlite3.Connection, snapshot_date: str
) -> str:
    """巨人 直近試合 + 3 安打 1 打点の打者 (H>=3 で hero candidate trigger 条件) を seed。"""
    game_id = f"{snapshot_date}:test-g-vs-db-01"
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (game_id, snapshot_date, "DeNA", "home", 5, 2, "win", "test://",
         "test", "2026-05-17T00:00:00Z"),
    )
    # H=3, RBI=1 = hero condition (H>=3) 該当
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, player_display, "
        "player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, 0, 4, 1, 3, 1, 0, '[]', '巨人')",
        (game_id, "テスト打者", "テスト打者"),
    )
    conn.commit()
    return game_id


def _seed_giants_game_with_relief_pitcher(
    conn: sqlite3.Connection, snapshot_date: str
) -> str:
    """巨人 直近試合 + 救援好投 (IP=1.0 ER=0 S) の投手 (game_pitcher_perf trigger 条件) を seed。"""
    game_id = f"{snapshot_date}:test-g-vs-db-02"
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, "
        "giants_score, opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (game_id, snapshot_date, "DeNA", "home", 5, 2, "win", "test://",
         "test", "2026-05-17T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, IP, BF, H_allowed, "
        "HR_allowed, BB, HBP, K, R, ER, team_name) "
        "VALUES (?, 'giants', 1, ?, ?, 'S', 1.0, 3, 0, 0, 0, 0, 1, 0, 0, '巨人')",
        (game_id, "テスト救援", "テスト救援"),
    )
    conn.commit()
    return game_id


def test_run_all_anomaly_detectors_returns_empty_game_hero_batter(tmp_path):
    """trigger 条件を満たす打者 seed しても game_hero_batter は 0 件。"""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_giants_game_with_multi_hit_batter(conn, "2026-05-16")
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-05-16")
        assert det.SIGNAL_GAME_HERO_BATTER in out, (
            f"key 維持確認失敗; keys={sorted(out.keys())}"
        )
        assert out[det.SIGNAL_GAME_HERO_BATTER] == [], (
            f"game_hero_batter detector が skip されていない: "
            f"{out[det.SIGNAL_GAME_HERO_BATTER]}"
        )
    finally:
        conn.close()


def test_run_all_anomaly_detectors_returns_empty_game_pitcher_perf(tmp_path):
    """trigger 条件を満たす救援投手 seed しても game_pitcher_perf は 0 件。"""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_giants_game_with_relief_pitcher(conn, "2026-05-16")
        out = det.run_all_anomaly_detectors(conn, snapshot_date="2026-05-16")
        assert det.SIGNAL_GAME_PITCHER_PERF in out, (
            f"key 維持確認失敗; keys={sorted(out.keys())}"
        )
        assert out[det.SIGNAL_GAME_PITCHER_PERF] == [], (
            f"game_pitcher_perf detector が skip されていない: "
            f"{out[det.SIGNAL_GAME_PITCHER_PERF]}"
        )
    finally:
        conn.close()
