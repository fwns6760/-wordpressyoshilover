"""Tests for COST-PGV-001 — pre-stage post_gen_validate fail history record at
review-confirmed skip sites (default OFF flag ENABLE_PRE_POST_GEN_VALIDATE_SKIP).

Required fixtures:
1. review系failで fail history が書かれる
2. 次cycleで同一source_url/status_idが early skip される
3. x_short_player候補は止めない
4. player/pitcher comment候補は止めない
5. source_link_only候補は止めない
6. flag OFFで既存挙動(emit helper called only when flag ON)
7. TTL切れ後は再評価される
8. Gemini callは増えない(review済みパスは元から Gemini を呼ばない)
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from src import rss_fetcher


# ─────────────────────────────────────────────
# Fixture 1, 6: helper writes ledger only when flag ON
# ─────────────────────────────────────────────
class HelperLedgerWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        rss_fetcher._reset_log_sampling_state()

    def test_emit_helper_writes_history_for_routing_v2_review(self):
        history: dict = {}
        item = {"entry_title_norm": "test_title_norm_value"}
        with patch.object(rss_fetcher, "persist_history") as persist_mock:
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://example.com/post-1",
                item=item,
                fail_axes=["routing_v2_review"],
                sample_title="サンプル記事",
            )

        url_key = f"{rss_fetcher.POST_GEN_VALIDATE_FAILURE_KEY_PREFIX}url:https://example.com/post-1"
        self.assertIn(url_key, history)
        self.assertEqual(history[url_key]["fail_axes"], ["routing_v2_review"])
        persist_mock.assert_called_once_with(history)

    def test_emit_helper_extracts_x_status_id(self):
        history: dict = {}
        item = {"entry_title_norm": "x_post_title_norm"}
        with patch.object(rss_fetcher, "persist_history"):
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://twitter.com/TokyoGiants/status/2051932442643296604",
                item=item,
                fail_axes=["postgame_strict_review"],
                sample_title="【試合終了】巨人 0-5 ヤクルト",
            )

        status_key = f"{rss_fetcher.POST_GEN_VALIDATE_FAILURE_KEY_PREFIX}status:2051932442643296604"
        self.assertIn(status_key, history)
        self.assertEqual(history[status_key]["x_status_id"], "2051932442643296604")

    def test_emit_helper_records_sample_with_bucket_key(self):
        history: dict = {}
        item = {"entry_title_norm": "weak_t"}
        with patch.object(rss_fetcher, "persist_history"):
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://example.com/wt-1",
                item=item,
                fail_axes=["weak_generated_title:title_too_short"],
                sample_title="監督「一度抹消する」",
            )
        summary = rss_fetcher._build_log_sampling_summary()
        section = summary["pre_post_gen_validate_skip"]
        self.assertEqual(section["count"], 1)
        self.assertIn("weak_generated_title", section["buckets"])
        self.assertEqual(section["buckets"]["weak_generated_title"]["count"], 1)
        self.assertEqual(
            section["buckets"]["weak_generated_title"]["samples"], ["監督「一度抹消する」"]
        )

    def test_emit_helper_sample_limit_three(self):
        history: dict = {}
        item = {"entry_title_norm": "x"}
        with patch.object(rss_fetcher, "persist_history"):
            for i in range(7):
                rss_fetcher._emit_pre_post_gen_validate_skip(
                    history,
                    post_url=f"https://example.com/p-{i}",
                    item=item,
                    fail_axes=["routing_v2_review"],
                    sample_title=f"記事{i}",
                )
        summary = rss_fetcher._build_log_sampling_summary()
        bucket = summary["pre_post_gen_validate_skip"]["buckets"]["routing_v2_review"]
        self.assertEqual(bucket["count"], 7)
        self.assertEqual(len(bucket["samples"]), 3)
        self.assertEqual(bucket["samples"], ["記事0", "記事1", "記事2"])


# ─────────────────────────────────────────────
# Fixture 2, 7: TTL behavior — same URL/status next cycle, expiry re-evaluates
# ─────────────────────────────────────────────
class LedgerTTLBehaviorTests(unittest.TestCase):
    def test_same_source_url_within_ttl_is_recent(self):
        history: dict = {}
        item = {"entry_title_norm": "norm-x"}
        with patch.object(rss_fetcher, "persist_history"):
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://example.com/dup-1",
                item=item,
                fail_axes=["routing_v2_review"],
                sample_title="dup1",
            )
        is_recent, kind = rss_fetcher._is_post_gen_validate_failure_recent(
            history,
            post_url="https://example.com/dup-1",
            x_status_id="",
            entry_title_norm="norm-x",
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "url")

    def test_same_x_status_id_within_ttl_is_recent(self):
        history: dict = {}
        item = {"entry_title_norm": "x_norm"}
        with patch.object(rss_fetcher, "persist_history"):
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://twitter.com/foo/status/9999999999",
                item=item,
                fail_axes=["postgame_strict_review"],
                sample_title="【試合終了】",
            )
        is_recent, kind = rss_fetcher._is_post_gen_validate_failure_recent(
            history,
            post_url="https://twitter.com/foo/status/9999999999",
            x_status_id="9999999999",
            entry_title_norm="x_norm",
        )
        self.assertTrue(is_recent)
        self.assertIn(kind, {"status", "url"})

    def test_ttl_expired_no_longer_recent(self):
        history: dict = {}
        item = {"entry_title_norm": "expired-x"}
        with patch.object(rss_fetcher, "persist_history"):
            rss_fetcher._emit_pre_post_gen_validate_skip(
                history,
                post_url="https://example.com/expired-1",
                item=item,
                fail_axes=["routing_v2_review"],
                sample_title="exp",
            )
        # Backdate every entry to 25h ago
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        for key, payload in list(history.items()):
            if isinstance(payload, dict) and key.startswith(
                rss_fetcher.POST_GEN_VALIDATE_FAILURE_KEY_PREFIX
            ):
                payload["timestamp"] = old_ts
        is_recent, kind = rss_fetcher._is_post_gen_validate_failure_recent(
            history,
            post_url="https://example.com/expired-1",
            x_status_id="",
            entry_title_norm="expired-x",
        )
        self.assertFalse(is_recent)
        self.assertEqual(kind, "")


# ─────────────────────────────────────────────
# Fixture 6: flag OFF default behavior preserved
# ─────────────────────────────────────────────
class FlagGateTests(unittest.TestCase):
    def test_flag_off_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(rss_fetcher._pre_post_gen_validate_skip_enabled())

    def test_flag_on_recognized(self):
        with patch.dict(
            "os.environ", {"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"}, clear=True
        ):
            self.assertTrue(rss_fetcher._pre_post_gen_validate_skip_enabled())


# ─────────────────────────────────────────────
# Fixture 3, 4, 5, 8: subtype safety + Gemini call count via _main run
# ─────────────────────────────────────────────
class MainLoopSubtypeSafetyTests(unittest.TestCase):
    """Run rss_fetcher._main with items whose subtype must NOT be stopped by
    COST-PGV-001 (x_short_player / player_comment / pitcher_comment /
    source_link_only). Assert _emit_pre_post_gen_validate_skip is not called.

    We also confirm Gemini text generation hook is not invoked any more times
    than the existing baseline — flag ON should not increase Gemini call count.
    """

    def _run_main_with_subtype(self, *, subtype: str, env: dict[str, str] | None = None):
        env = env or {}
        entry = {
            "title": "巨人・坂本選手「打席で集中していた」コメント全文",
            "summary": "坂本勇人 安打 試合速報のコメント",
            "link": "https://hochi.news/articles/2026/05/06/safety-test.html",
        }
        args = Namespace(
            dry_run=True, draft_only=False, limit=10, article_ai_mode=None
        )
        emit_mock = MagicMock()
        gemini_mock = MagicMock(return_value="本文サンプル")

        with tempfile.TemporaryDirectory() as tmpdir, ExitStack() as stack:
            tmpdir_path = Path(tmpdir)
            sources_file = tmpdir_path / "rss_sources.json"
            keywords_file = tmpdir_path / "keywords.json"
            sources_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "テストソース",
                            "url": "https://feed.example.com/rss.xml",
                            "type": "news",
                            "role": ["article_source"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            keywords_file.write_text(
                json.dumps({"選手情報": ["巨人"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            stack.enter_context(patch.dict("os.environ", env, clear=False))
            stack.enter_context(
                patch.object(rss_fetcher, "RSS_SOURCES_FILE", sources_file)
            )
            stack.enter_context(
                patch.object(rss_fetcher, "KEYWORDS_FILE", keywords_file)
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "check_giants_game_today",
                    return_value=(False, "", ""),
                )
            )
            stack.enter_context(
                patch.object(rss_fetcher, "load_history", return_value={})
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher.feedparser,
                    "parse",
                    return_value=SimpleNamespace(entries=[entry]),
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_entry_published_datetime",
                    return_value=datetime(2026, 5, 6, 12, 0, 0),
                )
            )
            stack.enter_context(
                patch.object(rss_fetcher, "_entry_day_key", return_value="2026-05-06")
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher, "_aggregate_lineup_candidates", side_effect=lambda items: items
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher, "_should_skip_stale_postgame_entry", return_value=False
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_should_skip_stale_player_status_entry",
                    return_value=False,
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher, "_is_promotional_video_entry", return_value=False
                )
            )
            stack.enter_context(
                patch.object(rss_fetcher, "_detect_article_subtype", return_value=subtype)
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_source_fact_block_metrics",
                    return_value=("x" * 200, 200),
                )
            )
            stack.enter_context(
                patch.object(rss_fetcher, "_is_thin_source_fact_block", return_value=False)
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_rewrite_display_title_with_template",
                    return_value=(
                        "巨人・坂本選手 安打を放ち集中力を発揮 試合で活躍",
                        "subtype_safety_test",
                    ),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_log_title_template_selected"))
            stack.enter_context(
                patch.object(
                    rss_fetcher, "_emit_pre_post_gen_validate_skip", emit_mock
                )
            )
            stack.enter_context(
                patch.object(
                    rss_fetcher, "_request_gemini_strict_text", gemini_mock
                )
            )

            rss_fetcher._main(args, logging.getLogger("rss_fetcher_test"))

        return emit_mock, gemini_mock

    def test_x_short_player_subtype_not_stopped(self):
        emit_mock, _gemini = self._run_main_with_subtype(
            subtype="x_short_player",
            env={"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"},
        )
        emit_mock.assert_not_called()

    def test_player_subtype_not_stopped(self):
        emit_mock, _gemini = self._run_main_with_subtype(
            subtype="player",
            env={"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"},
        )
        emit_mock.assert_not_called()

    def test_pitcher_comment_subtype_not_stopped(self):
        emit_mock, _gemini = self._run_main_with_subtype(
            subtype="pitcher_comment",
            env={"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"},
        )
        emit_mock.assert_not_called()

    def test_source_link_only_subtype_not_stopped(self):
        emit_mock, _gemini = self._run_main_with_subtype(
            subtype="source_link_only",
            env={"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"},
        )
        emit_mock.assert_not_called()

    def test_gemini_call_count_not_increased_by_flag_on(self):
        # Run once with flag OFF, once with flag ON. Flag should never
        # cause additional Gemini text-generation calls.
        emit_off, gemini_off = self._run_main_with_subtype(
            subtype="player_comment", env={}
        )
        emit_on, gemini_on = self._run_main_with_subtype(
            subtype="player_comment",
            env={"ENABLE_PRE_POST_GEN_VALIDATE_SKIP": "1"},
        )
        self.assertLessEqual(gemini_on.call_count, gemini_off.call_count)
        # Flag OFF must have zero emit calls regardless.
        emit_off.assert_not_called()


if __name__ == "__main__":
    unittest.main()
