import json
import unittest
from unittest.mock import Mock, call

from src import rss_fetcher


class FeaturedMediaFallbackTests(unittest.TestCase):
    def test_upload_featured_media_with_fallback_uses_second_candidate_when_primary_fails(self):
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = False
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
        # Generic banner shared across multiple source articles — same URL
        # already produced a media slug. We must skip rather than upload a
        # duplicate, falling through to the next candidate (or returning 0
        # so wp_client's resolver picks a per-person / diversified image).
        wp = Mock()
        wp.media_already_uploaded_for_url.side_effect = [True, False]
        wp.upload_image_from_url.return_value = 789

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            media_id = rss_fetcher._upload_featured_media_with_fallback(
                wp,
                [
                    "https://cdn.example.com/0f3c160ddac8.jpg",  # generic banner
                    "https://cdn.example.com/article-specific.jpg",
                ],
                "https://news.example.com/article/123",
            )

        self.assertEqual(media_id, 789)
        # Generic was skipped: only the specific URL was uploaded.
        wp.upload_image_from_url.assert_called_once_with(
            "https://cdn.example.com/article-specific.jpg",
            source_url="https://news.example.com/article/123",
        )
        skip_payload = json.loads(cm.records[0].getMessage())
        self.assertEqual(skip_payload["event"], "featured_media_skip_duplicate_source")
        self.assertEqual(
            skip_payload["candidate_url"],
            "https://cdn.example.com/0f3c160ddac8.jpg",
        )

    def test_returns_zero_when_all_candidates_are_duplicates(self):
        # Every og:image candidate points to a URL whose hash slug
        # already exists in WP media → return 0 so the caller falls
        # through to the per-person / diversified-pool fallback.
        wp = Mock()
        wp.media_already_uploaded_for_url.return_value = True

        media_id = rss_fetcher._upload_featured_media_with_fallback(
            wp,
            [
                "https://cdn.example.com/0f3c160ddac8.jpg",
                "https://cdn.example.com/another-generic.jpg",
            ],
            "https://news.example.com/article/456",
        )

        self.assertEqual(media_id, 0)
        wp.upload_image_from_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
