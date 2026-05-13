"""Tests for src.analysis.insight_nl_query."""

from __future__ import annotations

import pytest

from src.analysis import insight_nl_query as nlq


# ─── position aliases ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("セカンド", "二"),
        ("二塁手", "二"),
        ("2B", "二"),
        ("ショート", "遊"),
        ("遊撃", "遊"),
        ("センター", "中"),
        ("中堅手", "中"),
        ("ファースト", "一"),
        ("レフト", "左"),
        ("ピッチャー", "投"),
        ("捕手", "捕"),
    ],
)
def test_position_aliases(phrase, expected):
    result = nlq.parse_question(phrase + " OPS トップ10")
    assert result["position"] == expected


def test_ambiguous_position_marks_unresolved():
    r = nlq.parse_question("内野の OPS トップ10")
    # 内野 is ambiguous (could be 1B/2B/3B/SS)
    assert r["position"] is None
    assert "position_ambiguous" in r["unresolved"]


# ─── metric aliases ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("OPS", "OPS"),
        ("打率", "AVG"),
        ("出塁率", "OBP"),
        ("長打率", "SLG"),
        ("防御率", "ERA"),
        ("ERA", "ERA"),
        ("WHIP", "WHIP"),
        ("FIP", "FIP"),
        ("UZR", "UZR_proxy"),
        ("RF", "RF_proxy"),
        ("K/9", "K_per_9"),
        ("奪三振率", "K_per_9"),
        ("wOBA", "wOBA"),
        ("ISO", "ISO"),
        ("三振率", "K_pct"),
    ],
)
def test_metric_aliases(phrase, expected):
    result = nlq.parse_question(f"巨人 {phrase} トップ10")
    assert result["metric"] == expected


def test_unknown_metric_marks_unresolved():
    r = nlq.parse_question("巨人 WAR トップ10")
    assert r["metric"] is None
    assert "metric" in r["unresolved"]


# ─── top_n extraction ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("トップ10", 10),
        ("上位5", 5),
        ("TOP3", 3),
        ("8位", 8),
        ("トップ20", 20),
    ],
)
def test_top_n_extraction(phrase, expected):
    r = nlq.parse_question(f"巨人 OPS {phrase}")
    assert r["top_n"] == expected


def test_top_n_default_when_missing():
    r = nlq.parse_question("巨人 OPS")
    assert r["top_n"] == 10


def test_top_n_capped_at_50():
    r = nlq.parse_question("巨人 OPS トップ100")
    assert r["top_n"] == 50


# ─── league detection ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("セリーグ", "central"),
        ("セ・リーグ", "central"),
        ("パリーグ", "pacific"),
        ("パ・リーグ", "pacific"),
        ("全12球団", "all"),
    ],
)
def test_league_detection(phrase, expected):
    r = nlq.parse_question(f"{phrase} の OPS トップ10")
    assert r["league"] == expected


def test_league_not_detected_returns_none():
    r = nlq.parse_question("OPS トップ10")
    assert r["league"] is None


# ─── focus player ────────────────────────────────────────────────────────


def test_focus_player_giants_full_name():
    r = nlq.parse_question("巨人の戸郷翔征の FIP は何位？")
    assert r["focus_player"] == "戸郷翔征"


def test_focus_player_surname_fallback():
    r = nlq.parse_question("戸郷の FIP は何位？")
    # 戸郷 surname → 戸郷翔征 (unique in roster; 吉川 has multiple
    # entries after the 2026-05-13 roster expansion so surname-only
    # fallback for 吉川 is intentionally ambiguous and returns None).
    assert r["focus_player"] == "戸郷翔征"


def test_focus_player_unknown_is_none():
    r = nlq.parse_question("ベーブ・ルースの OPS は何位？")
    assert r["focus_player"] is None


# ─── user's example case ─────────────────────────────────────────────────


def test_user_example_se_league_second_uzr_top10():
    """「セリーグのセカンドUZRトップ10は？」をパース可能か"""
    r = nlq.parse_question("セリーグのセカンドUZRトップ10は？")
    assert r["league"] == "central"
    assert r["position"] == "二"
    assert r["metric"] == "UZR_proxy"
    assert r["top_n"] == 10
    assert r["unresolved"] == []


def test_user_example_ace_FIP_ranking():
    r = nlq.parse_question("先発投手のFIPランキングトップ5")
    assert r["position"] == "投"
    assert r["metric"] == "FIP"
    assert r["top_n"] == 5


def test_uzr_without_position_marks_unresolved():
    r = nlq.parse_question("巨人選手のUZRトップ10")
    # UZR_proxy requires position
    assert r["metric"] == "UZR_proxy"
    assert "position" in r["unresolved"]


# ─── raw_text round trip ─────────────────────────────────────────────────


def test_raw_text_preserved():
    text = "  巨人の岡本和真wOBAは？  "
    r = nlq.parse_question(text)
    assert r["raw_text"] == text.strip()
