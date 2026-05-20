"""Tests for rss_fetcher YouTube integration helpers (344-INGEST Phase 1a-4)."""

from __future__ import annotations

import logging
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

    def test_official_source_role_passes_even_without_title_keyword(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter_for_source(
            "小林の肩 vs 朝井の声",
            source_roles={"media_quote_only", "official_video_source"},
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "official_video_source")

    def test_non_official_source_role_still_uses_title_filter(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter_for_source(
            "メジャー大谷総決算",
            source_roles={"media_quote_only", "youtube_review_source"},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "no_match")

    def test_giants_ob_source_role_passes_for_draft_review_even_with_weak_title(self):
        ok, reason = rss_fetcher._check_youtube_giants_filter_for_source(
            "あの場面の配球を語る",
            source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
        )

        self.assertTrue(ok)
        self.assertEqual(reason, "giants_ob_source")


class YoutubeReviewDraftSourceTests(unittest.TestCase):
    def test_giants_ob_youtube_review_source_is_forced_to_draft(self):
        self.assertTrue(
            rss_fetcher._is_youtube_review_draft_source(
                source_type="tag_scrape",
                source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
                source_url="https://www.youtube.com/watch?v=abc12345DEF",
            )
        )

    def test_official_youtube_source_keeps_existing_publish_path(self):
        self.assertFalse(
            rss_fetcher._is_youtube_review_draft_source(
                source_type="tag_scrape",
                source_roles={"media_quote_only", "official_video_source", "review_only"},
                source_url="https://www.youtube.com/watch?v=abc12345DEF",
            )
        )

    def test_non_youtube_review_source_not_forced_to_draft(self):
        self.assertFalse(
            rss_fetcher._is_youtube_review_draft_source(
                source_type="tag_scrape",
                source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
                source_url="https://example.com/video",
            )
        )

    def test_giants_ob_youtube_category_routes_to_ob_commentary(self):
        category = rss_fetcher._youtube_review_category_override(
            "コラム",
            source_type="tag_scrape",
            source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
            source_url="https://www.youtube.com/watch?v=abc12345DEF",
        )

        self.assertEqual(category, "OB・解説者")

    def test_giants_ob_youtube_publish_reasons_force_draft_and_history_persistence(self):
        reasons = rss_fetcher._apply_youtube_review_draft_skip_reasons(
            [],
            source_type="tag_scrape",
            source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
            source_url="https://www.youtube.com/watch?v=abc12345DEF",
        )

        self.assertEqual(reasons, ["draft_only", "youtube_review_source_draft_only"])

    def test_official_youtube_publish_reasons_are_not_forced_to_draft(self):
        reasons = rss_fetcher._apply_youtube_review_draft_skip_reasons(
            [],
            source_type="tag_scrape",
            source_roles={"media_quote_only", "official_video_source", "review_only"},
            source_url="https://www.youtube.com/watch?v=abc12345DEF",
        )

        self.assertEqual(reasons, [])

    def test_youtube_review_notice_article_uses_embed_and_validates(self):
        article, validation = rss_fetcher._build_youtube_review_notice_article(
            source_url="https://www.youtube.com/watch?v=abc12345DEF",
            source_name="上原浩治の雑談魂",
            source_roles={"media_quote_only", "youtube_review_source", "giants_ob"},
            title="あの場面の配球を語る",
            published_at=None,
        )

        self.assertTrue(validation.ok, validation)
        self.assertIn("wp-block-embed-youtube", article.body_html)
        self.assertIn("上原浩治の雑談魂", article.title)


class YoutubeSourceArticleizeTests(unittest.TestCase):
    def test_youtube_channel_media_quote_only_still_articleizes_for_344(self):
        source = {
            "type": "tag_scrape",
            "scraper": "youtube_channel",
            "role": ["media_quote_only"],
        }
        roles = rss_fetcher._source_roles_from_config(source["role"])

        self.assertTrue(
            rss_fetcher._should_articleize_source(
                source_type="tag_scrape",
                source=source,
                source_roles=roles,
            )
        )

    def test_non_youtube_media_quote_only_remains_pool_only(self):
        source = {
            "type": "tag_scrape",
            "scraper": "instagram_tag",
            "role": ["media_quote_only"],
        }
        roles = rss_fetcher._source_roles_from_config(source["role"])

        self.assertFalse(
            rss_fetcher._should_articleize_source(
                source_type="tag_scrape",
                source=source,
                source_roles=roles,
            )
        )


class YoutubeRegistryExpansionTests(unittest.TestCase):
    def test_youtube_registry_sources_are_appended_when_youtube_scraper_present(self):
        base_sources = [
            {
                "name": "読売ジャイアンツYouTube公式",
                "url": "https://www.youtube.com/channel/UCXxg0igSYUp0tqdd6luPEnQ/videos",
                "type": "tag_scrape",
                "scraper": "youtube_channel",
                "role": ["media_quote_only"],
            }
        ]

        expanded = rss_fetcher._expand_sources_with_youtube_registry(
            base_sources,
            logger=logging.getLogger("test"),
        )
        names = {source["name"] for source in expanded}

        self.assertIn("デーブ大久保チャンネル", names)
        self.assertIn("日本野球機構(NPB)公式チャンネル", names)
        self.assertNotIn("sample non Giants YouTube channel", names)
        self.assertEqual(
            sum(
                1
                for source in expanded
                if "UCXxg0igSYUp0tqdd6luPEnQ" in source.get("url", "")
            ),
            1,
        )
        added = next(
            source for source in expanded if source["name"] == "デーブ大久保チャンネル"
        )
        self.assertEqual(added["type"], "tag_scrape")
        self.assertEqual(added["scraper"], "youtube_channel")
        self.assertEqual(added["max_age_days"], 2)
        self.assertEqual(added["article_limit"], 5)
        self.assertIn("media_quote_only", added["role"])
        self.assertIn("review_only", added["role"])
        self.assertIn("giants_ob", added["role"])

    def test_registry_not_appended_when_base_sources_have_no_youtube_scraper(self):
        base_sources = [
            {
                "name": "報知",
                "url": "https://hochi.news/",
                "type": "tag_scrape",
                "scraper": "hochi_giants_tag",
                "role": ["article_source"],
            }
        ]

        expanded = rss_fetcher._expand_sources_with_youtube_registry(
            base_sources,
            logger=logging.getLogger("test"),
        )

        self.assertEqual(expanded, base_sources)


if __name__ == "__main__":
    unittest.main()
