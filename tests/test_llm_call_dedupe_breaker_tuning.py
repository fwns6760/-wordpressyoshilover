from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import llm_call_dedupe, rss_fetcher


NOW = datetime(2026, 5, 5, 22, 26, tzinfo=timezone(timedelta(hours=9)))


def _breaker_env(**overrides) -> dict[str, str]:
    env = {
        llm_call_dedupe.ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV: "1",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV: "0.5",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV: "3600",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WARMUP_SECONDS_ENV: "0",
        llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_MIN_SAMPLE_ENV: "0",
    }
    env.update(overrides)
    return env


def _seed_breaker_ledger(ledger_path: Path, *, miss_count: int, hit_count: int, now: datetime = NOW) -> None:
    for index in range(miss_count):
        llm_call_dedupe.record_gemini_cache_outcome(
            cache_hit_reason="miss",
            post_id=1000 + index,
            ledger_path=ledger_path,
            now=now - timedelta(minutes=11, seconds=index),
        )
    for index in range(hit_count):
        llm_call_dedupe.record_gemini_cache_outcome(
            cache_hit_reason="content_hash_exact",
            hit_kind="exact_hit",
            post_id=2000 + index,
            ledger_path=ledger_path,
            now=now - timedelta(minutes=6, seconds=index),
        )


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


def _build_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(f"test_llm_call_dedupe_breaker_tuning.{id(stream)}")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


def _log_events(stream: io.StringIO) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw_line in stream.getvalue().splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(payload)
    return events


class CacheMissBreakerTuningTests(unittest.TestCase):
    """Fixture coverage for the 2026-05-05 22:14 JST live rollback and tuning hooks."""

    def _evaluate(
        self,
        *,
        miss_count: int,
        hit_count: int,
        env: dict[str, str] | None = None,
        now: datetime = NOW,
        process_started_at: datetime | None = None,
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "llm_call_dedupe_ledger.jsonl"
            _seed_breaker_ledger(ledger_path, miss_count=miss_count, hit_count=hit_count, now=now)
            return llm_call_dedupe.evaluate_gemini_cache_miss_breaker(
                ledger_path=ledger_path,
                now=now,
                env=env or _breaker_env(),
                process_started_at=process_started_at,
            )

    def test_current_default_reproduces_live_rollback_shape_11miss_0hit(self):
        state = self._evaluate(
            miss_count=11,
            hit_count=0,
            env=_breaker_env(),
            process_started_at=NOW - timedelta(hours=2),
        )

        self.assertTrue(state["enabled"])
        self.assertTrue(state["tripped"])
        self.assertEqual(state["reason"], "miss_rate_above_threshold")
        self.assertEqual(state["miss_count"], 11)
        self.assertEqual(state["hit_count"], 0)
        self.assertEqual(state["sample_count"], 11)
        self.assertEqual(state["miss_rate"], 1.0)
        self.assertEqual(state["skip_reason"], llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON)

    def test_warmup_suppresses_trip_inside_process_start_window(self):
        state = self._evaluate(
            miss_count=11,
            hit_count=0,
            env=_breaker_env(
                **{
                    llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WARMUP_SECONDS_ENV: "300",
                }
            ),
            process_started_at=NOW - timedelta(seconds=60),
        )

        self.assertFalse(state["tripped"])
        self.assertTrue(state["warmup_active"])
        self.assertEqual(state["reason"], "warmup_active")
        self.assertIsNone(state["skip_reason"])

    def test_warmup_expires_and_allows_trip_after_window(self):
        state = self._evaluate(
            miss_count=11,
            hit_count=0,
            env=_breaker_env(
                **{
                    llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WARMUP_SECONDS_ENV: "300",
                }
            ),
            process_started_at=NOW - timedelta(seconds=600),
        )

        self.assertTrue(state["tripped"])
        self.assertFalse(state["warmup_active"])
        self.assertEqual(state["reason"], "miss_rate_above_threshold")

    def test_min_sample_suppresses_trip_until_threshold_sample_size_is_met(self):
        state = self._evaluate(
            miss_count=11,
            hit_count=0,
            env=_breaker_env(
                **{
                    llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_MIN_SAMPLE_ENV: "20",
                }
            ),
            process_started_at=NOW - timedelta(hours=1),
        )

        self.assertFalse(state["tripped"])
        self.assertTrue(state["min_sample_active"])
        self.assertEqual(state["reason"], "min_sample_not_met")
        self.assertEqual(state["sample_count"], 11)

    def test_threshold_comparison_matrix_matches_expected_trip_boundaries(self):
        cases = [
            {"miss_count": 11, "hit_count": 0, "expected": {0.5: True, 0.8: True, 0.9: True}},
            {"miss_count": 11, "hit_count": 20, "expected": {0.5: False, 0.8: False, 0.9: False}},
            {"miss_count": 11, "hit_count": 4, "expected": {0.5: True, 0.8: False, 0.9: False}},
            {"miss_count": 11, "hit_count": 2, "expected": {0.5: True, 0.8: True, 0.9: False}},
        ]

        for case in cases:
            miss_count = case["miss_count"]
            hit_count = case["hit_count"]
            for threshold, expected_trip in case["expected"].items():
                with self.subTest(miss_count=miss_count, hit_count=hit_count, threshold=threshold):
                    state = self._evaluate(
                        miss_count=miss_count,
                        hit_count=hit_count,
                        env=_breaker_env(
                            **{
                                llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV: str(threshold),
                            }
                        ),
                        process_started_at=NOW - timedelta(hours=1),
                    )
                    self.assertEqual(state["tripped"], expected_trip)

    def test_skip_reason_payload_is_logged_with_threshold_window_sample_and_hit_ratio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "llm_call_dedupe_ledger.jsonl"
            _seed_breaker_ledger(ledger_path, miss_count=10, hit_count=0, now=NOW)

            logger, stream = _build_logger()
            duplicate_guard_context: dict[str, object] = {}
            candidate_meta = _candidate(duplicate_guard_context=duplicate_guard_context)

            def _unexpected_request(**_kwargs):
                raise AssertionError("Gemini request should not run when breaker is open")

            with patch.object(llm_call_dedupe, "DEFAULT_LEDGER_PATH", ledger_path), \
                patch.object(rss_fetcher, "_gemini_cache_lookup", lambda *_args, **_kwargs: (None, "miss", 128)), \
                patch.object(rss_fetcher, "_request_gemini_strict_text", _unexpected_request), \
                patch.dict(
                    "os.environ",
                    _breaker_env(
                        **{
                            llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_THRESHOLD_ENV: "0.8",
                            llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS_ENV: "3600",
                        }
                    ),
                    clear=False,
                ):
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

            events = _log_events(stream)
            breaker_events = [event for event in events if event.get("event") == "gemini_cache_miss_breaker"]

            self.assertEqual(text, "")
            self.assertFalse(telemetry["gemini_call_made"])
            self.assertEqual(telemetry["skip_reason"], llm_call_dedupe.GEMINI_CACHE_MISS_BREAKER_SKIP_REASON)
            self.assertEqual(telemetry["cache_miss_breaker"]["sample_count"], 11)
            self.assertEqual(telemetry["cache_miss_breaker"]["hit_ratio"], 0.0)
            self.assertEqual(
                telemetry["skip_reason_payload"],
                {
                    "reason": "miss_rate_above_threshold",
                    "threshold": 0.8,
                    "window_seconds": 3600,
                    "sample_count": 11,
                    "min_sample": 0,
                    "miss_count": 11,
                    "hit_count": 0,
                    "miss_rate": 1.0,
                    "hit_ratio": 0.0,
                    "warmup_seconds": 0,
                },
            )
            self.assertEqual(len(breaker_events), 1)
            self.assertEqual(breaker_events[0]["threshold"], 0.8)
            self.assertEqual(breaker_events[0]["window_seconds"], 3600)
            self.assertEqual(breaker_events[0]["sample_count"], 11)
            self.assertEqual(breaker_events[0]["hit_ratio"], 0.0)
            self.assertEqual(
                breaker_events[0]["skip_reason_payload"],
                telemetry["skip_reason_payload"],
            )

    def test_disabled_breaker_never_trips_even_with_all_misses(self):
        state = self._evaluate(
            miss_count=11,
            hit_count=0,
            env=_breaker_env(
                **{
                    llm_call_dedupe.ENABLE_GEMINI_CACHE_MISS_BREAKER_ENV: "0",
                }
            ),
            process_started_at=NOW - timedelta(hours=1),
        )

        self.assertFalse(state["enabled"])
        self.assertFalse(state["tripped"])
        self.assertEqual(state["reason"], "breaker_disabled")
        self.assertIsNone(state["skip_reason"])


if __name__ == "__main__":
    unittest.main()
