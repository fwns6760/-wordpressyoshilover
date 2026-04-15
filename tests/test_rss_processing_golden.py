import json
import unittest
from datetime import datetime
from pathlib import Path

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _skip_reason(category: str, title: str, summary: str, published_at: datetime | None) -> str:
    if rss_fetcher._should_skip_stale_postgame_entry(category, title, summary, published_at):
        return "postgame_stale"
    if rss_fetcher._should_skip_stale_player_status_entry(category, title, summary, published_at):
        return "player_status_stale"
    return ""


class RssProcessingGoldenTests(unittest.TestCase):
    def test_rss_processing_golden_fixture(self):
        with open(FIXTURE_DIR / "rss_processing_golden.json", encoding="utf-8") as f:
            cases = json.load(f)
        with open(rss_fetcher.KEYWORDS_FILE, encoding="utf-8") as f:
            keywords = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                title = case["title"]
                summary = case.get("summary", "")
                has_game = case.get("has_game", True)
                production_title = title[:40].strip()
                category = rss_fetcher.classify_category(f"{title} {summary}", keywords)
                article_subtype = rss_fetcher._detect_article_subtype(production_title, summary, category, has_game)
                player_mode = (
                    rss_fetcher._detect_player_article_mode(production_title, summary, category)
                    if category == "選手情報"
                    else ""
                )
                draft_title = rss_fetcher.rewrite_display_title(production_title, summary, category, has_game)
                published_at = datetime.fromisoformat(case["published_at"]) if case.get("published_at") else None

                actual = {
                    "category": category,
                    "article_subtype": article_subtype,
                    "player_mode": player_mode,
                    "draft_title": draft_title,
                    "skip_reason": _skip_reason(category, production_title, summary, published_at),
                }

                self.assertEqual(actual, case["expected"])


if __name__ == "__main__":
    unittest.main()
