"""Tests for rss_fetcher YouTube integration helpers (344-INGEST Phase 1a-4)."""

from __future__ import annotations

import unittest

from src import rss_fetcher


class IsYoutubePostUrlTests(unittest.TestCase):
    def test_youtube_com_watch_true(self):
        self.assertTrue(
            rss_fetcher._is_youtube_post_url("https://www.youtube.com/watch?v=abc123")
        )

    def test_youtube_com_channel_true(self):
        self.assertTrue(
            rss_fetcher._is_youtube_post_url("https://www.youtube.com/channel/UCxxxx")
        )

    def test_youtu_be_short_true(self):
        self.assertTrue(rss_fetcher._is_youtube_post_url("https://youtu.be/abc123"))

    def test_x_url_false(self):
        self.assertFalse(
            rss_fetcher._is_youtube_post_url("https://x.com/hochi_giants/status/123")
        )

    def test_news_url_false(self):
        self.assertFalse(
            rss_fetcher._is_youtube_post_url("https://hochi.news/articles/x.html")
        )

    def test_empty_safe(self):
        self.assertFalse(rss_fetcher._is_youtube_post_url(""))
        self.assertFalse(rss_fetcher._is_youtube_post_url(None))


class CheckYoutubeGiantsFilterTests(unittest.TestCase):
    def test_giants_keyword_passes(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter("巨人vsヤクルト振り返り")
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_keyword")

    def test_active_player_passes(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter("坂本勇人300号を語る")
        self.assertTrue(ok)
        self.assertIn(reason, ("giants_keyword", "giants_player"))

    def test_ob_passes(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter("上原浩治のWBC裏話")
        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob")

    def test_unrelated_skipped(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter("メジャー大谷翔平総決算")
        self.assertFalse(ok)
        self.assertEqual(reason, "no_match")

    def test_empty_input_safe(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter("")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
