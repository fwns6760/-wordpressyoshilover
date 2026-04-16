import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _skip_reason(
    case: dict,
    category: str,
    title: str,
    summary: str,
    published_at: datetime | None,
) -> str:
    if rss_fetcher._should_skip_stale_postgame_entry(category, title, summary, published_at):
        return "postgame_stale"
    if rss_fetcher._should_skip_stale_player_status_entry(category, title, summary, published_at):
        return "player_status_stale"
    publish_reasons = rss_fetcher.get_publish_skip_reasons(
        source_type=case.get("source_type", "news"),
        draft_only=case.get("draft_only", False),
        featured_media=1 if case.get("featured_media", True) else 0,
    )
    if publish_reasons:
        return ",".join(publish_reasons)
    return ""


class RssProcessingGoldenTests(unittest.TestCase):
    def _load_cases(self, fixture_name: str) -> list[dict]:
        with open(FIXTURE_DIR / fixture_name, encoding="utf-8") as f:
            return json.load(f)

    def _actual_for_case(self, case: dict, keywords: dict) -> dict:
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

        return {
            "category": category,
            "article_subtype": article_subtype,
            "player_mode": player_mode,
            "draft_title": draft_title,
            "skip_reason": _skip_reason(case, category, production_title, summary, published_at),
        }

    def _assert_cases_match_fixture(self, fixture_name: str):
        cases = self._load_cases(fixture_name)
        with open(rss_fetcher.KEYWORDS_FILE, encoding="utf-8") as f:
            keywords = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                if case.get("skip_check_now"):
                    fixed_now = datetime.fromisoformat(case["skip_check_now"])

                    class FixedDateTime(datetime):
                        @classmethod
                        def now(cls, tz=None):
                            if tz:
                                return fixed_now.astimezone(tz)
                            return fixed_now.replace(tzinfo=None)

                    with patch.object(rss_fetcher, "datetime", FixedDateTime):
                        actual = self._actual_for_case(case, keywords)
                else:
                    actual = self._actual_for_case(case, keywords)
                self.assertEqual(actual, case["expected"])

    def test_rss_processing_golden_fixture(self):
        self._assert_cases_match_fixture("rss_processing_golden.json")

    def test_today_cloud_run_golden_fixture(self):
        self._assert_cases_match_fixture("rss_today_cloud_run_golden.json")

    def test_today_cloud_run_fixture_covers_required_article_shapes(self):
        cases = self._load_cases("rss_today_cloud_run_golden.json")
        self.assertEqual(len(cases), 10)
        expected_rows = [case["expected"] for case in cases]
        self.assertTrue(any(row["category"] == "首脳陣" for row in expected_rows))
        self.assertTrue(any(row["category"] == "試合速報" for row in expected_rows))
        self.assertTrue(any(row["category"] == "ドラフト・育成" for row in expected_rows))
        self.assertTrue(any(row["player_mode"] == "player_quote" for row in expected_rows))
        self.assertTrue(any(row["player_mode"] == "player_mechanics" for row in expected_rows))
        self.assertTrue(any(row["player_mode"] == "player_status" for row in expected_rows))
        self.assertTrue(any(case.get("source_type") == "social_news" for case in cases))


if __name__ == "__main__":
    unittest.main()
