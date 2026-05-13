"""Tests for src.analysis.insight_atbats_parser."""

from __future__ import annotations

import pytest

from src.analysis import insight_atbats_parser as p


# ─── basic result classes ─────────────────────────────────────────────────


def test_empty_or_dash_is_no_pa():
    for token in ("", "-", " "):
        r = p.parse_atbat(token)
        assert r["result_class"] == "other"
        assert r["bases"] == 0
        assert r["fielding_position"] is None


def test_strikeout_variants():
    for token in ("三 振", "三振", "見三振", "空三振"):
        r = p.parse_atbat(token)
        assert r["is_strikeout"] is True
        assert r["result_class"] == "strikeout"
        assert r["bases"] == 0


def test_walk_variants():
    for token in ("四 球", "四球"):
        r = p.parse_atbat(token)
        assert r["is_walk"] is True
        assert r["bases"] == 1
        assert r["result_class"] == "walk"


def test_hbp_variant():
    r = p.parse_atbat("死 球")
    assert r["is_hbp"] is True
    assert r["bases"] == 1


# ─── hits & HR ────────────────────────────────────────────────────────────


def test_single_hit_to_center():
    r = p.parse_atbat("中前安")
    assert r["result_class"] == "hit"
    assert r["bases"] == 1
    assert r["fielding_position"] == "中"


def test_single_hit_to_right():
    r = p.parse_atbat("右前安")
    assert r["bases"] == 1
    assert r["fielding_position"] == "右"


def test_home_run_left():
    r = p.parse_atbat("左越本①")
    assert r["is_hr"] is True
    assert r["bases"] == 4
    assert r["fielding_position"] == "左"
    assert r["result_class"] == "hit"


def test_home_run_with_rbi_marker():
    r = p.parse_atbat("右中本②")
    assert r["is_hr"] is True
    assert r["bases"] == 4
    # 右中 → 右 を最初に拾う想定 (中も含まれるが detect_position は最初の hit)
    assert r["fielding_position"] in {"右", "中"}


def test_triple_to_right_center():
    r = p.parse_atbat("右中３②")
    assert r["result_class"] == "hit"
    assert r["bases"] == 3


def test_double_to_left():
    r = p.parse_atbat("左中２②")
    assert r["result_class"] == "hit"
    assert r["bases"] == 2


# ─── outs ─────────────────────────────────────────────────────────────────


def test_grounder_to_second():
    r = p.parse_atbat("二ゴロ")
    assert r["result_class"] == "out"
    assert r["is_grounder"] is True
    assert r["fielding_position"] == "二"


def test_flyout_to_left():
    r = p.parse_atbat("左 飛")
    assert r["result_class"] == "out"
    assert r["is_fly"] is True
    assert r["fielding_position"] == "左"


def test_double_play_started_at_second():
    r = p.parse_atbat("二併打")
    assert r["is_double_play"] is True
    assert r["result_class"] == "out"
    assert r["fielding_position"] == "二"


def test_sacrifice_fly():
    r = p.parse_atbat("中犠飛")
    assert r["is_sacrifice"] is True
    assert r["result_class"] == "sac_fly"
    assert r["is_fly"] is True


def test_error_marker():
    """失 marker → error, batter reached"""
    r = p.parse_atbat("遊失")
    assert r["is_error"] is True
    assert r["result_class"] == "error"
    assert r["bases"] == 1
    assert r["fielding_position"] == "遊"


# ─── aggregate_for_defense ────────────────────────────────────────────────


def test_aggregate_groups_by_position():
    atbats = [
        "中前安",     # 中 / hit
        "二ゴロ",     # 二 / out
        "右越本①",   # 右 / HR (hit)
        "三 振",      # K, no position
        "二併打",     # 二 / out (double play)
        "遊失",       # 遊 / error
        "-",          # skip
    ]
    agg = p.aggregate_for_defense(atbats)
    assert agg["中"]["opportunities"] == 1
    assert agg["中"]["hits_allowed"] == 1
    assert agg["中"]["converted_outs"] == 0
    assert agg["二"]["opportunities"] == 2
    assert agg["二"]["converted_outs"] == 2
    assert agg["二"]["hits_allowed"] == 0
    assert agg["右"]["opportunities"] == 1
    assert agg["右"]["hits_allowed"] == 1
    assert agg["遊"]["opportunities"] == 1
    assert agg["遊"]["errors"] == 1
    assert agg["遊"]["hits_allowed"] == 1
    # 三振 has no position so doesn't appear
    assert "投" not in agg
    assert "捕" not in agg


def test_aggregate_empty_input_returns_empty_dict():
    assert p.aggregate_for_defense([]) == {}


def test_aggregate_only_no_op_tokens():
    assert p.aggregate_for_defense(["-", "", "三 振", "四 球"]) == {}
