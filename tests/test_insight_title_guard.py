"""Tests for data-insight runtime title period guard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import insight_title_guard as guard  # noqa: E402
from src.analysis import insight_whitelist as wl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_whitelist_cache():
    wl.reset_cache()
    yield
    wl.reset_cache()


def test_title_guard_passes_existing_period_title():
    result = guard.ensure_title_period(
        "【巨人データ】大城卓三 OPS .912、リーグ4位（直近5試合）",
        scope="last_5_games",
    )
    assert result.ok is True
    assert result.title.endswith("（直近5試合）")
    assert result.appended_label == ""


def test_title_guard_auto_appends_known_scope():
    result = guard.ensure_title_period(
        "【巨人データ】大城卓三 OPS .912、リーグ4位",
        scope="last_5_games",
    )
    assert result.ok is True
    assert result.title == "【巨人データ】大城卓三 OPS .912、リーグ4位（直近5試合）"
    assert result.appended_label == "直近5試合"


def test_title_guard_does_not_accept_raw_scope_code_as_period():
    result = guard.ensure_title_period(
        "【巨人データ】大城卓三 OPS .912 last_5_games",
        scope="last_5_games",
    )
    assert result.ok is True
    assert result.title.endswith("last_5_games（直近5試合）")


def test_title_guard_does_not_treat_current_value_as_period():
    result = guard.ensure_title_period(
        "【巨人データ】竹丸和幸 防御率2.83 現在値",
        scope="season",
    )
    assert result.ok is True
    assert result.title.endswith("（今シーズン）")


def test_title_guard_blocks_when_period_unknown():
    result = guard.ensure_title_period(
        "【巨人データ】大城卓三 OPS .912、リーグ4位",
    )
    assert result.ok is False
    assert result.reason == "missing_period_in_title"


def test_title_guard_treats_game_date_as_period():
    result = guard.ensure_title_period(
        "【巨人データ】岡本和真、2安打3打点 (5/16 阪神戦)",
    )
    assert result.ok is True
    assert result.title.endswith("(5/16 阪神戦)")


def test_scope_label_for_week_and_month_is_reader_friendly():
    assert guard.period_label_for_scope("last_7d") == "直近1週間"
    assert guard.period_label_for_scope("last_30d") == "直近1ヶ月"
