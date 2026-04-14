import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


class HistoryPersistenceTests(unittest.TestCase):
    def test_persist_history_writes_arbitrary_history_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "rss_history.json"
            history = {
                "https://example.com/article": "2026-04-13T12:00:00",
                "x_post_count_2026-04-13": 4,
            }
            with patch.object(rss_fetcher, "HISTORY_FILE", history_file), patch.object(rss_fetcher, "GCS_BUCKET", ""):
                rss_fetcher.persist_history(history)

            saved = json.loads(history_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["x_post_count_2026-04-13"], 4)
            self.assertIn("https://example.com/article", saved)

    def test_save_history_preserves_existing_daily_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = Path(tmpdir) / "rss_history.json"
            history = {"x_post_count_2026-04-13": 2}
            with patch.object(rss_fetcher, "HISTORY_FILE", history_file), patch.object(rss_fetcher, "GCS_BUCKET", ""):
                rss_fetcher.save_history("https://example.com/a", history, "testnorm")

            saved = json.loads(history_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["x_post_count_2026-04-13"], 2)
            self.assertIn("https://example.com/a", saved)
            self.assertIn("title_norm:testnorm", saved)


if __name__ == "__main__":
    unittest.main()
