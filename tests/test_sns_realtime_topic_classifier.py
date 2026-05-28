"""Tests for sns_realtime_topic_classifier (ticket 445)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sns_realtime_topic_classifier import (  # noqa: E402
    classify_team_level,
    count_mentions,
    load_roster_aliases,
)


@pytest.fixture(scope="module")
def roster():
    return load_roster_aliases()


def test_load_roster_aliases_nonzero(roster):
    assert len(roster) > 100  # 136 名 × 複数 alias で 数百件


def test_ikusei_keyword_to_3gun(roster):
    assert classify_team_level("育成選手が初安打", roster) == "三軍"
    assert classify_team_level("三軍で初登板", roster) == "三軍"
    assert classify_team_level("3軍合宿", roster) == "三軍"


def test_farm_keyword_to_2gun(roster):
    assert classify_team_level("ファーム首位打者", roster) == "二軍"
    assert classify_team_level("二軍で完封勝利", roster) == "二軍"
    assert classify_team_level("イースタンリーグで初本塁打", roster) == "二軍"
    assert classify_team_level("2軍練習試合", roster) == "二軍"


def test_default_to_1gun_no_keyword(roster):
    assert classify_team_level("快勝！", roster) == "一軍"
    assert classify_team_level("試合終了", roster) == "一軍"


def test_player_alias_match_to_1gun(roster):
    # 坂本勇人 は player role
    result = classify_team_level("坂本勇人が3安打の活躍", roster)
    assert result == "一軍"


def test_ikusei_keyword_overrides_player_match(roster):
    # 育成 keyword は player match より優先
    result = classify_team_level("育成 林 燦が好投", roster)
    assert result == "三軍"


def test_farm_keyword_overrides_default(roster):
    result = classify_team_level("ファームで活躍中", roster)
    assert result == "二軍"


def test_count_mentions_basic(roster):
    posts = [
        "坂本勇人が3安打",
        "坂本勇人と岡本和真の連弾",
        "阿部監督のコメント",
    ]
    counts = count_mentions(posts, roster)
    assert counts.get("坂本勇人") == 2
    assert counts.get("岡本和真") == 1
    assert counts.get("阿部慎之助") == 1


def test_count_mentions_alias_dedup_per_post(roster):
    # 同 post 内で複数 alias がヒットしても 1 count
    posts = ["阿部監督と阿部慎之助監督のコメント"]
    counts = count_mentions(posts, roster)
    assert counts.get("阿部慎之助") == 1


def test_count_mentions_empty_text(roster):
    counts = count_mentions(["", None, "  "], roster)
    assert counts == {}


def test_count_mentions_no_match(roster):
    counts = count_mentions(["関係のない投稿"], roster)
    assert counts == {}
