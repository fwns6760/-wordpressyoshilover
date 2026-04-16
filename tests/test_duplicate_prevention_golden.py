import json
import unittest
from pathlib import Path

from src import rss_fetcher


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "duplicate_prevention_golden.json"


class DuplicatePreventionGoldenTests(unittest.TestCase):
    def test_duplicate_prevention_fixture(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            cases = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                actual = rss_fetcher._is_history_duplicate(
                    case["post_url"],
                    case["entry_title_norm"],
                    case["history"],
                )
                self.assertEqual(actual, case["expected_duplicate"])


if __name__ == "__main__":
    unittest.main()
