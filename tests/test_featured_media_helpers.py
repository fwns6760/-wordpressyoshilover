import json
import logging
import unittest
from unittest.mock import Mock, patch

from src import rss_fetcher


class FeaturedMediaHelperTests(unittest.TestCase):
    def test_story_fallback_prefers_team_media_fallback_over_generic_url(self):
        images = rss_fetcher._ensure_story_featured_images(
            [],
            "巨人阪神戦 試合前にどこを見たいか",
            "",
            "試合速報",
            "pregame",
            source_url="https://example.com/pregame",
        )

        self.assertEqual(images, [])

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

    def test_story_fallback_skips_generic_image_for_detectable_player_story(self):
        images = rss_fetcher._ensure_story_featured_images(
            [],
            "【巨人】浅野翔吾が一軍昇格",
            "浅野翔吾外野手が一軍昇格した。",
            "選手情報",
            "player",
            source_url="https://example.com/player",
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

    @patch("src.rss_fetcher.fetch_article_images")
    def test_tag_scrape_prefers_source_article_html_image_over_entry_linked_image(
        self,
        mock_fetch_article_images,
    ):
        mock_fetch_article_images.return_value = [
            "https://www.nikkansports.com/baseball/news/img/202605100001243-w500_0.jpg"
        ]
        entry = {
            "title": "巨人・吉川尚輝「岐阜をかみしめながらプレーしたい」",
            "summary": (
                "別記事リンクが混ざっても https://www.nikkansports.com/baseball/news/202605100001243.html "
                "該当記事の画像を使う"
            ),
        }
        html = (
            '<meta property="og:image" '
            'content="https://hochi.news/images/2026/05/11/20260511-OHT1I51491-L.jpg">'
        )

        images = rss_fetcher._extract_source_article_image_urls(
            "tag_scrape",
            entry,
            "https://hochi.news/articles/20260511-OHT1T51276.html",
            html,
            max_images=3,
        )

        self.assertEqual(
            images,
            ["https://hochi.news/images/2026/05/11/20260511-OHT1I51491-L.jpg"],
        )
        mock_fetch_article_images.assert_not_called()

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

    @patch("src.rss_fetcher.fetch_article_images")
    def test_refetch_article_images_when_existing_candidates_are_generic(self, mock_fetch_article_images):
        mock_fetch_article_images.return_value = [
            "https://hochi.news/images/2026/05/10/20260510-OHT1I51332-L.jpg"
        ]
        logger = logging.getLogger("rss_fetcher")

        images = rss_fetcher._refetch_article_images_if_empty(
            ["https://hochi.news/assets/v2/img/hochi_news_sns.png"],
            "https://hochi.news/articles/20260510-OHT1T51210.html",
            logger=logger,
            max_images=3,
        )

        self.assertEqual(
            images,
            [
                "https://hochi.news/assets/v2/img/hochi_news_sns.png",
                "https://hochi.news/images/2026/05/10/20260510-OHT1I51332-L.jpg",
            ],
        )

    @patch("src.rss_fetcher._fetch_url_html")
    def test_fetch_article_images_keeps_wp_uploads_paths(self, mock_fetch_url_html):
        mock_fetch_url_html.return_value = (
            '<meta property="og:image" '
            'content="https://full-count.jp/wp-content/uploads/2026/05/04193836/20260504_togo_ay.jpg">'
        )

        images = rss_fetcher.fetch_article_images(
            "https://full-count.jp/2026/05/04/post1955326/",
            max_images=3,
        )

        self.assertEqual(
            images,
            [
                "https://full-count.jp/wp-content/uploads/2026/05/04193836/20260504_togo_ay.jpg"
            ],
        )

    @patch("src.rss_fetcher._fetch_url_html")
    def test_fetch_article_images_keeps_baseballking_uploads_paths(self, mock_fetch_url_html):
        mock_fetch_url_html.return_value = (
            '<meta property="og:image" '
            'content="https://baseballking.jp/wp-content/uploads/2026/05/DSC_0091.jpg">'
        )

        images = rss_fetcher.fetch_article_images(
            "https://baseballking.jp/ns/695077/",
            max_images=3,
        )

        self.assertEqual(
            images,
            ["https://baseballking.jp/wp-content/uploads/2026/05/DSC_0091.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
