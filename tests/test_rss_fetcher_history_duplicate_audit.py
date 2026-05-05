import unittest
from datetime import datetime, timezone

from src import rss_fetcher


class HistoryDuplicateAuditTests(unittest.TestCase):
    def test_exact_widget_script_url_in_history_is_true_duplicate(self):
        post_url = "https://platform.twitter.com/widgets.js"
        history = {post_url: {"post_id": 1}}

        self.assertTrue(rss_fetcher._is_history_duplicate(post_url, "", history))

    def test_widget_script_like_url_without_exact_history_key_is_not_false_positive(self):
        history = {
            "https://platform.twitter.com/widgets.js?seed=1": {"post_id": 1},
            "title_norm:relatedpost": {"post_id": 2},
        }

        self.assertFalse(
            rss_fetcher._is_history_duplicate(
                "https://platform.twitter.com/widgets.js?seed=2",
                "differentwidgetseed",
                history,
            )
        )

    def test_short_common_anchor_title_norm_does_not_trigger_history_duplicate(self):
        history = {"title_norm:widget": {"post_id": 1}}

        self.assertFalse(rss_fetcher._is_history_duplicate("https://example.com/post", "短報", history))

    def test_canonical_url_normalization_drops_fragment_for_true_duplicate_boundary(self):
        left = rss_fetcher.compute_duplicate_key(
            source_url="https://example.com/post#widget",
            canonical_url="https://example.com/post#widget",
            title="【巨人】阿部監督がコメント",
            source_family="hochi",
            subtype="manager",
        )
        right = rss_fetcher.compute_duplicate_key(
            source_url="https://example.com/post#common-anchor",
            canonical_url="https://example.com/post#common-anchor",
            title="別タイトル",
            source_family="sponichi",
            subtype="manager",
        )

        self.assertEqual(left, right)

    def test_source_url_hash_keeps_exact_raw_url_for_audit_visibility(self):
        first = rss_fetcher._build_duplicate_news_context(
            source_url="https://news.hochi.news/articles/2026/05/05/example.html#widget",
            title="【巨人】阿部監督がコメント",
            summary="阿部監督がコメントした。",
            category="首脳陣",
            source_type="news",
            has_game=False,
            source_entry={},
            source_name="スポーツ報知",
            published_at=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        )
        second = rss_fetcher._build_duplicate_news_context(
            source_url="https://news.hochi.news/articles/2026/05/05/example.html#common-anchor",
            title="【巨人】阿部監督がコメント",
            summary="阿部監督がコメントした。",
            category="首脳陣",
            source_type="news",
            has_game=False,
            source_entry={},
            source_name="スポーツ報知",
            published_at=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first["source_url_hash"], second["source_url_hash"])
        self.assertEqual(first["duplicate_key"], second["duplicate_key"])


if __name__ == "__main__":
    unittest.main()
