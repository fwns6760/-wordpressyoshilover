import logging
import tempfile
import unittest
from pathlib import Path
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

    def test_persist_processed_entry_history_saves_in_draft_only_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "rss_history.json"
            history = {}

            with patch.object(rss_fetcher, "HISTORY_FILE", history_file), patch.object(rss_fetcher, "GCS_BUCKET", ""):
                persisted = rss_fetcher.persist_processed_entry_history(
                    history,
                    ["https://example.com/article"],
                    ["titlenorm"],
                    rewritten_title="巨人戦 試合前にどこを見たいか",
                    original_title="【4/16予告先発】 巨人 vs 阪神",
                    published=False,
                    publish_skip_reasons=["draft_only"],
                )

            self.assertTrue(persisted)
            self.assertIn("https://example.com/article", history)
            self.assertIn("title_norm:titlenorm", history)
            self.assertIn("rewritten_title_norm:巨人戦試合前にどこを見たいか", history)
            self.assertEqual(
                history["rewritten_title_norm:巨人戦試合前にどこを見たいか"]["original_title"],
                "【4/16予告先発】 巨人 vs 阪神",
            )

    def test_persist_processed_entry_history_skips_non_draft_only_unpublished_entries(self):
        with patch.object(rss_fetcher, "save_history_batch") as save_history_batch:
            persisted = rss_fetcher.persist_processed_entry_history(
                {},
                ["https://example.com/article"],
                ["titlenorm"],
                published=False,
                publish_skip_reasons=["featured_media_missing"],
            )

        self.assertFalse(persisted)
        save_history_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
