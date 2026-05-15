"""Tests for 348 step 3 Phase A+B+C: scope 拡張 foundational.

検証軸:
  1. _scope_window が monthly / weekly を正しく返す
  2. _player_last_n_game_window が直近 N 試合の date range を返す
  3. _player_last_n_game_window が試合数不足時に None
  4. compute_advanced_metric_snapshots が last_5_games / last_10_games で
     per-player rolling 集計を行う
  5. compute_advanced_metric_snapshots が monthly / weekly で範囲集計
  6. publisher の scope_label が新 scope を日本語化
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_advanced_metrics as adv  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_whitelist_cache():
    wl.reset_cache()
    yield
    wl.reset_cache()


# ─── _scope_window: monthly / weekly ──────────────────────────────────────


def test_scope_window_monthly():
    """monthly = 当月 1 日から snapshot_date まで。"""
    ws, we = insight_etl._scope_window("monthly", "2026-05-15")
    assert ws == "2026-05-01"
    assert we == "2026-05-15"


def test_scope_window_monthly_first_of_month():
    """snapshot_date が月初 = 1 日のみの window (same day)。"""
    ws, we = insight_etl._scope_window("monthly", "2026-05-01")
    assert ws == "2026-05-01"
    assert we == "2026-05-01"


def test_scope_window_weekly_friday():
    """2026-05-15 (金) → 月曜 2026-05-11 から。"""
    ws, we = insight_etl._scope_window("weekly", "2026-05-15")
    assert ws == "2026-05-11"
    assert we == "2026-05-15"


def test_scope_window_weekly_monday():
    """月曜 snapshot = 同日 1 日のみ。"""
    ws, we = insight_etl._scope_window("weekly", "2026-05-11")
    assert ws == "2026-05-11"
    assert we == "2026-05-11"


def test_scope_window_weekly_sunday():
    """日曜 snapshot = 月-日 7 日間。"""
    ws, we = insight_etl._scope_window("weekly", "2026-05-17")
    assert ws == "2026-05-11"
    assert we == "2026-05-17"


def test_scope_window_existing_scopes_unchanged():
    """既存 season / last_7d / last_30d は regression なし。"""
    ws, we = insight_etl._scope_window("season", "2026-05-15")
    assert ws == "2026-01-01"
    assert we == "2026-05-15"

    ws, we = insight_etl._scope_window("last_7d", "2026-05-15")
    assert ws == "2026-05-09"
    assert we == "2026-05-15"

    ws, we = insight_etl._scope_window("last_30d", "2026-05-15")
    assert ws == "2026-04-16"
    assert we == "2026-05-15"


def test_scope_window_unknown_raises():
    with pytest.raises(ValueError):
        insight_etl._scope_window("not_a_scope", "2026-05-15")


# ─── _player_last_n_game_window ──────────────────────────────────────────


def _open_db(tmp_path):
    return insight_etl.open_db(db_path=tmp_path / "t.db", schema_path=insight_etl.DEFAULT_SCHEMA)


def _seed_game(conn, *, game_id, game_date):
    conn.execute(
        "INSERT INTO games (game_id, game_date, opponent, home_away, giants_score, "
        "opp_score, result, source_url, source_kind, ingested_at) "
        "VALUES (?, ?, 't', 'home', 0, 0, '', '', 'test', '2026-05-15T00:00:00Z')",
        (game_id, game_date),
    )


def _seed_batting(conn, *, game_id, player_canonical, AB=4, H=2):
    conn.execute(
        "INSERT INTO batting_logs (game_id, team_role, slot_order, position, "
        "player_display, player_canonical, is_sub, AB, R, H, RBI, SB, atbats_json) "
        "VALUES (?, 'home', 1, '中', ?, ?, 0, ?, 0, ?, 0, 0, '[]')",
        (game_id, player_canonical, player_canonical, AB, H),
    )


def test_player_last_n_game_window_returns_date_range(tmp_path):
    """直近 5 試合の (oldest, latest) を返す。"""
    conn = _open_db(tmp_path)
    try:
        for i, date in enumerate([
            "2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13",
            "2026-05-14", "2026-05-15",
        ]):
            gid = f"g{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="坂本")
        conn.commit()

        window = insight_etl._player_last_n_game_window(
            conn, "坂本", 5, "2026-05-15", "batting_logs",
        )
        assert window is not None
        oldest, latest = window
        assert oldest == "2026-05-11"  # 直近 5 試合の最古
        assert latest == "2026-05-15"  # 直近 5 試合の最新
    finally:
        conn.close()


def test_player_last_n_game_window_returns_none_if_insufficient(tmp_path):
    """試合数不足時は None。"""
    conn = _open_db(tmp_path)
    try:
        for i, date in enumerate(["2026-05-12", "2026-05-13", "2026-05-14"]):
            gid = f"g{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="新人")
        conn.commit()
        window = insight_etl._player_last_n_game_window(
            conn, "新人", 5, "2026-05-15", "batting_logs",
        )
        assert window is None  # 3 試合しかない
    finally:
        conn.close()


def test_player_last_n_game_window_unknown_table_raises(tmp_path):
    conn = _open_db(tmp_path)
    try:
        with pytest.raises(ValueError):
            insight_etl._player_last_n_game_window(
                conn, "p", 5, "2026-05-15", "unknown_table",
            )
    finally:
        conn.close()


# ─── compute_advanced_metric_snapshots: 新 scope ────────────────────────


def _seed_player(conn, canonical, team_code="g"):
    insight_etl.seed_teams(conn)
    conn.execute(
        "INSERT OR IGNORE INTO players (player_canonical, team_code, role, active) "
        "VALUES (?, ?, 'batter', 1)",
        (canonical, team_code),
    )


def test_compute_snapshots_last_5_games_per_player(tmp_path):
    """last_5_games で per-player rolling 集計が実行される。

    試合数が 5 に満たない player は skip、 5 以上で集計される。
    """
    conn = _open_db(tmp_path)
    try:
        _seed_player(conn, "充足", "g")
        _seed_player(conn, "不足", "g")
        # 充足: 5 試合分の batting_logs
        for i, date in enumerate([
            "2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14",
        ]):
            gid = f"a{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="充足", AB=10, H=4)
        # 不足: 3 試合のみ
        for i, date in enumerate(["2026-05-13", "2026-05-14", "2026-05-15"]):
            gid = f"b{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="不足", AB=10, H=4)
        conn.commit()

        n = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="last_5_games", snapshot_date="2026-05-15",
            min_pa=3, min_ip=0.0,
        )
        # 充足 のみ snapshot insert (1 player × 複数 metric)
        assert n > 0
        rows = conn.execute(
            "SELECT player_canonical FROM advanced_metric_snapshots "
            "WHERE scope = 'last_5_games' GROUP BY player_canonical"
        ).fetchall()
        players = {r[0] for r in rows}
        assert "充足" in players
        assert "不足" not in players
    finally:
        conn.close()


def test_compute_snapshots_monthly(tmp_path):
    """monthly scope で当月 1 日から snapshot_date まで集計。"""
    conn = _open_db(tmp_path)
    try:
        _seed_player(conn, "選手A", "g")
        # 5/1 から 5/15 まで複数試合
        for i, date in enumerate([
            "2026-05-01", "2026-05-05", "2026-05-10", "2026-05-15",
        ]):
            gid = f"m{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="選手A", AB=10, H=4)
        # 4/30 (前月) は range 外
        _seed_game(conn, game_id="apr", game_date="2026-04-30")
        _seed_batting(conn, game_id="apr", player_canonical="選手A", AB=10, H=10)
        conn.commit()

        n = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="monthly", snapshot_date="2026-05-15",
            min_pa=3, min_ip=0.0,
        )
        assert n > 0
        # 5 月の累計 AB=40, H=16 → AVG=0.400
        row = conn.execute(
            "SELECT metric_value FROM advanced_metric_snapshots "
            "WHERE scope = 'monthly' AND metric_name = 'AVG' AND player_canonical = ?",
            ("選手A",),
        ).fetchone()
        assert row is not None
        assert row[0] == 0.4
    finally:
        conn.close()


def test_compute_snapshots_weekly(tmp_path):
    """weekly scope で ISO 週月曜から集計。"""
    conn = _open_db(tmp_path)
    try:
        _seed_player(conn, "選手B", "g")
        # 5/11 (月) から 5/15 (金)
        for i, date in enumerate([
            "2026-05-11", "2026-05-13", "2026-05-15",
        ]):
            gid = f"w{i}"
            _seed_game(conn, game_id=gid, game_date=date)
            _seed_batting(conn, game_id=gid, player_canonical="選手B", AB=10, H=3)
        # 5/10 (前週日曜) は範囲外
        _seed_game(conn, game_id="prev", game_date="2026-05-10")
        _seed_batting(conn, game_id="prev", player_canonical="選手B", AB=10, H=10)
        conn.commit()

        n = insight_etl.compute_advanced_metric_snapshots(
            conn, scope="weekly", snapshot_date="2026-05-15",
            min_pa=3, min_ip=0.0,
        )
        assert n > 0
        row = conn.execute(
            "SELECT metric_value FROM advanced_metric_snapshots "
            "WHERE scope = 'weekly' AND metric_name = 'AVG' AND player_canonical = ?",
            ("選手B",),
        ).fetchone()
        assert row is not None
        # 当週 AB=30, H=9 → AVG=0.300
        assert row[0] == 0.3
    finally:
        conn.close()


# ─── publisher scope label ─────────────────────────────────────────────


def test_publisher_scope_label_new_scopes():
    """publisher の scope_label が新 scope を日本語化 (348 step 3)。"""
    from src.analysis import anomaly_article_publisher as pub
    # internal scope_label dict は _render_unified_article 内で定義、
    # 直接 access できないので config 側を確認
    cfg = wl.load_whitelist_config(force_reload=True)
    assert cfg is not None
    scope_map = cfg.get("scope_ja", {})
    assert scope_map.get("last_5_games") == "直近5試合"
    assert scope_map.get("last_10_games") == "直近10試合"
    assert scope_map.get("monthly") == "月別"
    assert scope_map.get("weekly") == "週別"
