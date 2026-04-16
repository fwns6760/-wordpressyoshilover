import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import rss_fetcher, x_post_generator


class CostModeTests(unittest.TestCase):
    def test_low_cost_article_categories_default_to_selected_subset(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertTrue(rss_fetcher.should_use_ai_for_category("試合速報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("選手情報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("首脳陣"))
            self.assertFalse(rss_fetcher.should_use_ai_for_category("コラム"))

    def test_notice_like_column_routes_to_player_ai_category(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            use_ai, effective_category, reason = rss_fetcher._resolve_article_ai_strategy(
                "コラム",
                "【巨人】皆川岳飛が初１軍合流「やってやろうという気持ち」",
                "皆川岳飛が初１軍合流となり、試合前に抱負を語った。",
                has_game=False,
                article_subtype="general",
            )
            self.assertTrue(use_ai)
            self.assertEqual(effective_category, "選手情報")
            self.assertEqual(reason, "player_notice_route")

    def test_farm_articles_can_use_ai_even_when_category_is_not_enabled(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,選手情報,首脳陣"}, clear=False):
            use_ai, effective_category, reason = rss_fetcher._resolve_article_ai_strategy(
                "ドラフト・育成",
                "【二軍】巨人 3-1 ハヤテ（5回降雨コールド）",
                "巨人が3-1で勝利し、若手が本塁打を放った。",
                has_game=False,
                article_subtype="farm",
            )
            self.assertTrue(use_ai)
            self.assertEqual(effective_category, "ドラフト・育成")
            self.assertEqual(reason, "farm_article_route")

    def test_player_status_accepts_shorter_strict_output(self):
        self.assertEqual(
            rss_fetcher._get_gemini_strict_min_chars(
                "選手情報",
                "【巨人】中山礼都が登録抹消",
                "中山礼都が出場選手登録を抹消された。",
            ),
            160,
        )
        self.assertEqual(
            rss_fetcher._get_gemini_strict_min_chars(
                "選手情報",
                "【巨人】田中将大「打線を線にしない」",
                "田中将大が阪神戦前にコメントした。",
            ),
            220,
        )

    def test_article_categories_can_be_overridden(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "AI_ENABLED_CATEGORIES": "試合速報,補強・移籍"}, clear=False):
            self.assertTrue(rss_fetcher.should_use_ai_for_category("補強・移籍"))
            self.assertFalse(rss_fetcher.should_use_ai_for_category("選手情報"))

    def test_low_cost_x_post_ai_defaults_to_off(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertEqual(x_post_generator.get_x_post_ai_mode(), "none")
            self.assertTrue(x_post_generator.should_use_ai_for_x_post("試合速報"))
            self.assertFalse(x_post_generator.should_use_ai_for_x_post("コラム"))

    def test_x_post_ai_mode_can_be_enabled_for_selected_categories(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "X_POST_AI_MODE": "gemini", "X_POST_AI_CATEGORIES": "試合速報,首脳陣"}, clear=False):
            self.assertEqual(x_post_generator.get_x_post_ai_mode(), "gemini")
            self.assertTrue(x_post_generator.should_use_ai_for_x_post("首脳陣"))
            self.assertFalse(x_post_generator.should_use_ai_for_x_post("選手情報"))

    def test_auto_tweet_categories_default_to_selected_subset(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertTrue("試合速報" in rss_fetcher.get_auto_tweet_categories())
            self.assertTrue("首脳陣" in rss_fetcher.get_auto_tweet_categories())
            self.assertTrue("ドラフト・育成" in rss_fetcher.get_auto_tweet_categories())
            self.assertFalse("コラム" in rss_fetcher.get_auto_tweet_categories())

    def test_auto_tweet_skip_reasons_explain_disabled_state(self):
        with patch.dict("os.environ", {"AUTO_TWEET_ENABLED": "0"}, clear=False):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="news",
                category="試合速報",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, ["auto_tweet_disabled"])

    def test_auto_tweet_accepts_social_news_when_enabled(self):
        with patch.dict("os.environ", {"AUTO_TWEET_ENABLED": "1", "AUTO_TWEET_CATEGORIES": "ドラフト・育成"}, clear=False):
            reasons = rss_fetcher.get_auto_tweet_skip_reasons(
                source_type="social_news",
                category="ドラフト・育成",
                draft_only=False,
                x_post_count=0,
                x_post_daily_limit=5,
                featured_media=123,
                published=True,
                article_url="https://yoshilover.com/1",
            )
            self.assertEqual(reasons, [])

    def test_gemini_cli_for_x_post_defaults_to_off(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertFalse(x_post_generator.allow_gemini_cli_for_x_post())

    def test_gemini_cli_for_x_post_can_be_opted_in(self):
        with patch.dict("os.environ", {"X_POST_GEMINI_ALLOW_CLI": "1"}, clear=False):
            self.assertTrue(x_post_generator.allow_gemini_cli_for_x_post())

    def test_article_ai_mode_can_be_overridden_for_this_run(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1", "ARTICLE_AI_MODE": "gemini", "OFFDAY_ARTICLE_AI_MODE": "none"}, clear=False):
            self.assertEqual(rss_fetcher.get_article_ai_mode(True, override="grok"), "grok")
            self.assertEqual(rss_fetcher.get_article_ai_mode(False, override="grok"), "grok")

    def test_offday_article_ai_mode_defaults_to_gemini_in_low_cost_mode(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=True):
            self.assertEqual(rss_fetcher.get_article_ai_mode(False), "gemini")

    def test_stale_player_status_entry_is_skipped_after_24_hours(self):
        old_dt = datetime.now(timezone.utc) - timedelta(hours=25)
        self.assertTrue(
            rss_fetcher._should_skip_stale_player_status_entry(
                "選手情報",
                "【巨人】佐々木俊輔が登録抹消",
                "佐々木俊輔外野手が出場選手登録を抹消された。",
                old_dt,
            )
        )
        fresh_dt = datetime.now(timezone.utc) - timedelta(hours=2)
        self.assertFalse(
            rss_fetcher._should_skip_stale_player_status_entry(
                "選手情報",
                "【巨人】佐々木俊輔が登録抹消",
                "佐々木俊輔外野手が出場選手登録を抹消された。",
                fresh_dt,
            )
        )

    def test_yesterdays_postgame_entry_is_skipped(self):
        yesterday_local = datetime.now().astimezone() - timedelta(hours=12)
        if yesterday_local.date() == datetime.now().astimezone().date():
            yesterday_local = yesterday_local - timedelta(days=1)
        self.assertTrue(
            rss_fetcher._should_skip_stale_postgame_entry(
                "試合速報",
                "巨人4-0勝利",
                "松本剛が決勝打で巨人が4-0で勝利した。",
                yesterday_local.astimezone(timezone.utc),
            )
        )

    def test_todays_postgame_entry_is_not_skipped(self):
        fresh_dt = datetime.now(timezone.utc) - timedelta(hours=2)
        self.assertFalse(
            rss_fetcher._should_skip_stale_postgame_entry(
                "試合速報",
                "巨人4-0勝利",
                "松本剛が決勝打で巨人が4-0で勝利した。",
                fresh_dt,
            )
        )

    def test_gemini_attempt_limits_default_to_three_in_low_cost_mode(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=True), 3)
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=False), 1)

    def test_gemini_attempt_limits_can_be_overridden(self):
        with patch.dict(
            "os.environ",
            {"LOW_COST_MODE": "1", "GEMINI_STRICT_MAX_ATTEMPTS": "2", "GEMINI_GROUNDED_MAX_ATTEMPTS": "2"},
            clear=False,
        ):
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=True), 2)
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=False), 2)


if __name__ == "__main__":
    unittest.main()
