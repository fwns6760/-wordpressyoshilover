import unittest
from unittest.mock import patch

from src import rss_fetcher, x_post_generator


class CostModeTests(unittest.TestCase):
    def test_low_cost_article_categories_default_to_selected_subset(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertTrue(rss_fetcher.should_use_ai_for_category("試合速報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("選手情報"))
            self.assertTrue(rss_fetcher.should_use_ai_for_category("首脳陣"))
            self.assertFalse(rss_fetcher.should_use_ai_for_category("コラム"))

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

    def test_gemini_attempt_limits_default_to_one_in_low_cost_mode(self):
        with patch.dict("os.environ", {"LOW_COST_MODE": "1"}, clear=False):
            self.assertEqual(rss_fetcher.get_gemini_attempt_limit(strict_mode=True), 1)
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
