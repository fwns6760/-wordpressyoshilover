import json
import logging
import unittest
from unittest.mock import Mock, patch

from src import rss_fetcher


class FeaturedMediaHelperTests(unittest.TestCase):
    def test_story_fallback_applies_to_pregame_when_images_are_missing(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            images = rss_fetcher._ensure_story_featured_images(
                [],
                "巨人阪神戦 試合前にどこを見たいか",
                "",
                "試合速報",
                "pregame",
                source_url="https://example.com/pregame",
                logger=logger,
            )

        self.assertEqual(images, [rss_fetcher.get_story_fallback_image_url("試合速報", "pregame")])
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(
            payload,
            {
                "event": "featured_image_fallback_applied",
                "source_url": "https://example.com/pregame",
                "category": "試合速報",
                "article_subtype": "pregame",
                "fallback_type": "試合速報:pregame",
                "fallback_url": rss_fetcher.get_story_fallback_image_url("試合速報", "pregame"),
            },
        )

    def test_story_fallback_skips_unlisted_story_types(self):
        images = rss_fetcher._ensure_story_featured_images(
            [],
            "巨人阪神戦 試合の流れを分けたポイント",
            "",
            "試合速報",
            "postgame",
            source_url="https://example.com/postgame",
        )

        self.assertEqual(images, [])

    @patch("src.rss_fetcher.fetch_article_images")
    def test_refetch_article_images_if_empty_uses_page_scrape(self, mock_fetch_article_images):
        mock_fetch_article_images.return_value = ["https://example.com/hero.jpg"]
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            images = rss_fetcher._refetch_article_images_if_empty(
                [],
                "https://example.com/article",
                logger=logger,
                max_images=3,
            )

        self.assertEqual(images, ["https://example.com/hero.jpg"])
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(
            payload,
            {
                "event": "article_image_refetched",
                "source_url": "https://example.com/article",
                "image_count": 1,
                "first_image_url": "https://example.com/hero.jpg",
            },
        )

    def test_resolve_effective_featured_media_uses_existing_post_value(self):
        logger = logging.getLogger("rss_fetcher")
        wp = Mock()
        wp.get_post.return_value = {"featured_media": 62450}

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            featured_media = rss_fetcher._resolve_effective_featured_media(
                wp,
                post_id=62451,
                featured_media=0,
                logger=logger,
            )

        self.assertEqual(featured_media, 62450)
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(
            payload,
            {
                "event": "featured_media_reused_from_existing_post",
                "post_id": 62451,
                "featured_media": 62450,
            },
        )


if __name__ == "__main__":
    unittest.main()
