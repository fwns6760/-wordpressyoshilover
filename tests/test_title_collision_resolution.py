import json
import unittest
from collections import defaultdict
from pathlib import Path

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TitleCollisionResolutionTests(unittest.TestCase):
    def test_collision_resolution_fixture(self):
        with open(FIXTURE_DIR / "title_collision_resolution.json", encoding="utf-8") as f:
            cases = json.load(f)
        grouped_titles = defaultdict(list)

        for case in cases:
            with self.subTest(case=case["name"]):
                rewritten = rss_fetcher.rewrite_display_title(
                    case["title"],
                    case.get("summary", ""),
                    case["category"],
                    case.get("has_game", True),
                )
                self.assertEqual(rewritten, case["expected_title"])
                grouped_titles[case["group"]].append(rewritten)

        for group, titles in grouped_titles.items():
            with self.subTest(group=group):
                self.assertEqual(len(titles), len(set(titles)))
