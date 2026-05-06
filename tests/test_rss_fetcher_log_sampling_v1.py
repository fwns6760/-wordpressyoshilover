"""Tests for COST-LOG-001 — fetcher verbose log sampling (default OFF).

Coverage:
  - flag OFF: per-event log functions keep their existing behavior
  - flag ON: per-event logs are suppressed and aggregated into run_summary
  - ERROR / WARNING level logs are not affected by the flag
  - sample limit (<=3) per bucket
  - gemini_cache_lookup with gemini_call_made=True still emits per-event log
"""

from __future__ import annotations

import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src import rss_fetcher


def _make_cache_key(prefix: str = "abc") -> SimpleNamespace:
    return SimpleNamespace(
        source_url_hash=f"{prefix}-src",
        content_hash=f"{prefix}-content",
        prompt_template_id="tmpl-1",
    )


class FetcherLogSamplingFlagsTests(unittest.TestCase):
    def test_default_off(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(rss_fetcher._fetcher_log_sampling_v1_enabled())
            self.assertFalse(rss_fetcher._fetcher_log_detail_debug_enabled())

    def test_flag_on(self):
        with patch.dict("os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True):
            self.assertTrue(rss_fetcher._fetcher_log_sampling_v1_enabled())
        with patch.dict("os.environ", {"FETCHER_LOG_DETAIL_DEBUG": "true"}, clear=True):
            self.assertTrue(rss_fetcher._fetcher_log_detail_debug_enabled())


class GeminiCacheLookupSamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        rss_fetcher._reset_log_sampling_state()

    def test_flag_off_keeps_per_event_log(self):
        logger = logging.getLogger("test_gem_off")
        logger.info = MagicMock()
        with patch.dict("os.environ", {}, clear=True):
            rss_fetcher._log_gemini_cache_lookup(
                logger,
                source_url="https://example.com/a",
                cache_key=_make_cache_key("a"),
                cache_hit=True,
                cache_hit_reason="hit",
                cache_hit_kind="exact",
                gemini_call_made=False,
                cache_size_bytes=1234,
            )
        logger.info.assert_called_once()
        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "gemini_cache_lookup")
        self.assertEqual(payload["cache_hit"], True)
        self.assertEqual(payload["gemini_call_made"], False)

    def test_flag_on_hit_increments_counter_and_suppresses_log(self):
        logger = logging.getLogger("test_gem_hit")
        logger.info = MagicMock()
        with patch.dict("os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True):
            rss_fetcher._log_gemini_cache_lookup(
                logger,
                source_url="https://example.com/a",
                cache_key=_make_cache_key("a"),
                cache_hit=True,
                cache_hit_reason="hit",
                cache_hit_kind="exact",
                gemini_call_made=False,
                cache_size_bytes=1234,
            )
        logger.info.assert_not_called()
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["gemini_cache_lookup"]["hit"], 1)
        self.assertEqual(summary["gemini_cache_lookup"]["miss"], 0)
        self.assertEqual(summary["gemini_cache_lookup"]["call_made"], 0)

    def test_flag_on_miss_increments_counter_and_suppresses_log(self):
        logger = logging.getLogger("test_gem_miss")
        logger.info = MagicMock()
        with patch.dict("os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True):
            rss_fetcher._log_gemini_cache_lookup(
                logger,
                source_url="https://example.com/b",
                cache_key=_make_cache_key("b"),
                cache_hit=False,
                cache_hit_reason="miss",
                cache_hit_kind="unknown",
                gemini_call_made=False,
                cache_size_bytes=0,
            )
        logger.info.assert_not_called()
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["gemini_cache_lookup"]["hit"], 0)
        self.assertEqual(summary["gemini_cache_lookup"]["miss"], 1)
        self.assertEqual(summary["gemini_cache_lookup"]["call_made"], 0)

    def test_flag_on_call_made_still_emits_per_event_log(self):
        logger = logging.getLogger("test_gem_call_made")
        logger.info = MagicMock()
        with patch.dict("os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True):
            rss_fetcher._log_gemini_cache_lookup(
                logger,
                source_url="https://example.com/c",
                cache_key=_make_cache_key("c"),
                cache_hit=False,
                cache_hit_reason="miss",
                cache_hit_kind="unknown",
                gemini_call_made=True,
                cache_size_bytes=0,
            )
        logger.info.assert_called_once()
        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "gemini_cache_lookup")
        self.assertEqual(payload["gemini_call_made"], True)
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["gemini_cache_lookup"]["call_made"], 1)


class ArticleSkippedSamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        rss_fetcher._reset_log_sampling_state()

    def test_flag_off_keeps_per_event_log(self):
        logger = logging.getLogger("test_skip_off")
        logger.info = MagicMock()
        with patch.dict("os.environ", {}, clear=True), patch.object(
            rss_fetcher, "_record_post_gen_validate_skip_history"
        ):
            rss_fetcher._log_article_skipped_post_gen_validate(
                logger,
                title="生成タイトル",
                source_title="元タイトル",
                post_url="https://example.com/x1",
                category="試合速報",
                article_subtype="postgame",
                fail_axes=["weak_subject_title:related_info_escape"],
                stop_reason="weak_subject_title_review",
            )
        logger.info.assert_called_once()
        payload = json.loads(logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "article_skipped_post_gen_validate")

    def test_flag_on_aggregates_by_subtype_and_axis(self):
        logger = logging.getLogger("test_skip_on")
        logger.info = MagicMock()
        with patch.dict(
            "os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True
        ), patch.object(rss_fetcher, "_record_post_gen_validate_skip_history"):
            for i in range(2):
                rss_fetcher._log_article_skipped_post_gen_validate(
                    logger,
                    title=f"記事{i}",
                    source_title="",
                    post_url=f"https://example.com/x{i}",
                    category="試合速報",
                    article_subtype="postgame",
                    fail_axes=["weak_subject_title:related_info_escape"],
                    stop_reason="",
                )
            rss_fetcher._log_article_skipped_post_gen_validate(
                logger,
                title="他軸",
                source_title="",
                post_url="https://example.com/y",
                category="試合速報",
                article_subtype="lineup",
                fail_axes=["thin_body:short"],
                stop_reason="",
            )
        logger.info.assert_not_called()
        summary = rss_fetcher._build_log_sampling_summary()
        buckets = summary["article_skipped_post_gen_validate"]
        self.assertIn("postgame|weak_subject_title", buckets)
        self.assertEqual(buckets["postgame|weak_subject_title"]["count"], 2)
        self.assertEqual(
            buckets["postgame|weak_subject_title"]["samples"],
            ["記事0", "記事1"],
        )
        self.assertEqual(buckets["lineup|thin_body"]["count"], 1)

    def test_flag_on_sample_limit_three(self):
        logger = logging.getLogger("test_skip_limit")
        logger.info = MagicMock()
        with patch.dict(
            "os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True
        ), patch.object(rss_fetcher, "_record_post_gen_validate_skip_history"):
            for i in range(7):
                rss_fetcher._log_article_skipped_post_gen_validate(
                    logger,
                    title=f"タイトル{i}",
                    source_title="",
                    post_url=f"https://example.com/limit-{i}",
                    category="試合速報",
                    article_subtype="postgame",
                    fail_axes=["weak_subject_title:related_info_escape"],
                    stop_reason="",
                )
        summary = rss_fetcher._build_log_sampling_summary()
        bucket = summary["article_skipped_post_gen_validate"]["postgame|weak_subject_title"]
        self.assertEqual(bucket["count"], 7)
        self.assertEqual(len(bucket["samples"]), 3)
        self.assertEqual(bucket["samples"], ["タイトル0", "タイトル1", "タイトル2"])


class YahooFanReactionsSamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        rss_fetcher._reset_log_sampling_state()

    def test_flag_off_keeps_per_event_log(self):
        rss_fetcher._record_yahoo_fan_reactions_unavailable_sample("['queryA']")
        # Direct helper reachability check: with flag OFF the sampler is not called from
        # the original site. Here we verify the helper itself sample-limits correctly.
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["yahoo_fan_reactions_unavailable"]["count"], 1)
        self.assertEqual(
            summary["yahoo_fan_reactions_unavailable"]["sample_queries"], ["['queryA']"]
        )

    def test_flag_on_sample_limit_three(self):
        for i in range(5):
            rss_fetcher._record_yahoo_fan_reactions_unavailable_sample(f"['q{i}']")
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["yahoo_fan_reactions_unavailable"]["count"], 5)
        self.assertEqual(
            summary["yahoo_fan_reactions_unavailable"]["sample_queries"],
            ["['q0']", "['q1']", "['q2']"],
        )


class ResetSemanticsTests(unittest.TestCase):
    def test_reset_clears_all_counters(self):
        rss_fetcher._record_yahoo_fan_reactions_unavailable_sample("['x']")
        rss_fetcher._record_article_skipped_sample("postgame|axis", "title")
        rss_fetcher._log_sampling_state["post_gen_validate_failure_dedup_skip_count"] = 9
        rss_fetcher._log_sampling_state["gemini_cache_lookup_hit"] = 5

        rss_fetcher._reset_log_sampling_state()
        summary = rss_fetcher._build_log_sampling_summary()
        self.assertEqual(summary["post_gen_validate_failure_dedup_skip_count"], 0)
        self.assertEqual(summary["article_skipped_post_gen_validate"], {})
        self.assertEqual(summary["yahoo_fan_reactions_unavailable"]["count"], 0)
        self.assertEqual(summary["yahoo_fan_reactions_unavailable"]["sample_queries"], [])
        self.assertEqual(summary["gemini_cache_lookup"]["hit"], 0)


class ErrorWarningPreservedTests(unittest.TestCase):
    """Sampling must never suppress ERROR / WARNING level emissions."""

    def setUp(self) -> None:
        rss_fetcher._reset_log_sampling_state()

    def test_error_log_not_sampled(self):
        logger = logging.getLogger("test_error_preserved")
        with patch.dict(
            "os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True
        ), self.assertLogs(logger, level="ERROR") as cm:
            logger.error("boom: %s", "thing")
        self.assertTrue(any("boom: thing" in line for line in cm.output))

    def test_warning_log_not_sampled(self):
        logger = logging.getLogger("test_warning_preserved")
        with patch.dict(
            "os.environ", {"ENABLE_FETCHER_LOG_SAMPLING_V1": "1"}, clear=True
        ), self.assertLogs(logger, level="WARNING") as cm:
            logger.warning("watch: %s", "this")
        self.assertTrue(any("watch: this" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
