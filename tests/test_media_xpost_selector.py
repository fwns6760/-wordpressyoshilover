import unittest

from src.media_xpost_selector import select_media_quotes


class MediaXpostSelectorTests(unittest.TestCase):
    def test_social_news_returns_source_url(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/hochi_giants/status/123",
                "source_name": "スポーツ報知巨人班X",
                "created_at": "2026-04-16T10:00:00+09:00",
            }
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://twitter.com/hochi_giants/status/123")
        self.assertEqual(quotes[0]["handle"], "@hochi_giants")
        self.assertEqual(quotes[0]["quote_type"], "source_tweet")

    def test_news_returns_empty_list(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "source_url": "https://twitter.com/hochi_giants/status/123",
                "source_name": "スポーツ報知巨人班X",
            }
        )

        self.assertEqual(quotes, [])

    def test_max_count_zero_returns_empty_list(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/TokyoGiants/status/123",
            },
            max_count=0,
        )

        self.assertEqual(quotes, [])

    def test_falls_back_to_post_url_when_source_url_missing(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "post_url": "https://x.com/TokyoGiants/status/456",
                "source_name": "巨人公式X",
            }
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://x.com/TokyoGiants/status/456")
        self.assertEqual(quotes[0]["handle"], "@TokyoGiants")


if __name__ == "__main__":
    unittest.main()
