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
    logger = logging.getLogger(f"test_cache_miss_breaker.{id(stream)}")
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


def test_evaluate_gemini_cache_miss_breaker_counts_legacy_and_cache_rows(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"

    llm_call_dedupe.record_call(
        321,
        "hash-hit",
        "generated",
        skip_reason="content_hash_dedupe",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=50),
        provider="gemini",
        model="gemini-2.5-flash",
        hit_kind="dedupe_hit",
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="content_hash_exact",
        hit_kind="exact_hit",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=40),
    )
    llm_call_dedupe.record_call(
        322,
        "hash-miss-generated",
        "generated",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=20),
        provider="gemini",
        model="gemini-2.5-flash",
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=10),
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        ledger_path=ledger_path,
        now=NOW - timedelta(hours=2),
    )

    state = llm_call_dedupe.evaluate_gemini_cache_miss_breaker(
        ledger_path=ledger_path,
        now=NOW,
        env=_breaker_env(),
    )

    assert state["enabled"] is True
    assert state["tripped"] is False
    assert state["miss_count"] == 2
    assert state["hit_count"] == 2
    assert state["total_count"] == 4
    assert state["miss_rate"] == 0.5
    assert state["hit_kind_counts"] == {"dedupe_hit": 1, "exact_hit": 1}


def test_evaluate_gemini_cache_miss_breaker_trips_above_threshold(tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"

    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=50),
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=5),
    )
    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="content_hash_exact",
        hit_kind="exact_hit",
        ledger_path=ledger_path,
        now=NOW - timedelta(hours=2),
    )

    state = llm_call_dedupe.evaluate_gemini_cache_miss_breaker(
        ledger_path=ledger_path,
        now=NOW,
        env=_breaker_env(),
    )

    assert state["tripped"] is True
    assert state["miss_count"] == 2
    assert state["hit_count"] == 0
    assert state["miss_rate"] == 1.0
    assert state["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON


def test_gemini_text_with_cache_breaker_skips_gemini_and_marks_review(monkeypatch, tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    history_path = tmp_path / "preflight_skip_history.jsonl"
    duplicate_guard_context: dict[str, object] = {}
    candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)
    logger, stream = _build_logger()

    llm_call_dedupe.record_gemini_cache_outcome(
        cache_hit_reason="miss",
        ledger_path=ledger_path,
        now=NOW - timedelta(minutes=15),
    )

    monkeypatch.setattr(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(rss_fetcher, "PREFLIGHT_SKIP_HISTORY_DEFAULT_PATH", history_path)
    monkeypatch.setattr(rss_fetcher, "_gcs_client", lambda: None)
    monkeypatch.setattr(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 128))

    def _unexpected_request(**_kwargs):
        raise AssertionError("Gemini request should not run when breaker is open")

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", _unexpected_request)
    monkeypatch.setenv("ENABLE_PREFLIGHT_SKIP_NOTIFICATION", "1")
    for key, value in _breaker_env().items():
        monkeypatch.setenv(key, value)

    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url="https://example.com/breaker-open",
        content_text="本文A",
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
    assert telemetry["cache_hit_reason"] == "miss"
    assert telemetry["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert telemetry["skip_layer"] == rss_fetcher.PREFLIGHT_SKIP_LAYER
    assert telemetry["cache_miss_breaker"]["tripped"] is True
    assert duplicate_guard_context["postgame_strict_review_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert len(history_rows) == 1
    assert history_rows[0]["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
    assert any(event["event"] == "gemini_cache_miss_breaker" and event["tripped"] for event in events)
    assert any(
        event["event"] == "gemini_call_skipped"
        and event["skip_reason"] == llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON
        for event in events
    )


def test_gemini_text_with_cache_breaker_auto_resets_below_threshold(monkeypatch, tmp_path):
    ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    duplicate_guard_context: dict[str, object] = {}
    candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)
    logger, _stream = _build_logger()
    request_calls: list[dict[str, object]] = []

    for minutes in (55, 45, 35):
        llm_call_dedupe.record_gemini_cache_outcome(
            cache_hit_reason="content_hash_exact",
            hit_kind="exact_hit",
            ledger_path=ledger_path,
            now=NOW - timedelta(minutes=minutes),
        )

    monkeypatch.setattr(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 256))

    def _fake_request(**kwargs):
        request_calls.append(dict(kwargs))
        return "fresh text"

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", _fake_request)
    for key, value in _breaker_env().items():
        monkeypatch.setenv(key, value)

    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url="https://example.com/breaker-reset",
        content_text="本文B",
        prompt_template_id="prompt-v1",
        cache_manager=object(),
        candidate_meta=candidate_meta,
        now=NOW,
        log_label="test",
    )

    assert text == "fresh text"
    assert telemetry["gemini_call_made"] is True
    assert telemetry["cache_hit_reason"] == "miss"
    assert telemetry["cache_miss_breaker"]["tripped"] is False
    assert telemetry["cache_miss_breaker"]["miss_count"] == 1
    assert telemetry["cache_miss_breaker"]["hit_count"] == 3
    assert "skip_reason" not in telemetry
    assert "postgame_strict_review_reason" not in duplicate_guard_context
    assert len(request_calls) == 1
