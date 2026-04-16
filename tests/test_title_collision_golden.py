import json
import logging
import unittest
from pathlib import Path

from src import rss_fetcher


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "title_collision_golden.json"


class TitleCollisionGoldenTests(unittest.TestCase):
    def test_title_collision_fixture_emits_warning_log(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            cases = json.load(f)

        logger = logging.getLogger("rss_fetcher")

        for case in cases:
            with self.subTest(case=case["name"]):
                with self.assertLogs("rss_fetcher", level="WARNING") as cm:
                    rewritten_title_norm = rss_fetcher._log_title_collision_if_needed(
                        logger,
                        case["history"],
                        case["source_url"],
                        case["rewritten_title"],
                    )

                self.assertEqual(rewritten_title_norm, case["expected_warning"]["title_norm"])
                self.assertEqual(len(cm.records), 1)
                payload = json.loads(cm.records[0].getMessage())
                self.assertEqual(payload, case["expected_warning"])


if __name__ == "__main__":
    unittest.main()
