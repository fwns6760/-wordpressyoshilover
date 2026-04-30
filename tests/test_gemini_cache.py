from __future__ import annotations

import inspect
import io
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from src import rss_fetcher
from src.gemini_cache import GeminiCacheBackendError, GeminiCacheManager


NOW = datetime(2026, 4, 30, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def _build_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(f"test_gemini_cache.{id(stream)}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
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


def _manager(tmp_path) -> GeminiCacheManager:
    return GeminiCacheManager(state_manager=None, local_cache_dir=tmp_path / "gemini-cache")


def _seed_cache(
    manager: GeminiCacheManager,
    *,
    source_url: str,
    content_text: str,
    prompt_template_id: str,
    generated_text: str,
    now: datetime,
) -> None:
    cache_key = rss_fetcher._build_gemini_cache_key(
        source_url=source_url,
        content_text=content_text,
        prompt_template_id=prompt_template_id,
    )
    manager.save(cache_key, generated_text, now=now)


def _run_wrapper(
    monkeypatch,
    *,
    cache_manager,
    source_url: str,
    content_text: str,
    prompt_template_id: str,
    request_return: str = "generated text",
    now: datetime = NOW,
):
    logger, stream = _build_logger()
    calls: list[dict] = []

    def fake_request(**kwargs):
        calls.append(dict(kwargs))
        return request_return

    monkeypatch.setattr(rss_fetcher, "_request_gemini_strict_text", fake_request)
    text, telemetry = rss_fetcher._gemini_text_with_cache(
        api_key="api-key",
        prompt="PROMPT",
        logger=logger,
        attempt_limit=3,
        min_chars=1,
        source_url=source_url,
        content_text=content_text,
        prompt_template_id=prompt_template_id,
        cache_manager=cache_manager,
        now=now,
        log_label="test",
    )
    return text, telemetry, calls, _log_events(stream)


def test_same_source_same_content_within_cooldown_hits_exact_cache(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(hours=1),
    )

    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
    )

    assert text == "cached text"
    assert telemetry["cache_hit"] is True
    assert telemetry["cache_hit_reason"] == "content_hash_exact"
    assert telemetry["gemini_call_made"] is False
    assert calls == []
    assert events[-1]["cache_hit_reason"] == "content_hash_exact"


def test_same_source_same_content_after_cooldown_still_hits_exact_cache(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(days=3),
    )

    text, telemetry, calls, _events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
    )

    assert text == "cached text"
    assert telemetry["cache_hit"] is True
    assert telemetry["cache_hit_reason"] == "content_hash_exact"
    assert telemetry["gemini_call_made"] is False
    assert calls == []


def test_same_source_different_content_within_cooldown_hits_cooldown_cache(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(hours=2),
    )

    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/a",
        content_text="本文B",
        prompt_template_id="prompt-v1",
    )

    assert text == "cached text"
    assert telemetry["cache_hit"] is True
    assert telemetry["cache_hit_reason"] == "cooldown_active"
    assert telemetry["gemini_call_made"] is False
    assert calls == []
    assert events[-1]["cache_hit_reason"] == "cooldown_active"


def test_same_source_different_content_after_cooldown_misses(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(days=2),
    )

    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/a",
        content_text="本文B",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit"] is False
    assert telemetry["cache_hit_reason"] == "miss"
    assert telemetry["gemini_call_made"] is True
    assert len(calls) == 1
    assert events[-1]["cache_hit_reason"] == "miss"


def test_new_source_misses_then_saves(monkeypatch, tmp_path):
    manager = _manager(tmp_path)

    first_text, first_telemetry, first_calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/new",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert first_text == "fresh text"
    assert first_telemetry["cache_hit_reason"] == "miss"
    assert len(first_calls) == 1
    assert events[-1]["cache_hit_reason"] == "miss"

    second_text, second_telemetry, second_calls, _events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/new",
        content_text="本文A",
        prompt_template_id="prompt-v1",
    )

    assert second_text == "fresh text"
    assert second_telemetry["cache_hit_reason"] == "content_hash_exact"
    assert second_calls == []


def test_different_source_same_content_misses(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(hours=1),
    )

    text, telemetry, calls, _events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/b",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit_reason"] == "miss"
    assert len(calls) == 1


def test_different_prompt_template_misses(monkeypatch, tmp_path):
    manager = _manager(tmp_path)
    _seed_cache(
        manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        generated_text="cached text",
        now=NOW - timedelta(hours=1),
    )

    text, telemetry, calls, _events = _run_wrapper(
        monkeypatch,
        cache_manager=manager,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v2",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit_reason"] == "miss"
    assert len(calls) == 1


def test_backend_error_fails_open_and_logs_warning(monkeypatch):
    class BackendErrorManager:
        def lookup(self, *_args, **_kwargs):
            raise GeminiCacheBackendError("gcs denied")

        def save(self, *_args, **_kwargs):
            return 0

    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=BackendErrorManager(),
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit_reason"] == "cache_backend_error"
    assert telemetry["gemini_call_made"] is True
    assert len(calls) == 1
    assert any(event["event"] == "gemini_cache_backend_error" for event in events)


def test_lookup_exception_fails_open_and_logs_warning(monkeypatch):
    class ExplodingManager:
        def lookup(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def save(self, *_args, **_kwargs):
            return 0

    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=ExplodingManager(),
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit_reason"] == "cache_backend_error"
    assert telemetry["gemini_call_made"] is True
    assert len(calls) == 1
    assert any(event["event"] == "gemini_cache_backend_error" for event in events)


def test_cache_disabled_preserves_existing_behavior(monkeypatch):
    text, telemetry, calls, events = _run_wrapper(
        monkeypatch,
        cache_manager=None,
        source_url="https://example.com/a",
        content_text="本文A",
        prompt_template_id="prompt-v1",
        request_return="fresh text",
    )

    assert text == "fresh text"
    assert telemetry["cache_hit"] is False
    assert telemetry["cache_hit_reason"] == "cache_disabled"
    assert telemetry["gemini_call_made"] is True
    assert len(calls) == 1
    assert events[-1]["cache_hit_reason"] == "cache_disabled"


def test_request_gemini_strict_signature_unchanged():
    signature = inspect.signature(rss_fetcher._request_gemini_strict_text)
    assert list(signature.parameters.keys()) == [
        "api_key",
        "prompt",
        "logger",
        "attempt_limit",
        "min_chars",
        "log_label",
        "source_url",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())


def test_generate_article_with_gemini_strict_uses_cache_wrapper(monkeypatch):
    captured: dict[str, str] = {}

    def fake_wrapper(**kwargs):
        captured.update(kwargs)
        return "cached text", {"cache_hit": True}

    monkeypatch.setenv("GEMINI_API_KEY", "api-key")
    monkeypatch.setattr(rss_fetcher, "strict_fact_mode_enabled", lambda: True)
    monkeypatch.setattr(rss_fetcher, "_fetch_team_stats_block_for_strict_article", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(rss_fetcher, "_build_source_fact_block", lambda *_args, **_kwargs: "source facts")
    monkeypatch.setattr(rss_fetcher, "_build_gemini_strict_prompt", lambda *_args, **_kwargs: "PROMPT")
    monkeypatch.setattr(rss_fetcher, "_detect_article_subtype", lambda *_args, **_kwargs: "manager")
    monkeypatch.setattr(rss_fetcher, "_gemini_text_with_cache", fake_wrapper)
    monkeypatch.setattr(rss_fetcher, "_get_gemini_cache_manager", lambda: "manager")

    result = rss_fetcher.generate_article_with_gemini(
        title="阿部監督が語る",
        summary="要約",
        category="首脳陣",
        real_reactions=[],
        has_game=False,
        source_name="報知",
        source_day_label="4月30日",
        source_type="news",
        tweet_url="https://example.com/a",
        source_entry=None,
    )

    assert result == "cached text"
    assert captured["source_url"] == "https://example.com/a"
    assert captured["prompt_template_id"].startswith("strict_article_v1")
    assert captured["cache_manager"] == "manager"


def test_postgame_strict_slotfill_path_uses_cache_wrapper(monkeypatch):
    captured: dict[str, str] = {}

    def fake_wrapper(**kwargs):
        captured.update(kwargs)
        return "", {"cache_hit": False}

    monkeypatch.setenv("GEMINI_API_KEY", "api-key")
    monkeypatch.setattr(rss_fetcher, "strict_fact_mode_enabled", lambda: True)
    monkeypatch.setattr(rss_fetcher, "_postgame_strict_enabled", lambda: True)
    monkeypatch.setattr(rss_fetcher, "_detect_article_subtype", lambda *_args, **_kwargs: "postgame")
    monkeypatch.setattr(rss_fetcher, "_build_source_fact_block", lambda *_args, **_kwargs: "source facts")
    monkeypatch.setattr(rss_fetcher, "_extract_game_score_token", lambda *_args, **_kwargs: "3-2")
    monkeypatch.setattr(rss_fetcher, "_gemini_text_with_cache", fake_wrapper)
    monkeypatch.setattr(rss_fetcher, "_get_gemini_cache_manager", lambda: "manager")
    logger, _stream = _build_logger()

    result = rss_fetcher._maybe_render_postgame_article_parts(
        title="巨人が3-2で勝利",
        summary="試合要約",
        category="試合速報",
        has_game=True,
        source_name="報知",
        source_url="https://example.com/postgame",
        source_type="news",
        source_entry=None,
        win_loss_hint="巨人勝利",
        logger=logger,
    )

    assert isinstance(result, rss_fetcher._PostgameStrictReviewFallback)
    assert captured["source_url"] == "https://example.com/postgame"
    assert captured["prompt_template_id"] == rss_fetcher.GEMINI_POSTGAME_STRICT_SLOTFILL_TEMPLATE_ID
    assert captured["cache_manager"] == "manager"


def test_postgame_article_parts_path_uses_cache_wrapper(monkeypatch):
    captured: dict[str, str] = {}

    def fake_wrapper(**kwargs):
        captured.update(kwargs)
        return "", {"cache_hit": False}

    monkeypatch.setenv("GEMINI_API_KEY", "api-key")
    monkeypatch.setattr(rss_fetcher, "strict_fact_mode_enabled", lambda: True)
    monkeypatch.setattr(rss_fetcher, "_postgame_strict_enabled", lambda: False)
    monkeypatch.setattr(rss_fetcher, "article_parts_renderer_postgame_enabled", lambda: True)
    monkeypatch.setattr(rss_fetcher, "_detect_article_subtype", lambda *_args, **_kwargs: "postgame")
    monkeypatch.setattr(rss_fetcher, "_build_source_fact_block", lambda *_args, **_kwargs: "source facts")
    monkeypatch.setattr(rss_fetcher, "_extract_game_score_token", lambda *_args, **_kwargs: "3-2")
    monkeypatch.setattr(rss_fetcher, "_fetch_team_stats_block_for_strict_article", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(rss_fetcher, "_build_game_parts_prompt_postgame", lambda **_kwargs: "PROMPT")
    monkeypatch.setattr(rss_fetcher, "_gemini_text_with_cache", fake_wrapper)
    monkeypatch.setattr(rss_fetcher, "_get_gemini_cache_manager", lambda: "manager")
    logger, _stream = _build_logger()

    result = rss_fetcher._maybe_render_postgame_article_parts(
        title="巨人が3-2で勝利",
        summary="試合要約",
        category="試合速報",
        has_game=True,
        source_name="報知",
        source_url="https://example.com/postgame",
        source_type="news",
        source_entry=None,
        win_loss_hint="巨人勝利",
        logger=logger,
    )

    assert result is None
    assert captured["source_url"] == "https://example.com/postgame"
    assert captured["prompt_template_id"] == rss_fetcher.GEMINI_POSTGAME_PARTS_TEMPLATE_ID
    assert captured["cache_manager"] == "manager"
