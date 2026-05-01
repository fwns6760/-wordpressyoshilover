from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import llm_call_dedupe, rss_fetcher


NOW = datetime(2026, 5, 1, 15, 0, tzinfo=timezone(timedelta(hours=9)))


def _build_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(f"test_per_post_24h_budget.{id(stream)}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


def _log_events(stream: io.StringIO) -> list[dict]:
    events: list[dict] = []
    for raw_line in stream.getvalue().splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _candidate(**overrides) -> dict[str, object]:
    duplicate_guard_context = overrides.pop("duplicate_guard_context", {})
    payload: dict[str, object] = {
        "post_id": 321,
        "title": "【巨人】阿部監督が継投の狙いを説明",
        "summary": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "body_text": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "source_body": "巨人が阪神に勝利し、阿部監督が継投の狙いを説明した。",
        "category": "首脳陣",
        "article_subtype": "manager",
        "source_name": "スポーツ報知",
        "source_url": "https://news.hochi.news/articles/example.html",
        "source_type": "news",
        "source_links": [],
        "published_at": NOW,
        "has_game": True,
        "duplicate_guard_context": duplicate_guard_context,
    }
    payload.update(overrides)
    return payload


def _budget_env(**overrides) -> dict[str, str]:
    env = {
        llm_call_dedupe.ENABLE_PER_POST_24H_GEMINI_BUDGET_ENV: "1",
        llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_LIMIT_ENV: "5",
    }
    env.update(overrides)
    return env


def _breaker_env(**overrides) -> dict[str, str]:
    env = {
        llm_call_dedupe.ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV: "1",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV: "0.5",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV: "3600",
    }
    env.update(overrides)
    return env


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_evaluate_per_post_budget_flag_disabled_stays_inert(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    for minutes in (55, 45, 35, 25, 15, 5):
        llm_call_dedupe.record_gemini_call_attempt(
            post_id=321,
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
            model="gemini-2.5-flash",
        )

    state = llm_call_dedupe.evaluate_per_post_24h_gemini_budget(
        321,
        ledger_path=ledger_path,
        now=NOW,
        env={},
    )

    assert state["enabled"] is False
    assert state["call_count"] == 6
    assert state["remaining_calls"] == 0
    assert state["tripped"] is False


def test_evaluate_per_post_budget_counts_explicit_attempts_and_ignores_split_metric(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"

    for minutes in (55, 45, 35, 25):
        llm_call_dedupe.record_gemini_call_attempt(
            post_id=321,
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
            model="gemini-2.5-flash",
        )
    llm_call_dedupe.record_call(
        321,
        "repair-hash",
        "generated",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=10),
        provider="gemini",
        model="gemini-2.5-flash",
    )
    llm_call_dedupe.record_call(
        321,
        "repair-hash",
        "generated",
        skip_reason="content_hash_dedupe",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=5),
        provider="gemini",
        model="gemini-2.5-flash",
    )
    llm_call_dedupe.record_cache_hit_metric(
        hit_kind="dedupe_hit",
        post_id=321,
        content_hash="repair-hash",
        cache_hit_reason="content_hash_dedupe",
        skip_reason="content_hash_dedupe",
        layer="llm_call_dedupe",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=3),
        env={llm_call_dedupe.ENABLE_CACHE_HIT_SPLIT_METRIC_ENV: "1"},
    )

    state = llm_call_dedupe.evaluate_per_post_24h_gemini_budget(
        321,
        ledger_path=ledger_path,
        now=NOW,
        env=_budget_env(),
    )

    assert state["count_source"] == "explicit_attempts"
    assert state["call_count"] == 5
    assert state["remaining_calls"] == 0
    assert state["tripped"] is True
    assert state["skip_reason"] == llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_SKIP_REASON


def test_evaluate_per_post_budget_uses_cache_miss_fallback_when_explicit_rows_absent(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"

    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=20),
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="content_hash_exact",
        hit_kind="exact_hit",
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=15),
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=10),
    )

    state = llm_call_dedupe.evaluate_per_post_24h_gemini_budget(
        321,
        ledger_path=ledger_path,
        now=NOW,
        env=_budget_env(PER_POST_24H_GEMINI_BUDGET_LIMIT="3"),
    )

    assert state["count_source"] == "cache_miss_fallback"
    assert state["call_count"] == 2
    assert state["remaining_calls"] == 1
    assert state["tripped"] is False


def test_evaluate_per_post_budget_resets_after_24h(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"

    llm_call_dedupe.record_gemini_call_attempt(
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(hours=25),
        model="gemini-2.5-flash",
    )
    llm_call_dedupe.record_gemini_call_attempt(
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(hours=1),
        model="gemini-2.5-flash",
    )

    state = llm_call_dedupe.evaluate_per_post_24h_gemini_budget(
        321,
        ledger_path=ledger_path,
        now=NOW,
        env=_budget_env(),
    )

    assert state["call_count"] == 1
    assert state["remaining_calls"] == 4
    assert state["tripped"] is False


def test_gemini_text_with_per_post_budget_skips_when_limit_reached(monkeypatch, tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    history_path = tmp_path / "preflight_skip_history.jsonl"
    duplicate_guard_context: dict[str, object] = {}
    candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)
    logger, stream = _build_logger()

    for minutes in (55, 45, 35, 25, 15):
        llm_call_dedupe.record_gemini_call_attempt(
            post_id=321,
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
            model="gemini-2.5-flash",
        )

    monkeypatch.setattr(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(rss_fetcher, "PREFLIGHT_SKIP_HISTORY_DEFAULT_PATH", history_path)
    monkeypatch.setattr(rss_fetcher, "_gcs_client", lambda: None)
    monkeypatch.setattr(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 128))

    def _unexpected_request(**_kwargs):
        raise AssertionError("Gemini request should not run when per-post budget is exhausted")

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", _unexpected_request)
    monkeypatch.setenv("ENABLE_PREFLIGHT_SKIP_NOTIFICATION", "1")
    for key, value in _budget_env().items():
        monkeypatch.setenv(key, value)

    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url="https://example.com/per-post-budget",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        cache_manager=object(),
        candidate_meta=candidate_meta,
        now=NOW,
        log_label="test",
    )

    history_rows = _read_jsonl(history_path)
    ledger_rows = _read_jsonl(ledger_path)
    events = _log_events(stream)

    assert text == ""
    assert telemetry["gemini_call_made"] is False
    assert telemetry["skip_reason"] == llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_SKIP_REASON
    assert telemetry["skip_layer"] == rss_fetcher.PREFLIGHT_SKIP_LAYER
    assert telemetry["per_post_24h_gemini_budget"]["tripped"] is True
    assert duplicate_guard_context["postgame_strict_review_reason"] == llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_SKIP_REASON
    assert len(history_rows) == 1
    assert history_rows[0]["skip_reason"] == llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_SKIP_REASON
    assert sum(1 for row in ledger_rows if row.get("event") == llm_call_dedupe.GEMINI_CALL_ATTEMPT_EVENT) == 5
    assert any(event["event"] == "per_post_24h_gemini_budget" and event["tripped"] for event in events)
    assert any(
        event["event"] == "gemini_call_skipped"
        and event["skip_reason"] == llm_call_dedupe.PER_POST_24H_GEMINI_BUDGET_SKIP_REASON
        for event in events
    )


def test_gemini_text_with_per_post_budget_caps_attempt_limit_to_remaining_calls(monkeypatch, tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    duplicate_guard_context: dict[str, object] = {}
    candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)
    logger, _stream = _build_logger()
    captured: list[dict[str, object]] = []

    for minutes in (55, 45, 35, 25):
        llm_call_dedupe.record_gemini_call_attempt(
            post_id=321,
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
            model="gemini-2.5-flash",
        )

    monkeypatch.setattr(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 256))

    def _fake_request(**kwargs):
        captured.append(dict(kwargs))
        return "fresh text"

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", _fake_request)
    for key, value in _budget_env().items():
        monkeypatch.setenv(key, value)

    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url="https://example.com/remaining-one",
        content_text="本文B",
        prompt_template_id="prompt-v1",
        cache_manager=object(),
        candidate_meta=candidate_meta,
        now=NOW,
        log_label="test",
    )

    assert text == "fresh text"
    assert telemetry["gemini_call_made"] is True
    assert telemetry["per_post_24h_gemini_budget"]["remaining_calls"] == 1
    assert len(captured) == 1
    assert captured[0]["attempt_limit"] == 1
    assert captured[0]["budget_record_enabled"] is True
    assert captured[0]["budget_post_id"] == 321


def test_gemini_text_with_cache_breaker_keeps_precedence_over_per_post_budget(monkeypatch, tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    history_path = tmp_path / "preflight_skip_history.jsonl"
    duplicate_guard_context: dict[str, object] = {}
    candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)
    logger, stream = _build_logger()

    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        post_id=321,
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=15),
    )
    for minutes in (55, 45, 35, 25, 15):
        llm_call_dedupe.record_gemini_call_attempt(
            post_id=321,
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
            model="gemini-2.5-flash",
        )

    monkeypatch.setattr(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(rss_fetcher, "PREFLIGHT_SKIP_HISTORY_DEFAULT_PATH", history_path)
    monkeypatch.setattr(rss_fetcher, "_gcs_client", lambda: None)
    monkeypatch.setattr(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 128))

    def _unexpected_request(**_kwargs):
        raise AssertionError("Gemini request should not run when cache miss breaker is open")

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", _unexpected_request)
    monkeypatch.setenv("ENABLE_PREFLIGHT_SKIP_NOTIFICATION", "1")
    for key, value in _budget_env().items():
        monkeypatch.setenv(key, value)
    for key, value in _breaker_env().items():
        monkeypatch.setenv(key, value)

    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url="https://example.com/breaker-first",
        content_text="本文C",
        prompt_template_id="prompt-v1",
        cache_manager=object(),
        candidate_meta=candidate_meta,
        now=NOW,
        log_label="test",
    )

    history_rows = _read_jsonl(history_path)
    events = _log_events(stream)

    assert text == ""
    assert telemetry["gemini_call_made"] is False
    assert telemetry["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert telemetry["cache_miss_breaker"]["tripped"] is True
    assert duplicate_guard_context["postgame_strict_review_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert len(history_rows) == 1
    assert history_rows[0]["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert any(event["event"] == "gemini_cache_miss_breaker" and event["tripped"] for event in events)
    assert not any(event["event"] == "per_post_24h_gemini_budget" for event in events)
