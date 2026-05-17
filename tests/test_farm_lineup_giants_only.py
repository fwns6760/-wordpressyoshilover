"""Tests for issue #44 follow-up: farm/二軍 article は巨人スタメンのみ表示.

Bug pattern (post 68856): 【二軍】巨人 vs 西武 article で本文に
「📋 巨人スタメン」だけでなく「📋 西武スタメン」も emit されていた。
user 指示 (2026-05-17): farm/二軍 article は今後 巨人のスタメンだけでよい。

Fix: _filter_lineup_rows_for_subtype helper を rss_fetcher 直下に追加し、
body_subtype が ``farm`` / ``farm_lineup`` の場合は相手 row を除外して
巨人 row のみ返す。 _build_basic_lineup_table_block の 3 call site で
この helper を挟む。
"""

from __future__ import annotations

from src.rss_fetcher import (
    FARM_LINEUP_GIANTS_ONLY_SUBTYPES,
    _filter_lineup_rows_for_subtype,
)


def _sample_rows() -> list[dict]:
    return [
        {"name": "小濱", "team": "巨人", "position": "(6)", "order": "1"},
        {"name": "中山", "team": "巨人", "position": "(7)", "order": "2"},
        {"name": "西武打者A", "team": "相手", "position": "(8)", "order": "1"},
        {"name": "西武打者B", "team": "相手", "position": "(7)", "order": "2"},
    ]


def test_farm_subtype_filters_out_opponent_rows():
    rows = _sample_rows()
    filtered = _filter_lineup_rows_for_subtype(rows, "farm")
    teams = sorted({r["team"] for r in filtered})
    assert teams == ["巨人"], f"farm subtype で相手 row が残っている: {filtered!r}"
    assert len(filtered) == 2


def test_farm_lineup_subtype_filters_out_opponent_rows():
    rows = _sample_rows()
    filtered = _filter_lineup_rows_for_subtype(rows, "farm_lineup")
    teams = sorted({r["team"] for r in filtered})
    assert teams == ["巨人"], f"farm_lineup subtype で相手 row が残っている: {filtered!r}"


def test_lineup_subtype_keeps_both_teams():
    """1軍 lineup (試合速報 lineup subtype) は従来通り両方 keep."""
    rows = _sample_rows()
    filtered = _filter_lineup_rows_for_subtype(rows, "lineup")
    teams = sorted({r["team"] for r in filtered})
    assert teams == ["巨人", "相手"], f"1軍 lineup で相手 row が消えている: {filtered!r}"
    assert len(filtered) == 4


def test_postgame_and_live_update_subtypes_keep_both_teams():
    """1軍 postgame / live_update も従来通り両方 keep."""
    for subtype in ("postgame", "live_update", "pregame", ""):
        filtered = _filter_lineup_rows_for_subtype(_sample_rows(), subtype)
        teams = sorted({r["team"] for r in filtered})
        assert teams == ["巨人", "相手"], (
            f"subtype={subtype} で相手 row が消えている: {filtered!r}"
        )


def test_empty_rows_returns_as_is():
    assert _filter_lineup_rows_for_subtype([], "farm") == []
    assert _filter_lineup_rows_for_subtype([], "lineup") == []


def test_constant_is_frozenset():
    assert "farm" in FARM_LINEUP_GIANTS_ONLY_SUBTYPES
    assert "farm_lineup" in FARM_LINEUP_GIANTS_ONLY_SUBTYPES
    assert "lineup" not in FARM_LINEUP_GIANTS_ONLY_SUBTYPES
