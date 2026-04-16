import json
import logging
import unittest
from pathlib import Path

from src import rss_fetcher


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sns_weak_rescue_golden.json"


class SocialWeakRescueGoldenTests(unittest.TestCase):
    def test_sns_weak_rescue_fixture(self):
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            cases = json.load(f)

        logger = logging.getLogger("rss_fetcher")

        for case in cases:
            with self.subTest(case=case["name"]):
                worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
                    case["title"],
                    case["summary"],
                    case["category"],
                    case["article_subtype"],
                )
                self.assertEqual(worthy, case["expected_worthy"])

                if "expected_log" in case:
                    with self.assertLogs("rss_fetcher", level="INFO") as cm:
                        rss_fetcher._log_sns_weak_rescue(
                            logger,
                            case["source_url"],
                            case["title"],
                            rescue_meta,
                        )
                    self.assertEqual(len(cm.records), 1)
                    payload = json.loads(cm.records[0].getMessage())
                    self.assertEqual(payload, case["expected_log"])
                else:
                    self.assertIsNone(rescue_meta)


if __name__ == "__main__":
    unittest.main()
