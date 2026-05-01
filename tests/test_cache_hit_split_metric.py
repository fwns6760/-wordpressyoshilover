from __future__ import annotations

import json

from src import llm_call_dedupe
from src.gemini_cache import (
    DEFAULT_MODEL_NAME,
    GeminiCacheKey,
    GeminiCacheValue,
    classify_lookup_hit_kind,
)


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_classify_lookup_hit_kind_returns_exact_for_same_prompt_and_model():
    cache_key = GeminiCacheKey(
        source_url_hash="source-hash",
        content_hash="content-hash",
        prompt_template_id="prompt-v1",
    )
    cached_value = GeminiCacheValue(
        generated_text="cached text",
        generated_at_iso="2026-05-01T12:00:00+09:00",
        model=DEFAULT_MODEL_NAME,
        prompt_template_id="prompt-v1",
    )

    assert (
        classify_lookup_hit_kind(
            cache_key=cache_key,
            cached_value=cached_value,
            hit_reason="content_hash_exact",
            expected_model=DEFAULT_MODEL_NAME,
        )
        == "exact_hit"
    )


def test_classify_lookup_hit_kind_returns_cooldown_for_model_mismatch():
    cache_key = GeminiCacheKey(
        source_url_hash="source-hash",
        content_hash="content-hash",
        prompt_template_id="prompt-v1",
    )
    cached_value = GeminiCacheValue(
        generated_text="cached text",
        generated_at_iso="2026-05-01T12:00:00+09:00",
        model="gemini-2.5-pro",
        prompt_template_id="prompt-v1",
    )

    assert (
        classify_lookup_hit_kind(
            cache_key=cache_key,
            cached_value=cached_value,
            hit_reason="content_hash_exact",
            expected_model=DEFAULT_MODEL_NAME,
        )
        == "cooldown_hit"
    )


def test_record_call_writes_dedupe_hit_metric_when_enabled(monkeypatch, tmp_path):
    dedupe_ledger_path = tmp_path / "llm_call_dedupe_ledger.jsonl"
    metric_ledger_path = tmp_path / "cache_hit_split_metric_ledger.jsonl"
    content_hash = llm_call_dedupe.compute_content_hash(321, "本文です。")

    monkeypatch.setenv(llm_call_dedupe.ENABLE_CACHE_HIT_SPLIT_METRIC_ENV, "1")
    monkeypatch.setenv(llm_call_dedupe.CACHE_HIT_SPLIT_METRIC_LEDGER_PATH_ENV, str(metric_ledger_path))

    llm_call_dedupe.record_call(
        321,
        content_hash,
        "generated",
        skip_reason="content_hash_dedupe",
        ledger_path=dedupe_ledger_path,
        prompt_template_id="strict_article_v1_game",
        model=DEFAULT_MODEL_NAME,
        source_url_hash="source-hash",
        reused_from_timestamp="2026-05-01T09:00:00+09:00",
    )

    dedupe_rows = _read_jsonl(dedupe_ledger_path)
    metric_rows = _read_jsonl(metric_ledger_path)

    assert len(dedupe_rows) == 1
    assert dedupe_rows[0]["skip_reason"] == "content_hash_dedupe"
    assert len(metric_rows) == 1
    assert metric_rows[0]["event"] == "cache_hit_split_metric"
    assert metric_rows[0]["hit_kind"] == "dedupe_hit"
    assert metric_rows[0]["post_id"] == 321
    assert metric_rows[0]["content_hash"] == content_hash
    assert metric_rows[0]["prompt_template_id"] == "strict_article_v1_game"
    assert metric_rows[0]["model"] == DEFAULT_MODEL_NAME
    assert metric_rows[0]["cache_hit_reason"] == "content_hash_dedupe"


def test_record_cache_hit_metric_is_noop_when_flag_disabled(tmp_path):
    metric_ledger_path = tmp_path / "cache_hit_split_metric_ledger.jsonl"

    payload = llm_call_dedupe.record_cache_hit_metric(
        hit_kind="exact_hit",
        post_id=321,
        content_hash="content-hash",
        ledger_path=metric_ledger_path,
        env={},
    )

    assert payload is None
    assert not metric_ledger_path.exists()


def test_resolve_hit_kind_defaults_unknown_for_legacy_rows():
    legacy_payload = {
        "timestamp": "2026-05-01T12:00:00+09:00",
        "post_id": 321,
        "content_hash": "content-hash",
        "result": "generated",
    }

    assert llm_call_dedupe.resolve_hit_kind(legacy_payload) == "unknown"
    assert llm_call_dedupe.resolve_hit_kind({"hit_kind": "dedupe_hit"}) == "dedupe_hit"
