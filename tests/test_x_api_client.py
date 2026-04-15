import unittest
from unittest.mock import patch

from src import x_api_client


class XApiClientTests(unittest.TestCase):
    def test_select_primary_category_name_skips_auto_post_category(self):
        categories = [
            {"id": 673, "name": "自動投稿", "slug": "auto-post"},
            {"id": 5, "name": "試合速報", "slug": "game"},
        ]

        category = x_api_client.select_primary_category_name([673, 5], categories)

        self.assertEqual(category, "試合速報")

    def test_select_primary_category_name_falls_back_when_only_auto_category_exists(self):
        categories = [
            {"id": 673, "name": "自動投稿", "slug": "auto-post"},
        ]

        category = x_api_client.select_primary_category_name([673], categories)

        self.assertEqual(category, "自動投稿")

    def test_build_post_context_extracts_plain_summary_and_html(self):
        post = {
            "content": {
                "rendered": "<p>巨人が勝利</p><p>井上温大が好投</p>",
            }
        }

        summary, html = x_api_client.build_post_context(post)

        self.assertEqual(summary, "巨人が勝利 井上温大が好投")
        self.assertIn("<p>巨人が勝利</p>", html)

    def test_x_collect_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertFalse(x_api_client.x_collect_enabled())

    def test_x_collect_enabled_when_env_flag_is_set(self):
        with patch.dict("os.environ", {"ENABLE_X_COLLECT": "1"}, clear=False):
            self.assertTrue(x_api_client.x_collect_enabled())


if __name__ == "__main__":
    unittest.main()
