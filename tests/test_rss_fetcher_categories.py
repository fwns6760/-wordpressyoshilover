import unittest
from unittest.mock import Mock

from src import rss_fetcher


class RssFetcherDraftCategoryTests(unittest.TestCase):
    def _build_wp(self, mapping: dict[str, int]) -> Mock:
        wp = Mock()
        wp.resolve_category_id.side_effect = lambda name: mapping.get(name, 0)
        return wp

    def test_new_article_no_auto_post_category(self):
        wp = self._build_wp({"試合速報": 663, "コラム": 670})

        categories = rss_fetcher._resolve_draft_category_ids(wp, "試合速報")

        self.assertEqual(categories, [663])
        self.assertNotIn(rss_fetcher.AUTO_POST_CATEGORY_ID, categories)

    def test_semantic_category_resolved(self):
        wp = self._build_wp({"選手情報": 664, "コラム": 670})

        categories = rss_fetcher._resolve_draft_category_ids(wp, "選手情報")

        self.assertEqual(categories, [664])
        wp.resolve_category_id.assert_called_once_with("選手情報")

    def test_fallback_category_when_unresolved(self):
        wp = self._build_wp({"コラム": 670})

        with self.assertLogs("rss_fetcher", level="WARNING") as cm:
            categories = rss_fetcher._resolve_draft_category_ids(
                wp,
                "未設定カテゴリ",
                rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        self.assertEqual(categories, [670])
        self.assertIn("draft category fallback applied", "\n".join(cm.output))

    def test_categories_never_empty(self):
        wp = self._build_wp({"コラム": 670})

        categories = rss_fetcher._resolve_draft_category_ids(wp, "")

        self.assertEqual(categories, [670])
        self.assertTrue(categories)


if __name__ == "__main__":
    unittest.main()
