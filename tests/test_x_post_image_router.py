"""437 image router unit tests."""
from __future__ import annotations

import pytest

from src.x_post_image_router import (
    DEFAULT_TEMPLATE,
    TEMPLATE_KEYS,
    select_template,
)


def test_default_for_empty_data():
    assert select_template({}) == DEFAULT_TEMPLATE
    assert select_template({"subtype": ""}) == DEFAULT_TEMPLATE


def test_ranking_maps_to_ranking_table():
    assert select_template({"subtype": "ranking"}) == "ranking_table"


def test_postgame_maps_to_scoreboard():
    assert select_template({"subtype": "postgame"}) == "scoreboard"


def test_lineup_maps_to_starting_lineup():
    assert select_template({"subtype": "lineup"}) == "starting_lineup"


def test_standings_maps_to_standings():
    assert select_template({"subtype": "standings"}) == "standings"


def test_pitcher_maps_to_pitcher_card():
    assert select_template({"subtype": "pitcher"}) == "pitcher_card"


def test_monthly_maps_to_monthly_summary():
    assert select_template({"subtype": "monthly"}) == "monthly_summary"


def test_trend_maps_to_chart_bars():
    assert select_template({"subtype": "trend"}) == "chart_bars"


def test_data_sheet_maps_to_data_sheet():
    assert select_template({"subtype": "data_sheet"}) == "data_sheet"


def test_spray_maps_to_spray_chart():
    assert select_template({"subtype": "spray"}) == "spray_chart"


def test_12team_bar_maps_to_12team_bar():
    assert select_template({"subtype": "12team_bar"}) == "12team_bar"


# ----- spotlight crown_count branching -----


@pytest.mark.parametrize("crown_count", [5, 6, 7, 8])
def test_spotlight_5plus_crowns_goes_to_12team_crown(crown_count):
    assert (
        select_template({"subtype": "spotlight", "crown_count": crown_count})
        == "12team_crown"
    )


@pytest.mark.parametrize("crown_count", [2, 3, 4])
def test_spotlight_2to4_crowns_goes_to_12team_crown_3(crown_count):
    assert (
        select_template({"subtype": "spotlight", "crown_count": crown_count})
        == "12team_crown_3"
    )


@pytest.mark.parametrize("crown_count", [0, 1])
def test_spotlight_low_crowns_goes_to_player_spotlight(crown_count):
    assert (
        select_template({"subtype": "spotlight", "crown_count": crown_count})
        == "player_spotlight"
    )


def test_spotlight_missing_crown_count_defaults_to_player_spotlight():
    # crown_count 未指定 → 0 扱い → player_spotlight
    assert select_template({"subtype": "spotlight"}) == "player_spotlight"


# ----- unknown / fallback -----


def test_unknown_subtype_falls_back_to_default():
    assert select_template({"subtype": "nonexistent_xyz"}) == DEFAULT_TEMPLATE


def test_none_data_does_not_crash():
    # router は data=None でも crash しない (caller の defensive 入力に堪える)
    assert select_template(None) == DEFAULT_TEMPLATE


def test_all_returned_keys_are_valid_templates():
    subtypes = [
        "ranking", "spotlight", "postgame", "lineup", "standings",
        "pitcher", "monthly", "trend", "data_sheet", "spray", "12team_bar",
        "nonexistent",
    ]
    for s in subtypes:
        key = select_template({"subtype": s, "crown_count": 6})
        assert key in TEMPLATE_KEYS, f"router returned unknown template_key={key}"
