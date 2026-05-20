import inspect
import unittest

from src import rss_fetcher


class MediaQuoteDefaultGuardTests(unittest.TestCase):
    def test_main_initializes_media_quote_defaults_before_selector_and_logs(self):
        """398: media quote selector/logging variables must have safe defaults.

        A production run observed an UnboundLocalError for
        ``media_quote_evaluation`` in the post-create observability block. Keep
        per-entry defaults before the selector call so future branch changes
        cannot leave the log block without safe values.
        """

        source = inspect.getsource(rss_fetcher._main)
        default_pos = source.index("media_quote_evaluation: dict[str, object]")
        selector_pos = source.index("media_quote_evaluation = evaluate_media_quote_selection")
        log_pos = source.index("_log_media_xpost_evaluated(")

        self.assertLess(default_pos, selector_pos)
        self.assertLess(selector_pos, log_pos)
        self.assertIn("media_quotes: list[dict] = []", source)
        self.assertIn(") or {}", source)
        self.assertIn('media_quotes = list(media_quote_evaluation.get("quotes") or [])', source)


if __name__ == "__main__":
    unittest.main()
