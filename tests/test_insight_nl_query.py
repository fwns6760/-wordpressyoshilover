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


# ─── LLM fallback (Gemini Flash) ─────────────────────────────────────────


class _FakeLLMClient:
    """Mock client matching the contract _build_gemini_client returns."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0

    def parse(self, question: str) -> str:
        self.calls += 1
        return self.response_text


def test_llm_fallback_disabled_returns_rule_result(tmp_path, monkeypatch):
    # Empty/unparseable input — rule-based returns metric=None
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    r = nlq.parse_question("打撃絶好調なのはだれ？", llm_fallback=False)
    assert r["metric"] is None
    assert r["source"] == "rule"
    assert "metric" in r["unresolved"]


def test_llm_fallback_fires_when_rule_misses_metric(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    fake = _FakeLLMClient(
        '{"metric":"OPS","position":null,"league":null,"top_n":null,"focus_player":null}'
    )
    r = nlq.parse_question("打撃絶好調なのはだれ？", llm_client=fake)
    assert fake.calls == 1
    assert r["metric"] == "OPS"
    assert r["source"] == "llm_fallback"
    # metric resolved → unresolved no longer contains 'metric'
    assert "metric" not in r["unresolved"]


def test_llm_fallback_not_fired_when_rule_already_found_metric(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    fake = _FakeLLMClient('{"metric":"FIP"}')
    r = nlq.parse_question("OPSトップ10", llm_client=fake)
    # Rule found OPS, LLM never called
    assert fake.calls == 0
    assert r["metric"] == "OPS"
    assert r["source"] == "rule"


def test_llm_fallback_drops_unknown_metric(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    fake = _FakeLLMClient(
        '{"metric":"得点圏打率","position":null,"league":null,"top_n":null}'
    )
    r = nlq.parse_question("得点圏で熱い奴", llm_client=fake)
    # LLM returned an unknown metric — normalized to None, stays unresolved
    assert r["metric"] is None
    assert "metric" in r["unresolved"]


def test_llm_fallback_validates_focus_player_against_roster(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    # LLM hallucinates a player name not in the roster
    fake = _FakeLLMClient(
        '{"metric":"OPS","position":null,"league":null,"top_n":null,'
        '"focus_player":"架空の選手"}'
    )
    r = nlq.parse_question("〇〇のOPS知りたい", llm_client=fake)
    assert r["metric"] == "OPS"
    assert r["focus_player"] is None  # roster check dropped invalid name


def test_llm_fallback_invalid_json_returns_rule_result(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    fake = _FakeLLMClient("not json at all")
    r = nlq.parse_question("打撃絶好調なのはだれ？", llm_client=fake)
    # Fallback failed to parse → rule result stands
    assert r["metric"] is None
    assert r["source"] == "rule"


def test_llm_budget_zero_cap_blocks_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(tmp_path / "b.json"))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "0")
    fake = _FakeLLMClient('{"metric":"OPS"}')
    r = nlq.parse_question("打撃絶好調なのはだれ？", llm_client=fake)
    assert fake.calls == 0
    assert r["metric"] is None
    assert r["source"] == "rule"


def test_llm_budget_records_usage_on_success(tmp_path, monkeypatch):
    budget_path = tmp_path / "b.json"
    monkeypatch.setenv("INSIGHT_NL_LLM_BUDGET_PATH", str(budget_path))
    monkeypatch.setenv("INSIGHT_NL_LLM_DAILY_CAP", "10")
    fake = _FakeLLMClient('{"metric":"OPS"}')
    nlq.parse_question("打撃絶好調なのはだれ？", llm_client=fake)
    import json as _json
    data = _json.loads(budget_path.read_text(encoding="utf-8"))
    assert sum(data.values()) == 1


def test_normalize_response_clamps_top_n_out_of_range():
    out = nlq._normalize_llm_response(
        '{"metric":"OPS","top_n":9999}'
    )
    assert out is not None
    assert out["top_n"] is None  # >50 → dropped
