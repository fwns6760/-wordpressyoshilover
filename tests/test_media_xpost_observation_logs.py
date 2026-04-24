import json
import logging
import unittest

from src import rss_fetcher


class MediaXpostObservationLogTests(unittest.TestCase):
    def test_media_xpost_evaluated_log_payload(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_media_xpost_evaluated(
                logger,
                post_id=62550,
                title="阿部監督の発言をどう見るか",
                category="首脳陣",
                article_subtype="manager",
                selector_type="manager_media",
                is_target=True,
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(
            payload,
            {
                "event": "media_xpost_evaluated",
                "post_id": 62550,
                "title": "阿部監督の発言をどう見るか",
                "category": "首脳陣",
                "article_subtype": "manager",
                "selector_type": "manager_media",
                "is_target": True,
            },
        )

    def test_media_xpost_skipped_log_payload(self):
        logger = logging.getLogger("rss_fetcher")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            rss_fetcher._log_media_xpost_skipped(
                logger,
                post_id=62551,
                title="皆川岳飛、一軍登録 関連情報",
                category="選手情報",
                article_subtype="notice",
                skip_meta={
                    "skip_reason": "score_below_threshold",
                    "pool_size_checked": 3,
                    "best_candidate_score": 188,
                    "best_candidate_handle": "@npb",
                    "best_candidate_age_hours": 6.5,
                },
            )

        payload = json.loads(cm.output[0].split(":", 2)[2])
        self.assertEqual(
            payload,
            {
                "event": "media_xpost_skipped",
                "post_id": 62551,
                "title": "皆川岳飛、一軍登録 関連情報",
                "category": "選手情報",
                "article_subtype": "notice",
                "skip_reason": "score_below_threshold",
                "pool_size_checked": 3,
                "best_candidate_score": 188,
                "best_candidate_handle": "@npb",
                "best_candidate_age_hours": 6.5,
            },
        )


if __name__ == "__main__":
    unittest.main()
