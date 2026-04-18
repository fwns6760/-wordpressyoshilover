import json
import unittest
from unittest.mock import Mock, call

from src import rss_fetcher


class FeaturedMediaFallbackTests(unittest.TestCase):
    def test_upload_featured_media_with_fallback_uses_second_candidate_when_primary_fails(self):
        wp = Mock()
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


if __name__ == "__main__":
    unittest.main()
