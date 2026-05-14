"""Tests for _maybe_apply_youtube_title_prefix (344-INGEST Phase 1a-7)."""

from __future__ import annotations

import unittest

from src import rss_fetcher


class YoutubeTitlePrefixTests(unittest.TestCase):
    def test_youtube_url_prefix_applied(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "上原浩治のWBC裏話",
            "https://www.youtube.com/watch?v=abc12345678",
        )
        self.assertEqual(result, "【YouTube】上原浩治のWBC裏話")

    def test_youtu_be_url_prefix_applied(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "巨人OB座談会",
            "https://youtu.be/xyz98765432",
        )
        self.assertEqual(result, "【YouTube】巨人OB座談会")

    def test_non_youtube_url_unchanged(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "巨人vsヤクルト",
            "https://hochi.news/articles/x.html",
        )
        self.assertEqual(result, "巨人vsヤクルト")

    def test_empty_title_unchanged(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "",
            "https://www.youtube.com/watch?v=abc",
        )
        self.assertEqual(result, "")

    def test_idempotent_when_prefix_already_present(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "【YouTube】既存 prefix 付き",
            "https://www.youtube.com/watch?v=abc",
        )
        self.assertEqual(result, "【YouTube】既存 prefix 付き")

    def test_empty_url_unchanged(self):
        result = rss_fetcher._maybe_apply_youtube_title_prefix(
            "巨人記事",
            "",
        )
        self.assertEqual(result, "巨人記事")


if __name__ == "__main__":
    unittest.main()
