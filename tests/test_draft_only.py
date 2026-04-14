import logging
import unittest
from unittest.mock import Mock, patch

from src import rss_fetcher


class DraftOnlyTests(unittest.TestCase):
    def test_finalize_post_publication_skips_publish_in_draft_only_mode(self):
        wp = Mock()
        history = {}
        logger = logging.getLogger("rss_fetcher")

        with patch.object(rss_fetcher, "save_history") as save_history:
            published = rss_fetcher.finalize_post_publication(
                wp,
                post_id=123,
                post_url="https://example.com/article",
                history=history,
                entry_title_norm="title",
                logger=logger,
                draft_only=True,
            )

        self.assertFalse(published)
        wp.update_post_status.assert_not_called()
        save_history.assert_not_called()

    def test_finalize_post_publication_publishes_and_saves_history(self):
        wp = Mock()
        history = {}
        logger = logging.getLogger("rss_fetcher")

        with patch.object(rss_fetcher, "save_history") as save_history:
            published = rss_fetcher.finalize_post_publication(
                wp,
                post_id=456,
                post_url="https://example.com/article",
                history=history,
                entry_title_norm="title",
                logger=logger,
                draft_only=False,
            )

        self.assertTrue(published)
        wp.update_post_status.assert_called_once_with(456, "publish")
        save_history.assert_called_once_with("https://example.com/article", history, "title")


if __name__ == "__main__":
    unittest.main()
