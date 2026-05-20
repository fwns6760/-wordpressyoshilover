"""Tests for 403 Stage A3: scope-aware min_sample in insight_quality_gate.

新 scope vocabulary 対応 (last_N_games / last_N_pa / last_N_appearances /
last_N_ip)、 audit-based 値 (打者 last_3=8 AB / last_5=12 / last_10=20)。
既存 date scope (last_7d / last_30d / season 等) は完全不変。
"""

from __future__ import annotations

from src.analysis import insight_quality_gate as qg


# ─── 既存挙動 (scope=None or date-based) は完全不変 ──────────────────────────


def test_min_sample_batter_default_unchanged():
    """打者 metric (scope=None): 既存 20 PA を返す。"""
    assert qg.min_sample_for_metric("OPS") == 20
    assert qg.min_sample_for_metric("AVG") == 20
    assert qg.min_sample_for_metric("OBP") == 20
    assert qg.min_sample_for_metric("SLG") == 20
    assert qg.min_sample_for_metric("RISP") == 20


def test_min_sample_pitcher_default_unchanged():
    """投手 metric (scope=None): 既存 10 IP を返す。"""
    assert qg.min_sample_for_metric("ERA") == 10
    assert qg.min_sample_for_metric("K_per_9") == 10


def test_min_sample_fielding_unchanged():
    """守備 metric: scope に関わらず 10 (不変)。"""
    assert qg.min_sample_for_metric("UZR_proxy") == 10
    assert qg.min_sample_for_metric("UZR_proxy", scope="last_5_games") == 10


def test_min_sample_unknown_metric_returns_none():
    """unknown metric (counting stats): None を返す。"""
    assert qg.min_sample_for_metric("HR") is None
    assert qg.min_sample_for_metric("RBI") is None


def test_min_sample_existing_date_scope_unchanged():
    """既存 date scope (last_7d / last_30d / season): default value を返す。"""
    assert qg.min_sample_for_metric("OPS", scope="last_7d") == 20
    assert qg.min_sample_for_metric("OPS", scope="last_30d") == 20
    assert qg.min_sample_for_metric("OPS", scope="season") == 20
    assert qg.min_sample_for_metric("ERA", scope="last_7d") == 10


# ─── 403 新 scope (audit 反映値) ────────────────────────────────────────────


def test_min_sample_batter_last_3_games():
    """打者 last_3_games: audit-based 8 AB。"""
    assert qg.min_sample_for_metric("OPS", scope="last_3_games") == 8
    assert qg.min_sample_for_metric("AVG", scope="last_3_games") == 8


def test_min_sample_batter_last_5_games():
    """打者 last_5_games: audit-based 12 AB。"""
    assert qg.min_sample_for_metric("OPS", scope="last_5_games") == 12
    assert qg.min_sample_for_metric("OBP", scope="last_5_games") == 12


def test_min_sample_batter_last_10_games():
    """打者 last_10_games: audit-based 20 AB。"""
    assert qg.min_sample_for_metric("OPS", scope="last_10_games") == 20


def test_min_sample_batter_last_n_pa():
    """打者 last_N_pa: PA 自体を threshold (N そのもの)。"""
    assert qg.min_sample_for_metric("OPS", scope="last_30_pa") == 30
    assert qg.min_sample_for_metric("OPS", scope="last_50_pa") == 50
    assert qg.min_sample_for_metric("OPS", scope="last_100_pa") == 100


def test_min_sample_pitcher_last_n_appearances():
    """投手 last_N_appearances: 0 (登板数自体を threshold、 IP cumsum 不要)。"""
    assert qg.min_sample_for_metric("ERA", scope="last_3_appearances") == 0
    assert qg.min_sample_for_metric("ERA", scope="last_5_appearances") == 0
    assert qg.min_sample_for_metric("ERA", scope="last_10_appearances") == 0


def test_min_sample_pitcher_last_n_ip():
    """投手 last_N_ip: IP 自体を threshold (N そのもの)。"""
    assert qg.min_sample_for_metric("ERA", scope="last_5_ip") == 5
    assert qg.min_sample_for_metric("ERA", scope="last_10_ip") == 10
    assert qg.min_sample_for_metric("K_per_9", scope="last_5_ip") == 5


def test_min_sample_pitcher_last_n_games_413_fix():
    """投手 last_N_games: 413 fix で IP base の小さな threshold (リリーフ救済)."""
    # 413 fix: リリーフ (マルティネス 等) が 21:00 fire で skip 多発
    # last_5_games で min=10 → 3 に下げ、 5 IP → publish 候補化
    assert qg.min_sample_for_metric("ERA", scope="last_3_games") == 2
    assert qg.min_sample_for_metric("ERA", scope="last_5_games") == 3
    assert qg.min_sample_for_metric("ERA", scope="last_10_games") == 5
    assert qg.min_sample_for_metric("K_per_9", scope="last_5_games") == 3
