"""Tests for 403 Stage A4: ETL window helpers for new scope vocabulary.

新 scope (last_N_pa / last_N_appearances / last_N_ip) 用の per-player
window helper を ``insight_etl`` に追加。 各 helper は (oldest_date,
latest_date) を返し、 sample 不足は None。

``compute_advanced_metric_snapshots`` の dispatch も新 scope を受けて
適切な window helper を呼ぶ。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.analysis import insight_etl


def _open_db(tmp_path: Path) -> sqlite3.Connection:
    return insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )


def _seed_batter_atbats(
    conn: sqlite3.Connection,
    *,
    player: str,
    team: str,
    game_date: str,
    atbats: list[str],
    seq: int = 0,
) -> None:
    gid = f"g-{game_date}-{seq}"
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
        (gid, game_date),
    )
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, "
        "atbats_json, team_name) "
        "VALUES (?, 'home', 1, '中', ?, ?, 0, ?, 0, 0, 0, 0, ?, ?)",
        (gid, player, player, len(atbats), json.dumps(atbats), team),
    )


def _seed_pitching(
    conn: sqlite3.Connection,
    *,
    pitcher: str,
    team: str,
    game_date: str,
    ip: float,
    seq: int = 0,
) -> None:
    gid = f"gp-{game_date}-{seq}"
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-20T00:00:00Z')",
        (gid, game_date),
    )
    conn.execute(
        "INSERT INTO pitching_logs (game_id, team_role, appearance_order, "
        "player_display, player_canonical, result_mark, pitches, BF, IP, "
        "H_allowed, HR_allowed, BB, HBP, K, R, ER, team_name) "
        "VALUES (?, 'home', 1, ?, ?, '', 100, 25, ?, 5, 0, 2, 0, 5, 1, 1, ?)",
        (gid, pitcher, pitcher, ip, team),
    )


# ─── _player_last_n_pa_window (打者 PA cumsum) ──────────────────────────────


def test_pa_window_30_pa_5_games_sufficient(tmp_path):
    """1 試合 6 PA × 5 試合 = 30 PA、 最古 5/15 / 最新 5/19 を返す。"""
    conn = _open_db(tmp_path)
    try:
        dates = ["2026-05-15", "2026-05-16", "2026-05-17", "2026-05-18", "2026-05-19"]
        for i, d in enumerate(dates):
            _seed_batter_atbats(
                conn, player="岡本", team="巨人", game_date=d,
                atbats=["中安", "三振", "四球", "中安", "三振", "右安"],
                seq=i,
            )
        conn.commit()
        result = insight_etl._player_last_n_pa_window(
            conn, "岡本", n_pa=30, snapshot_date="2026-05-20",
        )
        assert result is not None
        assert result == ("2026-05-15", "2026-05-19")
    finally:
        conn.close()


def test_pa_window_insufficient_returns_none(tmp_path):
    """20 PA しかない / n_pa=30 → None。"""
    conn = _open_db(tmp_path)
    try:
        # 4 PA × 5 試合 = 20 PA
        for i, d in enumerate(["2026-05-15", "2026-05-16", "2026-05-17",
                                "2026-05-18", "2026-05-19"]):
            _seed_batter_atbats(
                conn, player="浦田", team="巨人", game_date=d,
                atbats=["中安", "三振", "四球", "中安"],
                seq=i,
            )
        conn.commit()
        result = insight_etl._player_last_n_pa_window(
            conn, "浦田", n_pa=30, snapshot_date="2026-05-20",
        )
        assert result is None
    finally:
        conn.close()


def test_pa_window_excludes_future_games(tmp_path):
    """snapshot_date より後の試合は除外。"""
    conn = _open_db(tmp_path)
    try:
        for i, d in enumerate(["2026-05-13", "2026-05-15", "2026-05-17",
                                "2026-05-18", "2026-05-19", "2026-05-25"]):
            _seed_batter_atbats(
                conn, player="岡本", team="巨人", game_date=d,
                atbats=["中安"] * 6, seq=i,
            )
        conn.commit()
        # snapshot_date=2026-05-20、 5/25 試合は除外
        result = insight_etl._player_last_n_pa_window(
            conn, "岡本", n_pa=30, snapshot_date="2026-05-20",
        )
        assert result is not None
        # 6 PA × 5 試合 (5/19 から逆順 5/13 まで) = 30 PA を 5/13 で達成
        # 5/25 試合は snapshot_date より後で除外、 latest=5/19 / oldest=5/13
        assert result == ("2026-05-13", "2026-05-19")
    finally:
        conn.close()


# ─── _pitcher_last_n_appearance_window (投手 登板数) ───────────────────────


def test_appearance_window_5_apps_sufficient(tmp_path):
    """5 登板達成、 最古 / 最新を返す。"""
    conn = _open_db(tmp_path)
    try:
        for i, d in enumerate(["2026-05-10", "2026-05-12", "2026-05-14",
                                "2026-05-16", "2026-05-18"]):
            _seed_pitching(
                conn, pitcher="戸郷", team="巨人", game_date=d, ip=6.0, seq=i,
            )
        conn.commit()
        result = insight_etl._pitcher_last_n_appearance_window(
            conn, "戸郷", n_apps=5, snapshot_date="2026-05-20",
        )
        assert result is not None
        assert result == ("2026-05-10", "2026-05-18")
    finally:
        conn.close()


def test_appearance_window_insufficient_returns_none(tmp_path):
    """3 登板 / n_apps=5 → None。"""
    conn = _open_db(tmp_path)
    try:
        for i, d in enumerate(["2026-05-14", "2026-05-16", "2026-05-18"]):
            _seed_pitching(
                conn, pitcher="高梨", team="巨人", game_date=d, ip=1.0, seq=i,
            )
        conn.commit()
        result = insight_etl._pitcher_last_n_appearance_window(
            conn, "高梨", n_apps=5, snapshot_date="2026-05-20",
        )
        assert result is None
    finally:
        conn.close()


# ─── _pitcher_last_n_ip_window (投手 IP cumsum) ────────────────────────────


def test_ip_window_10_ip_sufficient(tmp_path):
    """先発 6.0 + 5.0 = 11 IP、 2 試合で 10 IP 達成。"""
    conn = _open_db(tmp_path)
    try:
        _seed_pitching(
            conn, pitcher="戸郷", team="巨人", game_date="2026-05-14", ip=5.0, seq=0,
        )
        _seed_pitching(
            conn, pitcher="戸郷", team="巨人", game_date="2026-05-18", ip=6.0, seq=1,
        )
        conn.commit()
        result = insight_etl._pitcher_last_n_ip_window(
            conn, "戸郷", n_ip=10.0, snapshot_date="2026-05-20",
        )
        assert result is not None
        # 5/18 (6 IP) → cumsum=6 < 10、 5/14 (5 IP) → cumsum=11 >= 10
        assert result == ("2026-05-14", "2026-05-18")
    finally:
        conn.close()


def test_ip_window_insufficient_returns_none(tmp_path):
    """3 IP しかない / n_ip=10 → None。"""
    conn = _open_db(tmp_path)
    try:
        _seed_pitching(
            conn, pitcher="マルティネス", team="巨人",
            game_date="2026-05-18", ip=1.0, seq=0,
        )
        _seed_pitching(
            conn, pitcher="マルティネス", team="巨人",
            game_date="2026-05-19", ip=2.0, seq=1,
        )
        conn.commit()
        result = insight_etl._pitcher_last_n_ip_window(
            conn, "マルティネス", n_ip=10.0, snapshot_date="2026-05-20",
        )
        assert result is None
    finally:
        conn.close()


# ─── compute_advanced_metric_snapshots dispatch (新 scope 経由) ─────────────


def test_compute_snapshots_last_30_pa_writes_batter_only(tmp_path):
    """scope=last_30_pa: 打者 metric が書かれる、 投手 metric は skip。"""
    conn = _open_db(tmp_path)
    try:
        # players seed (active 巨人)
        conn.execute(
            "INSERT INTO teams (team_code, team_name, league, home_park) "
            "VALUES ('g', '巨人', 'central', '東京ドーム')"
        )
        conn.execute(
            "INSERT INTO players (player_canonical, team_code, primary_position, "
            "role, jersey_number, active) "
            "VALUES ('岡本', 'g', '内野手', 'player', '25', 1)"
        )
        # 5 試合 × 6 PA = 30 PA
        for i, d in enumerate(["2026-05-15", "2026-05-16", "2026-05-17",
                                "2026-05-18", "2026-05-19"]):
            _seed_batter_atbats(
                conn, player="岡本", team="巨人", game_date=d,
                atbats=["中安", "中安", "中安", "三振", "四球", "右安"],
                seq=i,
            )
        conn.commit()

        n_written = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_30_pa", snapshot_date="2026-05-20",
            min_pa=20, min_ip=10.0,
        )
        assert n_written > 0
        rows = conn.execute(
            "SELECT metric_name FROM advanced_metric_snapshots "
            "WHERE scope='last_30_pa' AND player_canonical='岡本'"
        ).fetchall()
        metric_names = {r[0] for r in rows}
        # 打者 metric (OPS / AVG 等) が存在
        assert "OPS" in metric_names or "AVG" in metric_names
    finally:
        conn.close()


def test_compute_snapshots_last_5_ip_writes_pitcher_only(tmp_path):
    """scope=last_5_ip: 投手 metric が書かれる、 打者 metric は skip。"""
    conn = _open_db(tmp_path)
    try:
        conn.execute(
            "INSERT INTO teams (team_code, team_name, league, home_park) "
            "VALUES ('g', '巨人', 'central', '東京ドーム')"
        )
        conn.execute(
            "INSERT INTO players (player_canonical, team_code, primary_position, "
            "role, jersey_number, active) "
            "VALUES ('戸郷', 'g', '投手', 'pitcher', '11', 1)"
        )
        _seed_pitching(
            conn, pitcher="戸郷", team="巨人", game_date="2026-05-18", ip=6.0, seq=0,
        )
        conn.commit()

        n_written = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_5_ip", snapshot_date="2026-05-20",
            min_pa=20, min_ip=5.0,
        )
        # 6 IP >= 5 IP target、 投手 metric が書かれる
        assert n_written > 0
        rows = conn.execute(
            "SELECT metric_name FROM advanced_metric_snapshots "
            "WHERE scope='last_5_ip' AND player_canonical='戸郷'"
        ).fetchall()
        metric_names = {r[0] for r in rows}
        # 投手 metric (ERA / K_per_9 等) が存在
        assert "ERA" in metric_names or "K_per_9" in metric_names
    finally:
        conn.close()


def test_compute_snapshots_existing_last_5_games_unchanged(tmp_path):
    """既存 last_5_games scope は依然動作 (regression check)。"""
    conn = _open_db(tmp_path)
    try:
        conn.execute(
            "INSERT INTO teams (team_code, team_name, league, home_park) "
            "VALUES ('g', '巨人', 'central', '東京ドーム')"
        )
        conn.execute(
            "INSERT INTO players (player_canonical, team_code, primary_position, "
            "role, jersey_number, active) "
            "VALUES ('岡本', 'g', '内野手', 'player', '25', 1)"
        )
        for i, d in enumerate(["2026-05-15", "2026-05-16", "2026-05-17",
                                "2026-05-18", "2026-05-19"]):
            _seed_batter_atbats(
                conn, player="岡本", team="巨人", game_date=d,
                atbats=["中安", "中安", "中安", "三振", "四球"],
                seq=i,
            )
        conn.commit()

        n_written = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_5_games", snapshot_date="2026-05-20",
            min_pa=15, min_ip=10.0,
        )
        assert n_written > 0
    finally:
        conn.close()
