import json
import unittest

from src import rss_fetcher


class NotGiantsObservationTests(unittest.TestCase):
    def test_matching_giants_keywords_returns_empty_when_no_hit(self):
        self.assertEqual(rss_fetcher._matching_giants_keywords("阪神が勝利した。"), [])

    def test_log_not_giants_related_skip_contains_title(self):
        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_not_giants_related_skip(
                rss_fetcher.logging.getLogger("rss_fetcher"),
                title="阪神の試合振り返り",
                post_url="https://example.com/hanshin",
                source_name="スポーツ報知",
                detected_keywords=[],
            )
        payload = json.loads(cm.output[0].split("INFO:rss_fetcher:", 1)[1])
        self.assertEqual(payload["event"], "not_giants_related_skip")
        self.assertEqual(payload["title"], "阪神の試合振り返り")
        self.assertEqual(payload["detected_keywords"], [])

    def test_skip_reasons_with_samples_includes_sample_titles(self):
        payload = rss_fetcher._skip_reasons_with_samples(
            rss_fetcher.Counter({"not_giants_related": 12, "sns_polluted": 3}),
            not_giants_related_sample_titles=["A", "B", "C", "D"],
        )
        self.assertEqual(payload["not_giants_related"], 12)
        self.assertEqual(payload["sns_polluted"], 3)
        self.assertEqual(payload["not_giants_related_sample_titles"], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
