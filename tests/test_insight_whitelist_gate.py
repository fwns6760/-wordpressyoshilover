"""Tests for insight_whitelist + detector × metric gate (348 step 1).

検証軸:
  1. config load: JSON ファイルから ◯/× / 巨人 filter / 閾値 / label を取得できる
  2. metric gate: × metric (ISO/wOBA/BABIP/K_pct/BB_pct/WHIP/K_BB/FIP/xFIP/RF_proxy)
     を渡された detector は candidate insert しない
  3. ◯ metric (OPS/AVG/OBP/SLG/ERA/K_per_9/BB_per_9/HR_per_9/UZR_proxy) は通常通り insert
  4. 巨人 only filter: 非巨人 team_code (t/c/db/...) の選手は candidate insert されない
     (baseline 計算には使われるが title 主語にはならない)
  5. backward-compat: config 不在時は 既存挙動 (全 team 許可) を維持
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_etl  # noqa: E402
from src.analysis import insight_anomaly_detector as det  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402


# ─── fixtures ───────────────────────────────────────────────────────────────


def _seed_snapshots(conn, *, snapshot_date, scope, metric, ranking):
    """ranking = list of (player, team, value, sample, rank, total)"""
    for player, team, value, sample, rank, total in ranking:
        conn.execute(
            "INSERT INTO advanced_metric_snapshots "
            "(snapshot_date, scope, player_canonical, team_code, "
            "metric_name, metric_value, sample_size, league_rank, league_total) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_date, scope, player, team, metric, value, sample, rank, total),
        )
    conn.commit()


@pytest.fixture(autouse=True)
def _reset_whitelist_cache():
    """各 test の前後で whitelist cache を reset、 fixture 間の汚染を防止。"""
    wl.reset_cache()
    yield
    wl.reset_cache()


# ─── config load ─────────────────────────────────────────────────────────────


def test_config_loads_from_repo_default():
    """repo 直下 config/insight_whitelist.json が load できる。"""
    cfg = wl.load_whitelist_config(force_reload=True)
    assert cfg is not None
    assert cfg.get("version") == "1.0"
    assert "metrics_disallowed" in cfg
    assert "metric_name_ja" in cfg


def test_config_returns_none_when_missing(tmp_path):
    """config 不在時は None、 caller は backward-compat fallback すべき。"""
    missing = tmp_path / "missing.json"
    cfg = wl.load_whitelist_config(path=missing, force_reload=True)
    assert cfg is None


# ─── metric gate ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_metric", [
    "ISO", "wOBA", "BABIP", "K_pct", "BB_pct",
    "WHIP", "K_BB", "FIP", "xFIP",
    "RF_proxy",
])
def test_is_metric_allowed_blocks_x_metrics(bad_metric):
    """× metric は is_metric_allowed False を返す。"""
    assert wl.is_metric_allowed(bad_metric) is False


@pytest.mark.parametrize("good_metric", [
    "AVG", "OBP", "SLG", "OPS",
    "ERA", "K_per_9", "BB_per_9", "HR_per_9",
    "WIN_PCT", "FIELDING_PCT", "UZR_proxy", "WAR", "RISP",
])
def test_is_metric_allowed_passes_o_metrics(good_metric):
    """◯ metric は is_metric_allowed True を返す。"""
    assert wl.is_metric_allowed(good_metric) is True


def test_is_metric_allowed_default_true_when_config_no_file(tmp_path):
    """config file 不在時は True (backward-compat、 既存挙動維持)。"""
    missing = tmp_path / "no_config.json"
    cfg = wl.load_whitelist_config(path=missing, force_reload=True)
    assert cfg is None
    assert wl.is_metric_allowed("FIP", config=cfg) is True
    assert wl.is_metric_allowed("OPS", config=cfg) is True


# ─── 巨人 only filter ────────────────────────────────────────────────────────


def test_is_subject_team_only_giants():
    """team_code='g' のみ subject team (title 主語対象)。"""
    assert wl.is_subject_team("g") is True
    assert wl.is_subject_team(" g ") is True  # whitespace tolerant
    assert wl.is_subject_team("t") is False
    assert wl.is_subject_team("db") is False
    assert wl.is_subject_team(None) is False
    assert wl.is_subject_team("") is False


def test_is_subject_team_default_true_when_config_no_file(tmp_path):
    """config file 不在時は True (backward-compat、 既存挙動維持)。"""
    missing = tmp_path / "no_config.json"
    cfg = wl.load_whitelist_config(path=missing, force_reload=True)
    assert cfg is None
    assert wl.is_subject_team("t", config=cfg) is True
    assert wl.is_subject_team("g", config=cfg) is True


# ─── 日本語 label / scope ──────────────────────────────────────────────────


def test_metric_name_ja_mapping():
    """metric_name → 日本語 (OPS だけ英略号のまま)。"""
    assert wl.metric_name_ja("AVG") == "打率"
    assert wl.metric_name_ja("ERA") == "防御率"
    assert wl.metric_name_ja("K_per_9") == "奪三振率"
    assert wl.metric_name_ja("FIELDING_PCT") == "守備率"
    assert wl.metric_name_ja("UZR_proxy") == "簡易UZR"
    assert wl.metric_name_ja("OPS") == "OPS"
    assert wl.metric_name_ja("WAR") == "総合貢献度"
    # mapping 不在は原文 fallback
    assert wl.metric_name_ja("UNKNOWN_METRIC") == "UNKNOWN_METRIC"


def test_manual_metric_options_hide_disallowed_metrics():
    """手動画面候補にも × 指標を出さない。"""
    from src import manual_intake_insight_query as miq

    opts = miq.metric_options()
    assert "ERA" in opts
    assert "OPS" in opts
    assert "FIP" not in opts
    assert "wOBA" not in opts
    assert "WHIP" not in opts
    assert "UZR_proxy" in opts


def test_manual_query_rank_blocks_disallowed_fip_before_db_check(tmp_path):
    """直接 query API でも FIP は db 有無に関係なく拒否する。"""
    from src import manual_intake_insight_query as miq

    blocked = miq.query_rank(metric_name="FIP", db_path=tmp_path / "missing.db")
    assert blocked["ok"] is False
    assert blocked["reason"] == "metric_not_allowed:FIP"

    allowed = miq.query_rank(metric_name="UZR_proxy", db_path=tmp_path / "missing.db")
    assert allowed["ok"] is False
    assert allowed["reason"] == "db_not_available"


def test_scope_ja_mapping():
    assert wl.scope_ja("season") == "今シーズン"
    assert wl.scope_ja("last_5_games") == "直近5試合"
    assert wl.scope_ja("monthly") == "月別"


# ─── 閾値 ────────────────────────────────────────────────────────────────────


def test_thresholds_from_config():
    """率系 z-score 閾値 = 1.5σ、 counting TOP = 10。"""
    assert wl.zscore_sigma() == 1.5
    assert wl.counting_top_n() == 10
    assert det.DEFAULT_ZSCORE_THRESHOLD == 1.5


# ─── detector integration: × metric が candidate に入らない ────────────────


def test_zscore_batter_skips_disallowed_metric(tmp_path):
    """× metric (BABIP) を渡しても candidate insert 0。"""
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [(f"avg_{i}", "t", 0.250 + i * 0.005, 50, i + 2, 6) for i in range(5)]
        ranking.append(("巨人A", "g", 0.500, 100, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="BABIP", ranking=ranking)
        ids = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14",
            metric_name="BABIP", threshold_sigma=1.5,
        )
        assert ids == []
        cnt = conn.execute(
            "SELECT COUNT(*) FROM article_candidates "
            "WHERE signal_type = ?", (det.SIGNAL_ZSCORE_BATTER,),
        ).fetchone()[0]
        assert cnt == 0
    finally:
        conn.close()


def test_zscore_pitcher_skips_disallowed_metric(tmp_path):
    """× metric (FIP) を渡しても candidate insert 0。"""
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [(f"avg_p{i}", "t", 3.5 + i * 0.1, 30, i + 2, 6) for i in range(5)]
        ranking.append(("巨人E", "g", 0.500, 50, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="season",
                        metric="FIP", ranking=ranking)
        ids = det.detect_zscore_pitcher_outliers(
            conn, snapshot_date="2026-05-14", metric_name="FIP",
            threshold_sigma=1.5,
        )
        assert ids == []
    finally:
        conn.close()


# ─── detector integration: 巨人 only filter ─────────────────────────────────


def test_zscore_batter_only_giants_in_candidates(tmp_path):
    """baseline は全 team で計算、 candidate insert は team='g' のみ。

    10 非巨人 baseline (0.700) + 1 巨人 outlier (1.500) + 1 非巨人 outlier (1.500)。
    z-score ≈ 2.14σ で 1.5σ threshold を上回るが、 非巨人 outlier は filter される。
    """
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [(f"avg_{i}", "t", 0.700, 50, i + 2, 12) for i in range(10)]
        ranking.append(("巨人A", "g", 1.500, 100, 1, 12))
        ranking.append(("阪神X", "t", 1.500, 100, 2, 12))  # 非巨人 outlier
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="OPS", ranking=ranking)
        ids = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14",
            metric_name="OPS", threshold_sigma=1.5,
        )
        rows = conn.execute(
            "SELECT player_canonical, notes FROM article_candidates "
            "WHERE candidate_id IN (" + ",".join("?" * len(ids)) + ")", ids,
        ).fetchall() if ids else []
        # 巨人A は含まれる、 阪神X は含まれない (非巨人 filter)
        players = [r[0] for r in rows]
        assert "巨人A" in players
        assert "阪神X" not in players
    finally:
        conn.close()


def test_o_metric_passes_for_giants(tmp_path):
    """◯ metric (OPS) + 巨人 candidate は通常通り insert される (回帰防止)。"""
    db = tmp_path / "t.db"
    conn = insight_etl.open_db(db_path=db, schema_path=insight_etl.DEFAULT_SCHEMA)
    try:
        ranking = [(f"avg_{i}", "t", 0.700 + i * 0.005, 50, i + 2, 6) for i in range(5)]
        ranking.append(("巨人A", "g", 1.500, 100, 1, 6))
        _seed_snapshots(conn, snapshot_date="2026-05-14", scope="last_30d",
                        metric="OPS", ranking=ranking)
        ids = det.detect_zscore_batter_outliers(
            conn, snapshot_date="2026-05-14",
            metric_name="OPS", threshold_sigma=1.5,
        )
        assert len(ids) >= 1
    finally:
        conn.close()
