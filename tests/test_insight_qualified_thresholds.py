"""Tests for issue #44 #1: 規定打席 / 規定投球回 動的閾値.

Bug: ``insight_nightly.py:287-300`` の ``scope_thresholds`` で season scope の
``min_pa=50`` / ``min_ip=15.0`` が **固定** で、 規定打席 (試合数 × 3.1) /
規定投球回 (試合数 × 1.0) に追従しない。 結果として 5/17 時点で IP=30 の
則本昂大 や IP=34 の竹丸和幸 が season ERA snapshot に入り、 「セ・リーグ
N/M 位」 と公式 ranking 風に表示される (実際は規定投球回未到達)。

Fix: season scope の min_pa / min_ip を ``games`` table の最進行球団試合数を
基準に動的化する helper を新規。 短期 scope (last_7d / last_30d / last_5_games
/ last_10_games / weekly / monthly) は不変。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.analysis import insight_etl


REPO = Path(__file__).resolve().parents[1]


def _open_seed_db(tmp_path: Path) -> sqlite3.Connection:
    return insight_etl.open_db(
        db_path=tmp_path / "insight.db",
        schema_path=insight_etl.DEFAULT_SCHEMA,
    )


def _seed_games(conn: sqlite3.Connection, *, team: str, n: int, base_date: str = "2026-04-01") -> None:
    """team が出場する n 試合分の games + batting_logs を seed."""
    import datetime as dt
    base = dt.date.fromisoformat(base_date)
    for i in range(n):
        gd = (base + dt.timedelta(days=i)).isoformat()
        game_id = f"{gd}:test-{team}-{i:02d}"
        conn.execute(
            "INSERT INTO games (game_id, game_date, opponent, home_away, "
            "giants_score, opp_score, result, source_url, source_kind, "
            "ingested_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (game_id, gd, "相手", "home", 3, 2, "win", "test://", "test",
             "2026-05-17T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO batting_logs (game_id, team_role, slot_order, player_display, "
            "is_sub, team_name) VALUES (?,?,?,?,?,?)",
            (game_id, "giants", 1, f"{team}_player", 0, team),
        )
    conn.commit()


# ─── helper: team_games_for_qualified_thresholds ─────────────────────────────


def test_team_games_helper_returns_max_central_team_games(tmp_path):
    """セ各球団試合数の max を返す (= リーグ最進行球団基準)."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_games(conn, team="巨人", n=40)
        _seed_games(conn, team="阪神", n=42, base_date="2026-04-01")
        _seed_games(conn, team="ヤクルト", n=41, base_date="2026-04-01")
        _seed_games(conn, team="DeNA", n=39, base_date="2026-04-01")
        # パ・リーグ球団は無視されることを確認
        _seed_games(conn, team="ソフトバンク", n=80, base_date="2026-04-01")

        n = insight_etl.team_games_for_qualified_thresholds(conn)
        assert n == 42, f"expected max(セ) = 42, got {n}"
    finally:
        conn.close()


def test_team_games_helper_safe_fallback_for_empty_db(tmp_path):
    """空 DB では旧固定値 (50 PA / 15 IP) を再現する fallback 値を返す."""
    conn = _open_seed_db(tmp_path)
    try:
        # 0 試合 → fallback = 約 16 試合 (= 50 / 3.1 ≒ 16.1) で旧値再現
        n = insight_etl.team_games_for_qualified_thresholds(conn)
        # qualified_pa = n * 3.1 ≈ 50 になる n を返す
        # qualified_ip = n * 1.0 ≈ 15 だと n=15、 一致しないので
        # 安全側 (publish を出しすぎない方) で大きい方を返す
        # 旧固定値 (min_pa=50, min_ip=15) を再現するには n=16〜17 程度
        # 0 件で snapshot 死なないことが最低条件 → n >= 1 必須
        assert n >= 1, f"empty DB fallback must be >= 1, got {n}"
        # mid-season を想定して旧固定値 (50 PA / 15 IP) 程度に保つ
        assert n * 3.1 >= 40 or n >= 16, (
            f"fallback should reproduce conservative thresholds; got n={n} "
            f"=> qualified_pa={n*3.1:.1f}, qualified_ip={n*1.0:.1f}"
        )
    finally:
        conn.close()


def test_team_games_helper_excludes_pacific_league_teams(tmp_path):
    """パ・リーグ球団は max 計算から除外される."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_games(conn, team="巨人", n=10)
        _seed_games(conn, team="日本ハム", n=80, base_date="2026-04-01")  # パ
        _seed_games(conn, team="西武", n=70, base_date="2026-04-01")  # パ
        n = insight_etl.team_games_for_qualified_thresholds(conn)
        assert n == 10, f"パ・リーグを含めるべきではない; got {n}"
    finally:
        conn.close()


# ─── snapshot integration ────────────────────────────────────────────────────


def _seed_player_with_ip(
    conn: sqlite3.Connection, *, canonical: str, total_ip: float,
    base_date: str = "2026-04-01",
) -> None:
    """player を seed + total_ip 分の pitching_logs を ETL 経由でなく直接挿入."""
    import datetime as dt
    base = dt.date.fromisoformat(base_date)
    # teams table seed (players FK 先)
    insight_etl.seed_teams(conn)
    # players table seed
    conn.execute(
        "INSERT OR REPLACE INTO players (player_canonical, team_code, active) "
        "VALUES (?, 'g', 1)",
        (canonical,),
    )
    # 7 IP × n_appearances ≒ total_ip
    n_apps = max(1, int(total_ip // 7))
    per_ip = total_ip / n_apps
    for i in range(n_apps):
        gd = (base + dt.timedelta(days=i * 5)).isoformat()
        game_id = f"{gd}:seed-{canonical}-{i:02d}"
        conn.execute(
            "INSERT OR IGNORE INTO games (game_id, game_date, opponent, home_away, "
            "giants_score, opp_score, result, source_url, source_kind, "
            "ingested_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (game_id, gd, "相手", "home", 3, 2, "win", "test://", "test",
             "2026-05-17T00:00:00Z"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO pitching_logs (game_id, team_role, appearance_order, "
            "player_display, player_canonical, IP, BF, H_allowed, HR_allowed, "
            "BB, HBP, K, R, ER, team_name) "
            "VALUES (?, 'giants', 1, ?, ?, ?, 28, 5, 0, 1, 0, 6, 1, 1, '巨人')",
            (game_id, canonical, canonical, per_ip),
        )
    conn.commit()


def test_norimoto_ip30_excluded_from_season_snapshot_when_qualified_threshold_applied(tmp_path):
    """則本 IP=30 が巨人 40 試合時点で season snapshot に入らない."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_games(conn, team="巨人", n=40)
        _seed_player_with_ip(conn, canonical="則本昂大", total_ip=30.0)

        team_games = insight_etl.team_games_for_qualified_thresholds(conn)
        qualified_ip = team_games * 1.0
        assert qualified_ip == 40.0, f"expected 40 IP, got {qualified_ip}"

        insight_etl.compute_advanced_metric_snapshots(
            conn, scope="season", snapshot_date="2026-05-17",
            min_pa=int(team_games * 3.1), min_ip=qualified_ip,
        )
        # 規定未到達 → ERA snapshot row 無し
        row = conn.execute(
            "SELECT COUNT(*) FROM advanced_metric_snapshots "
            "WHERE player_canonical='則本昂大' AND scope='season'"
        ).fetchone()
        assert row[0] == 0, f"則本 IP=30 < 40 規定未到達なのに snapshot 入った: count={row[0]}"
    finally:
        conn.close()


def test_qualified_pitcher_ip50_included_in_season_snapshot(tmp_path):
    """規定到達投手 (IP=50, 巨人 40 試合) は snapshot に入る."""
    conn = _open_seed_db(tmp_path)
    try:
        _seed_games(conn, team="巨人", n=40)
        _seed_player_with_ip(conn, canonical="規定到達投手", total_ip=50.0)

        team_games = insight_etl.team_games_for_qualified_thresholds(conn)
        insight_etl.compute_advanced_metric_snapshots(
            conn, scope="season", snapshot_date="2026-05-17",
            min_pa=int(team_games * 3.1), min_ip=team_games * 1.0,
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM advanced_metric_snapshots "
            "WHERE player_canonical='規定到達投手' AND scope='season' AND metric_name='ERA'"
        ).fetchone()
        assert row[0] == 1, f"規定到達投手 IP=50 >= 40 なのに snapshot に入っていない: count={row[0]}"
    finally:
        conn.close()
