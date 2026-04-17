import unittest
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
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

    def test_cmd_post_dry_run_skips_auto_post_category_and_passes_context_to_build_post(self):
        fake_post = {
            "title": {"rendered": "【巨人】今日のスタメン発表"},
            "link": "https://yoshilover.com/cmd-post-lineup",
            "content": {"rendered": "<p>巨人がスタメンを発表した。</p>"},
            "categories": [673, 5],
        }
        fake_categories = [
            {"id": 673, "name": "自動投稿", "slug": "auto-post"},
            {"id": 5, "name": "試合速報", "slug": "game"},
        ]
        args = SimpleNamespace(post_id=321, dry_run=True)

        with patch.object(x_api_client, "WPClient") as wp_mock:
            wp_mock.return_value.get_post.return_value = fake_post
            wp_mock.return_value.get_categories.return_value = fake_categories
            with patch.object(x_api_client, "build_post", return_value="tweet-text") as build_mock:
                with redirect_stdout(io.StringIO()):
                    x_api_client.cmd_post(args)

        args_called, kwargs_called = build_mock.call_args
        self.assertEqual(
            args_called[:3],
            ("【巨人】今日のスタメン発表", "https://yoshilover.com/cmd-post-lineup", "試合速報"),
        )
        self.assertEqual(kwargs_called["summary"], "巨人がスタメンを発表した。")
        self.assertEqual(kwargs_called["content_html"], "<p>巨人がスタメンを発表した。</p>")

    def test_cmd_post_dry_run_uses_build_post_fallback_for_notice_like_post(self):
        fake_post = {
            "title": {"rendered": "【巨人】浅野翔吾が出場選手登録"},
            "link": "https://yoshilover.com/cmd-post-notice",
            "content": {"rendered": "<p>公示で浅野翔吾外野手の出場選手登録が発表された。</p>"},
            "categories": [8],
        }
        fake_categories = [
            {"id": 8, "name": "選手情報", "slug": "player"},
        ]
        args = SimpleNamespace(post_id=654, dry_run=True)

        with patch.object(x_api_client, "WPClient") as wp_mock:
            wp_mock.return_value.get_post.return_value = fake_post
            wp_mock.return_value.get_categories.return_value = fake_categories
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                x_api_client.cmd_post(args)

        output = stdout.getvalue()
        self.assertIn("浅野翔吾が一軍登録。", output)
        self.assertIn("ここから出番が増えるかも気になります。", output)
        self.assertIn("この動き、どう見ますか？", output)


if __name__ == "__main__":
    unittest.main()
