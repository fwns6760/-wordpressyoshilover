"""Tests for _maybe_append_youtube_caption_section + _extract_youtube_video_id (344-INGEST Phase 1a-6)."""

from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from src import rss_fetcher


class ExtractYoutubeVideoIdTests(unittest.TestCase):
    def test_youtube_watch_url(self):
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id(
                "https://www.youtube.com/watch?v=abc12345678"
            ),
            "abc12345678",
        )

    def test_youtu_be_short(self):
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id("https://youtu.be/xyz98765432"),
            "xyz98765432",
        )

    def test_shorts_url(self):
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id(
                "https://www.youtube.com/shorts/short_id_111"
            ),
            "short_id_111",
        )

    def test_embed_url(self):
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id(
                "https://www.youtube.com/embed/embed_id_222"
            ),
            "embed_id_222",
        )

    def test_non_youtube_returns_empty(self):
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id("https://example.com/x"), ""
        )
        self.assertEqual(rss_fetcher._extract_youtube_video_id(""), "")

    def test_youtube_channel_url_returns_empty(self):
        # channel URL は video_id 抽出対象外 (nullable で空文字 fallback)
        self.assertEqual(
            rss_fetcher._extract_youtube_video_id("https://www.youtube.com/channel/UCxxxx"),
            "",
        )


class MaybeAppendYoutubeCaptionSectionTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")

    def test_non_youtube_url_unchanged(self):
        html = "<p>既存本文</p>"
        result = rss_fetcher._maybe_append_youtube_caption_section(
            html,
            source_url="https://hochi.news/articles/x.html",
            source_name="報知",
            logger=self.logger,
        )
        self.assertEqual(result, html)

    def test_idempotent_when_marker_present(self):
        html = '<p>既存</p><aside class="nomotoke-youtube-caption">...</aside>'
        result = rss_fetcher._maybe_append_youtube_caption_section(
            html,
            source_url="https://www.youtube.com/watch?v=abc12345678",
            source_name="巨人公式",
            logger=self.logger,
        )
        self.assertEqual(result, html)

    def test_no_video_id_returns_unchanged(self):
        html = "<p>本文</p>"
        result = rss_fetcher._maybe_append_youtube_caption_section(
            html,
            source_url="https://www.youtube.com/channel/UCxxxx",
            source_name="巨人公式",
            logger=self.logger,
        )
        self.assertEqual(result, html)

    def test_caption_fetched_appends_section(self):
        html = "<p>既存本文</p>"
        with patch(
            "src.youtube_caption_fetcher.fetch_youtube_caption",
            return_value="巨人・坂本勇人が逆転サヨナラ３ラン。「一生忘れない」と語った。",
        ):
            result = rss_fetcher._maybe_append_youtube_caption_section(
                html,
                source_url="https://www.youtube.com/watch?v=abc12345678",
                source_name="巨人公式",
                logger=self.logger,
            )
        self.assertIn("nomotoke-youtube-caption", result)
        self.assertIn("📺 字幕抜粋", result)
        self.assertIn("巨人・坂本勇人", result)
        self.assertIn("巨人公式", result)
        self.assertIn("youtube.com/embed/abc12345678", result)
        self.assertIn("引用法 32 条範囲内", result)

    def test_no_caption_returns_unchanged(self):
        html = "<p>既存</p>"
        with patch(
            "src.youtube_caption_fetcher.fetch_youtube_caption", return_value=""
        ):
            result = rss_fetcher._maybe_append_youtube_caption_section(
                html,
                source_url="https://www.youtube.com/watch?v=abc12345678",
                source_name="巨人公式",
                logger=self.logger,
            )
        self.assertEqual(result, html)

    def test_caption_fetch_exception_returns_unchanged(self):
        html = "<p>既存</p>"
        with patch(
            "src.youtube_caption_fetcher.fetch_youtube_caption",
            side_effect=RuntimeError("network"),
        ):
            result = rss_fetcher._maybe_append_youtube_caption_section(
                html,
                source_url="https://www.youtube.com/watch?v=abc12345678",
                source_name="巨人公式",
                logger=self.logger,
            )
        self.assertEqual(result, html)

    def test_html_escapes_caption(self):
        html = "<p>本文</p>"
        with patch(
            "src.youtube_caption_fetcher.fetch_youtube_caption",
            return_value="<script>alert(1)</script>巨人本文長め説明文ABCDEFGH",
        ):
            result = rss_fetcher._maybe_append_youtube_caption_section(
                html,
                source_url="https://www.youtube.com/watch?v=abc12345678",
                source_name="巨人公式",
                logger=self.logger,
            )
        self.assertNotIn("<script>alert", result)
        self.assertIn("&lt;script&gt;", result)


if __name__ == "__main__":
    unittest.main()
