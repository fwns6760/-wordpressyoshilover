import logging
import unittest
from unittest.mock import MagicMock, patch

from src import rss_fetcher


HOCHI_TWEET_URL = "https://twitter.com/hochi_giants/status/2051037501184167955"
HOCHI_ARTICLE_URL = "https://hochi.news/articles/20260504-OHT1T51001.html"
SOURCE_NAME = "スポーツ報知巨人班X"


class FetcherFanImportantNarrowExemptTests(unittest.TestCase):
    def _logger(self) -> logging.Logger:
        logger = logging.getLogger("test_rss_fetcher_fan_important_narrow_exempt")
        logger.info = MagicMock()
        logger.warning = MagicMock()
        return logger

    def _context(self, skip_kind: str, **post_meta):
        return rss_fetcher._fetcher_fan_important_narrow_exempt_context(
            skip_kind=skip_kind,
            post_meta=post_meta,
            source_url=post_meta.get("source_url", HOCHI_TWEET_URL),
            title=post_meta.get("title", ""),
            validation=post_meta.get("validation"),
        )

    def test_social_too_weak_allows_priority_source_player_return_story(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "social_too_weak",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境",
                summary="泉口友汰が負傷離脱中の心境を明かし、1軍合流へ備えている。",
                category="選手情報",
                article_subtype="player",
                title="あえて巨人戦はチェックせず 泉口友汰が明かした負傷離脱中の心境",
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["reason"], "priority_source_or_keyword_social")
        self.assertIn("泉口友汰", context["keyword_hits"])

    def test_comment_required_allows_priority_source_without_quote_for_togo(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "comment_required",
                source_name="スポーツ報知",
                source_title="【巨人】戸郷翔征が4日ヤクルト戦で今季初登板",
                summary="戸郷翔征が4日ヤクルト戦で今季初登板へ向けて調整した。",
                category="選手情報",
                article_subtype="player",
                title="【巨人】戸郷翔征が4日ヤクルト戦で今季初登板",
                source_url=HOCHI_ARTICLE_URL,
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["reason"], "priority_source_commentless_news")

    def test_live_update_disabled_allows_emergency_relief(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "live_update_disabled",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="【巨人】松浦慶斗が初回から緊急リリーフ",
                summary="松浦慶斗が初回から緊急リリーフ。先発・山崎伊織が2球で交代した。",
                category="試合速報",
                article_subtype="live_update",
                title="【巨人】松浦慶斗が初回から緊急リリーフ",
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["reason"], "urgent_live_update")

    def test_pregame_started_allows_manager_comment_about_first_team_return(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "pregame_started",
                source_name="スポーツ報知",
                source_title="【巨人】阿部監督が泉口友汰の1軍合流を説明",
                summary="阿部監督が泉口友汰の1軍合流について試合前にコメントした。",
                category="首脳陣",
                article_subtype="pregame",
                title="【巨人】阿部監督が泉口友汰の1軍合流を説明",
                source_url=HOCHI_ARTICLE_URL,
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["reason"], "injury_return_or_manager_comment_after_start")

    def test_body_contract_reroll_is_allowlisted_but_fail_is_not(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            reroll_context = self._context(
                "body_contract_validate",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="巨人・戸郷翔征「ゼロにこだわりたい」",
                summary="戸郷翔征が今季初登板へ向けて意気込みを語った。",
                category="選手情報",
                article_subtype="player",
                title="戸郷翔征 今季初登板 発言ポイント",
                validation={"ok": False, "action": "reroll", "fail_axes": ["first_block_mismatch"]},
            )
            fail_context = self._context(
                "body_contract_validate",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="巨人・戸郷翔征「ゼロにこだわりたい」",
                summary="戸郷翔征が今季初登板へ向けて意気込みを語った。",
                category="選手情報",
                article_subtype="player",
                title="戸郷翔征 今季初登板 発言ポイント",
                validation={"ok": False, "action": "fail", "fail_axes": ["source_block_missing"]},
            )

        self.assertIsNotNone(reroll_context)
        self.assertEqual(reroll_context["reason"], "body_contract_reroll_only")
        self.assertIsNone(fail_context)

    def test_post_gen_close_marker_only_is_allowlisted(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "post_gen_validate",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="巨人・戸郷翔征「ゼロにこだわりたい」",
                summary="戸郷翔征が今季初登板へ向けて意気込みを語った。",
                category="選手情報",
                article_subtype="player",
                title="戸郷翔征 今季初登板 発言ポイント",
                validation={"ok": False, "fail_axes": ["close_marker"], "stop_reason": "close_marker"},
            )

        self.assertIsNotNone(context)
        self.assertEqual(context["reason"], "post_gen_close_marker_only")

    def test_post_gen_multi_axis_and_history_duplicate_are_not_allowlisted(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            multi_axis = self._context(
                "post_gen_validate",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="巨人・戸郷翔征「ゼロにこだわりたい」",
                summary="戸郷翔征が今季初登板へ向けて意気込みを語った。",
                category="選手情報",
                article_subtype="player",
                title="戸郷翔征 今季初登板 発言ポイント",
                validation={"ok": False, "fail_axes": ["close_marker", "intro_echo"], "stop_reason": "close_marker"},
            )
            duplicate = self._context(
                "history_duplicate",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="【巨人】泉口友汰が1軍合流",
                summary="泉口友汰が1軍合流した。",
                category="選手情報",
                article_subtype="player",
                title="【巨人】泉口友汰が1軍合流",
            )

        self.assertIsNone(multi_axis)
        self.assertIsNone(duplicate)

    def test_weak_title_routes_are_exempt_only_with_new_flag(self):
        logger = self._logger()
        kwargs = {
            "article_subtype": "player",
            "rewritten_title": "戸郷翔征 今季初登板 発言ポイント",
            "original_title": "【巨人】戸郷翔征「ゼロにこだわりたい」4日ヤクルト戦で今季初登板",
            "source_name": SOURCE_NAME,
            "source_url": HOCHI_TWEET_URL,
            "source_title": "【巨人】戸郷翔征「ゼロにこだわりたい」4日ヤクルト戦で今季初登板",
            "source_body": "戸郷翔征が今季初登板へ向けて意気込みを語った。",
            "summary": "戸郷翔征が今季初登板へ向けて意気込みを語った。",
            "metadata": {"category": "選手情報", "article_subtype": "player", "player_name": "戸郷翔征"},
            "logger": logger,
        }

        with patch.dict("os.environ", {}, clear=False):
            fallback_off = rss_fetcher._maybe_route_weak_generated_title_review(**kwargs)
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            fallback_on = rss_fetcher._maybe_route_weak_generated_title_review(**kwargs)

        self.assertIsInstance(fallback_off, rss_fetcher._WeakTitleReviewFallback)
        self.assertIsNone(fallback_on)

    def test_hard_stop_obituary_never_unlocks(self):
        with patch.dict("os.environ", {rss_fetcher.FETCHER_FAN_IMPORTANT_NARROW_EXEMPT_ENV_FLAG: "1"}, clear=False):
            context = self._context(
                "social_too_weak",
                source_name=SOURCE_NAME,
                source_handle="@hochi_giants",
                source_title="元巨人OBの訃報",
                summary="元巨人OBの訃報が伝えられた。",
                category="コラム",
                article_subtype="general",
                title="元巨人OBの訃報",
            )

        self.assertIsNone(context)


if __name__ == "__main__":
    unittest.main()
