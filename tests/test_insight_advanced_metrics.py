"""Tests for src.analysis.insight_advanced_metrics."""

from __future__ import annotations

import pytest

from src.analysis import insight_advanced_metrics as m


# ─── BattingLine.coerce ────────────────────────────────────────────────────


def test_coerce_computes_PA_and_TB_when_zero():
    line = m.BattingLine(AB=4, H=2, H1=1, H2=1, BB=1, HBP=0, SF=0).coerce()
    assert line.PA == 5  # AB+BB+HBP+SF+SH = 4+1+0+0+0
    assert line.TB == 3  # 1 single + 1 double


def test_coerce_respects_explicit_PA_TB():
    line = m.BattingLine(AB=4, H=2, PA=99, TB=99).coerce()
    assert line.PA == 99
    assert line.TB == 99


# ─── batting metrics ───────────────────────────────────────────────────────


def test_avg_basic():
    assert m.avg(m.BattingLine(AB=4, H=2)) == 0.5


def test_avg_zero_AB_returns_none():
    assert m.avg(m.BattingLine(AB=0)) is None


def test_obp_basic():
    """4 AB / 2 H / 1 BB / 1 HBP / 1 SF → (2+1+1) / (4+1+1+1) = 4/7 ≈ .5714"""
    line = m.BattingLine(AB=4, H=2, BB=1, HBP=1, SF=1)
    assert m.obp(line) == round(4 / 7, 4)


def test_slg_basic():
    """4 AB, single+double+HR → TB=1+2+4=7, SLG = 7/4 = 1.75"""
    line = m.BattingLine(AB=4, H=3, H1=1, H2=1, HR=1)
    assert m.slg(line) == 1.75


def test_ops_basic():
    """AVG .333 OBP .400 SLG .750 → OPS 1.150"""
    line = m.BattingLine(AB=3, H=1, H2=1, BB=1, HBP=0, SF=0, PA=4, TB=1 + 2)
    # AVG = 1/3 ≈ .3333, OBP = (1+1+0)/(3+1+0+0) = 2/4 = .5, SLG = 3/3 = 1.0
    assert m.ops(line) == round((2 / 4) + 1.0, 4)


def test_iso_basic():
    """SLG - AVG. With 4 AB, 2 H, 1 of which is HR → SLG=(1+4)/4=1.25, AVG=.5,
    ISO=.75"""
    line = m.BattingLine(AB=4, H=2, H1=1, HR=1)
    assert m.iso(line) == 0.75


def test_k_pct_and_bb_pct():
    line = m.BattingLine(AB=4, H=1, BB=2, SO=2, PA=6)
    assert m.k_pct(line) == round(2 / 6, 4)
    assert m.bb_pct(line) == round(2 / 6, 4)


def test_babip_basic():
    """5 H (1 HR) / 10 AB / 2 SO / 0 SF → (5-1)/(10-2-1+0) = 4/7 ≈ .5714"""
    line = m.BattingLine(AB=10, H=5, HR=1, SO=2, SF=0)
    assert m.babip(line) == round(4 / 7, 4)


def test_babip_denominator_zero_returns_none():
    """K + HR が AB を超える病的ケース → None"""
    line = m.BattingLine(AB=4, H=0, HR=4, SO=0)
    assert m.babip(line) is None


def test_woba_known_line():
    """Single line with 1 single, 0 BB, 0 HBP → wOBA = WOBA_WEIGHT_1B / denom.
    denom = AB + BB + SF + HBP = 4."""
    line = m.BattingLine(AB=4, H=1, H1=1, BB=0, HBP=0, SF=0)
    expected = round(m.WOBA_WEIGHT_1B / 4, 4)
    assert m.woba(line) == expected


def test_woba_excludes_ibb():
    """IBB は wOBA 分母に入れない (BB - IBB を numerator に)"""
    line = m.BattingLine(AB=3, H=0, BB=2, IBB=2, HBP=0, SF=0)
    # denom = 3 + (2-2) + 0 + 0 = 3, numerator = 0 (BB-IBB=0)
    assert m.woba(line) == 0.0


# ─── pitching metrics ──────────────────────────────────────────────────────


def test_era_basic():
    """9 IP / 3 ER → ERA = 3.0"""
    assert m.era(m.PitchingLine(IP=9.0, ER=3)) == 3.0


def test_era_zero_IP_returns_none():
    assert m.era(m.PitchingLine(IP=0, ER=5)) is None


def test_whip_basic():
    """6 IP / 4 H / 2 BB → WHIP = 6/6 = 1.0"""
    assert m.whip(m.PitchingLine(IP=6.0, H=4, BB=2)) == 1.0


def test_k9_bb9_hr9():
    line = m.PitchingLine(IP=6.0, SO=8, BB=2, HR=1)
    assert m.k_per_9(line) == round(8 * 9 / 6, 2)
    assert m.bb_per_9(line) == round(2 * 9 / 6, 2)
    assert m.hr_per_9(line) == round(1 * 9 / 6, 2)


def test_k_bb_ratio_basic():
    assert m.k_bb_ratio(m.PitchingLine(SO=10, BB=2)) == 5.0


def test_k_bb_ratio_zero_bb_returns_none():
    assert m.k_bb_ratio(m.PitchingLine(SO=10, BB=0)) is None


def test_fip_basic():
    """6 IP / 1 HR / 2 BB / 0 HBP / 8 K → (13+6-16)/6 + 3.10 = 3/6+3.10 = 3.6"""
    line = m.PitchingLine(IP=6.0, HR=1, BB=2, HBP=0, SO=8)
    expected = round((13 * 1 + 3 * 2 - 2 * 8) / 6 + 3.10, 3)
    assert m.fip(line) == expected


def test_fip_constant_override():
    line = m.PitchingLine(IP=9.0, HR=0, BB=0, HBP=0, SO=9)
    base = m.fip(line, constant=2.50)
    assert base is not None
    # raw = (0+0-18)/9 = -2.0, + 2.50 = 0.5
    assert base == 0.5


def test_xfip_returns_value_when_IP_positive():
    line = m.PitchingLine(IP=6.0, HR=1, BB=2, HBP=0, SO=8)
    v = m.xfip(line)
    assert v is not None
    # xFIP should differ from FIP because it uses expected HR
    assert v != m.fip(line)


def test_era_plus_basic():
    """player_ERA=3.0, league_ERA=4.0 → ERA+ = 4.0/3.0*100 ≈ 133.3"""
    assert m.era_plus(3.0, 4.0) == 133.3


def test_era_plus_handles_invalid_inputs():
    assert m.era_plus(None, 4.0) is None
    assert m.era_plus(3.0, None) is None
    assert m.era_plus(0.0, 4.0) is None


# ─── batch helpers ────────────────────────────────────────────────────────


def test_all_batter_metrics_returns_full_set():
    line = m.BattingLine(AB=4, H=2, H1=1, HR=1, BB=1, SO=1, HBP=0, SF=0)
    result = m.all_batter_metrics(line)
    expected_keys = {"AVG", "OBP", "SLG", "OPS", "ISO", "wOBA",
                     "K_pct", "BB_pct", "BABIP"}
    assert set(result.keys()) == expected_keys
    assert all(v is None or isinstance(v, float) for v in result.values())


def test_all_pitcher_metrics_returns_full_set():
    # 348 step 2: WIN_PCT added to all_pitcher_metrics (勝率)
    line = m.PitchingLine(IP=6.0, H=4, HR=1, BB=2, SO=8, ER=2)
    result = m.all_pitcher_metrics(line)
    expected_keys = {"ERA", "WHIP", "K_per_9", "BB_per_9", "HR_per_9",
                     "K_BB", "FIP", "xFIP", "WIN_PCT"}
    assert set(result.keys()) == expected_keys


def test_all_pitcher_metrics_zero_IP_all_none():
    result = m.all_pitcher_metrics(m.PitchingLine(IP=0))
    assert all(v is None for v in result.values())
