import json
import unittest
from unittest.mock import Mock, call

from src import rss_fetcher


class FeaturedMediaFallbackTests(unittest.TestCase):
    def test_reuses_existing_media_for_article_specific_source_url_without_upload(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.return_value = 654
        wp.upload_image_from_url.side_effect = AssertionError("should not upload")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://cdn.example.com/article-specific.jpg",
            ],
            "https://news.example.com/article/654",
        )

        self.assertEqual(media_id, 654)
        wp.find_uploaded_media_id_for_url.assert_called_once_with(
            "https://cdn.example.com/article-specific.jpg"
        )
        wp.upload_image_from_url.assert_not_called()

    def test_skips_generic_primary_and_reuses_specific_existing_media(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.return_value = 789
        wp.upload_image_from_url.side_effect = AssertionError("should not upload")

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://hochi.news/assets/v2/img/hochi_news_sns.png",
                "https://hochi.news/images/2026/05/09/20260509-OHT1I51548-L.jpg",
            ],
            "https://twitter.com/hochi_giants/status/2053070768624267651",
        )

        self.assertEqual(media_id, 789)
        self.assertEqual(
            wp.find_uploaded_media_id_for_url.call_args_list,
            [
                call("https://hochi.news/images/2026/05/09/20260509-OHT1I51548-L.jpg"),
            ],
        )
        wp.upload_image_from_url.assert_not_called()

    def test_upload_featured_media_with_fallback_uses_second_candidate_when_primary_fails(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.return_value = 0
        wp.upload_image_from_url.side_effect = [0, 456]

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            media_id = rss_fetcher._upload_featured_media_with_fallback(
                wp,
                [
                    "https://abs.twimg.com/emoji/v2/svg/26a0.svg",
                    "https://pbs.twimg.com/media/HF77Ob7agAA_PyF?format=jpg&name=orig",
                ],
                "https://twitter.com/TokyoGiants/status/2044384085616066802",
            )

        self.assertEqual(media_id, 456)
        self.assertEqual(
            wp.upload_image_from_url.call_args_list,
            [
                call(
                    "https://abs.twimg.com/emoji/v2/svg/26a0.svg",
                    source_url="https://twitter.com/TokyoGiants/status/2044384085616066802",
                ),
                call(
                    "https://pbs.twimg.com/media/HF77Ob7agAA_PyF?format=jpg&name=orig",
                    source_url="https://twitter.com/TokyoGiants/status/2044384085616066802",
                ),
            ],
        )
        payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(
            payload,
            {
                "event": "featured_media_fallback_used",
                "post_url": "https://twitter.com/TokyoGiants/status/2044384085616066802",
                "primary_url": "https://abs.twimg.com/emoji/v2/svg/26a0.svg",
                "fallback_url": "https://pbs.twimg.com/media/HF77Ob7agAA_PyF?format=jpg&name=orig",
            },
        )

    def test_upload_featured_media_with_fallback_returns_primary_media_without_log(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.return_value = 0
        wp.upload_image_from_url.return_value = 321

        with self.assertNoLogs("rss_fetcher", level="INFO"):
            media_id = rss_fetcher._upload_featured_media_with_fallback(
                wp,
                [
                    "https://example.com/hero.jpg",
                    "https://example.com/secondary.jpg",
                ],
                "https://example.com/article",
            )

        self.assertEqual(media_id, 321)
        wp.upload_image_from_url.assert_called_once_with(
            "https://example.com/hero.jpg",
            source_url="https://example.com/article",
        )

    def test_skip_candidate_when_already_uploaded_for_another_post(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.side_effect = [0, 0]
        wp.upload_image_from_url.return_value = 789

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            media_id = rss_fetcher._upload_featured_media_with_fallback(
                wp,
                [
                    "https://www.sponichi.co.jp/assets/images/@1x/sponichi_sns001.webp",
                    "https://cdn.example.com/article-specific.jpg",
                ],
                "https://news.example.com/article/123",
            )

        self.assertEqual(media_id, 789)
        wp.upload_image_from_url.assert_called_once_with(
            "https://cdn.example.com/article-specific.jpg",
            source_url="https://news.example.com/article/123",
        )
        skip_payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(skip_payload["event"], "featured_media_skip_generic_source")
        self.assertEqual(
            skip_payload["candidate_url"],
            "https://www.sponichi.co.jp/assets/images/@1x/sponichi_sns001.webp",
        )

    def test_returns_zero_when_all_candidates_are_generic(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
        wp.find_uploaded_media_id_for_url.return_value = 0

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://hochi.news/assets/v2/img/hochi_news_sns.png",
                "https://www.sponichi.co.jp/assets/images/@1x/sponichi_sns001.webp",
            ],
            "https://news.example.com/article/456",
        )

        self.assertEqual(media_id, 0)
        wp.upload_image_from_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
