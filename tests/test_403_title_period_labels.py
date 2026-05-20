"""Tests for 403 Stage A5: title period labels for new scope vocabulary.

新 scope (last_N_games / last_N_pa / last_N_appearances / last_N_ip) の
日本語 period label を insight_title_guard が認識すること、 config の
scope_ja に lookup が通ること。
"""

from __future__ import annotations

from src.analysis import insight_title_guard as tg
from src.analysis import insight_whitelist as wl


# ─── scope_ja config (whitelist.json) lookup ─────────────────────────────────


def test_scope_ja_existing_unchanged():
    """既存 scope は完全不変。"""
    assert wl.scope_ja("season") == "今シーズン"
    assert wl.scope_ja("last_7d") == "直近1週間"
    assert wl.scope_ja("last_30d") == "直近1ヶ月"
    assert wl.scope_ja("last_5_games") == "直近5試合"
    assert wl.scope_ja("last_10_games") == "直近10試合"


def test_scope_ja_new_games_scopes():
    assert wl.scope_ja("last_3_games") == "直近3試合"


def test_scope_ja_new_pa_scopes():
    assert wl.scope_ja("last_30_pa") == "直近30打席"
    assert wl.scope_ja("last_50_pa") == "直近50打席"
    assert wl.scope_ja("last_100_pa") == "直近100打席"


def test_scope_ja_new_appearance_scopes():
    assert wl.scope_ja("last_3_appearances") == "直近3登板"
    assert wl.scope_ja("last_5_appearances") == "直近5登板"
    assert wl.scope_ja("last_10_appearances") == "直近10登板"


def test_scope_ja_new_ip_scopes():
    assert wl.scope_ja("last_5_ip") == "直近5投球回"
    assert wl.scope_ja("last_10_ip") == "直近10投球回"


# ─── period_label_for_scope (title_guard fallback) ───────────────────────────


def test_period_label_for_scope_existing_unchanged():
    assert tg.period_label_for_scope("last_5_games") == "直近5試合"
    assert tg.period_label_for_scope("season") == "今シーズン"


def test_period_label_for_scope_new_pa():
    assert tg.period_label_for_scope("last_30_pa") == "直近30打席"


def test_period_label_for_scope_new_appearance():
    assert tg.period_label_for_scope("last_5_appearances") == "直近5登板"


def test_period_label_for_scope_new_ip():
    assert tg.period_label_for_scope("last_10_ip") == "直近10投球回"


# ─── title_has_period (新 unit 認識) ─────────────────────────────────────────


def test_title_has_period_existing_unit_unchanged():
    assert tg.title_has_period("【巨人データ】 岡本 OPS .912 (直近5試合)")
    assert tg.title_has_period("【巨人データ】 戸郷 ERA 2.10 (直近10試合)")


def test_title_has_period_new_pa_unit():
    """直近N打席 を period marker として認識する。"""
    assert tg.title_has_period("【巨人データ】 岡本 OPS .950 (直近30打席)")
    assert tg.title_has_period("【巨人データ】 浦田 AVG .310 (直近50打席)")


def test_title_has_period_new_appearance_unit():
    """直近N登板 を period marker として認識する。"""
    assert tg.title_has_period("【巨人データ】 戸郷 ERA 1.85 (直近5登板)")


def test_title_has_period_new_ip_unit():
    """直近N投球回 を period marker として認識する。"""
    assert tg.title_has_period("【巨人データ】 マルティネス K_per_9 11.5 (直近10投球回)")


# ─── ensure_title_period (新 scope 経由で自動 append) ───────────────────────


def test_ensure_title_period_appends_new_pa_label():
    """scope=last_30_pa で period 無し title に '直近30打席' を append。"""
    result = tg.ensure_title_period(
        "【巨人データ】 岡本 OPS .950", scope="last_30_pa",
    )
    assert result.ok is True
    assert "直近30打席" in result.title


def test_ensure_title_period_appends_new_ip_label():
    """scope=last_5_ip で '直近5投球回' を append。"""
    result = tg.ensure_title_period(
        "【巨人データ】 マルティネス ERA 2.50", scope="last_5_ip",
    )
    assert result.ok is True
    assert "直近5投球回" in result.title


def test_compact_period_label_new_units():
    """compact_period_label が新 unit のスペース除去をする。"""
    assert tg.compact_period_label("直近 30 打席") == "直近30打席"
    assert tg.compact_period_label("直近 5 登板") == "直近5登板"
    assert tg.compact_period_label("直近 10 投球回") == "直近10投球回"
