import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src import guarded_publish_runner as runner
from src import rss_fetcher


NOW = datetime.fromisoformat("2026-05-05T17:30:00+09:00")


class StaleFreshness64384RegressionTests(unittest.TestCase):
    def _runner_entry(self) -> dict:
        return {
            "post_id": 64384,
            "title": "阿部監督が打線の反応を説明",
            "resolved_subtype": "manager",
            "template_key": "manager_v1",
            "backlog_only": True,
            "freshness_age_hours": 48.13,
            "freshness_source": "created_at",
            "source_published_at": "2026-05-03T17:22:00+09:00",
            "created_at": "2026-05-05T17:22:00+09:00",
            "modified": "2026-05-05T17:30:00+09:00",
        }

    def _fetcher_entry(self) -> dict:
        return {
            "title": "阿部監督が打線の反応を説明",
            "summary": "スポーツ報知のコメント記事",
            "link": "https://hochi.news/articles/2026/05/03/64384.html",
            "published_parsed": datetime.fromisoformat("2026-05-03T17:22:00+09:00").astimezone(timezone.utc).timetuple(),
            "published": "Sun, 03 May 2026 08:22:00 GMT",
        }

    def test_all_three_flags_on_blocks_64384_shape(self):
        with patch.dict(
            os.environ,
            {
                runner.SOURCE_TIME_PRIORITY_FRESHNESS_ENV: "1",
                runner.STRICT_BREAKING_NEWS_THRESHOLDS_ENV: "1",
                rss_fetcher.ENABLE_FETCHER_STALE_SOURCE_GUARD_ENV_FLAG: "1",
            },
            clear=False,
        ):
            runner_decision = runner._backlog_narrow_publish_decision(self._runner_entry(), now=NOW)
            fetcher_decision = rss_fetcher._evaluate_fetcher_stale_source_guard(
                self._fetcher_entry(),
                post_url="https://hochi.news/articles/2026/05/03/64384.html",
                article_subtype="manager",
                now=NOW,
            )

        self.assertFalse(runner_decision["eligible"])
        self.assertEqual(runner_decision["reason"], "stale_source_age")
        self.assertFalse(fetcher_decision["allow"])

    def test_all_three_flags_off_preserve_existing_behavior(self):
        with patch.dict(
            os.environ,
            {
                runner.SOURCE_TIME_PRIORITY_FRESHNESS_ENV: "0",
                runner.STRICT_BREAKING_NEWS_THRESHOLDS_ENV: "0",
                rss_fetcher.ENABLE_FETCHER_STALE_SOURCE_GUARD_ENV_FLAG: "0",
            },
            clear=False,
        ):
            runner_decision = runner._backlog_narrow_publish_decision(self._runner_entry(), now=NOW)
            fetcher_decision = rss_fetcher._evaluate_fetcher_stale_source_guard(
                self._fetcher_entry(),
                post_url="https://hochi.news/articles/2026/05/03/64384.html",
                article_subtype="manager",
                now=NOW,
            )

        self.assertTrue(runner_decision["eligible"])
        self.assertTrue(fetcher_decision["allow"])


if __name__ == "__main__":
    unittest.main()
