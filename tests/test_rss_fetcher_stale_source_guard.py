import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src import rss_fetcher


FETCHER_FLAG = rss_fetcher.ENABLE_FETCHER_STALE_SOURCE_GUARD_ENV_FLAG
STRICT_FLAG = "ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS"
NOW = datetime.fromisoformat("2026-05-05T17:30:00+09:00")


class RssFetcherStaleSourceGuardTests(unittest.TestCase):
    def _entry(
        self,
        *,
        link: str,
        published_dt: datetime | None = None,
        updated_dt: datetime | None = None,
    ) -> dict:
        payload = {
            "title": "阿部監督がコメントを整理",
            "summary": "巨人の最新動向を整理",
            "link": link,
        }
        if published_dt is not None:
            payload["published_parsed"] = published_dt.astimezone(timezone.utc).timetuple()
            payload["published"] = published_dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        if updated_dt is not None:
            payload["updated_parsed"] = updated_dt.astimezone(timezone.utc).timetuple()
            payload["updated"] = updated_dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return payload

    def _x_status_url(self, dt: datetime) -> str:
        timestamp_ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
        status_id = (timestamp_ms - rss_fetcher.X_SNOWFLAKE_EPOCH_MS) << 22
        return f"https://twitter.com/TokyoGiants/status/{status_id}"

    def _decision(self, entry: dict, *, post_url: str, article_subtype: str, env: dict[str, str]) -> dict:
        with patch.dict(os.environ, env, clear=False):
            return rss_fetcher._evaluate_fetcher_stale_source_guard(
                entry,
                post_url=post_url,
                article_subtype=article_subtype,
                now=NOW,
            )

    def test_flag_off_keeps_existing_behavior_for_old_rss_entry(self):
        entry = self._entry(
            link="https://example.com/story",
            published_dt=datetime.fromisoformat("2026-05-03T08:00:00+09:00"),
        )

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "0", STRICT_FLAG: "0"},
        )

        self.assertTrue(decision["allow"])
        self.assertEqual(decision["reason"], "")

    def test_flag_on_two_day_old_x_post_skips_with_stale_x_post(self):
        entry = self._entry(link=self._x_status_url(datetime.fromisoformat("2026-05-03T10:00:00+09:00")))

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "stale_x_post")

    def test_flag_on_same_day_x_post_stays_creatable(self):
        entry = self._entry(link=self._x_status_url(datetime.fromisoformat("2026-05-05T14:00:00+09:00")))

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertTrue(decision["allow"])
        self.assertEqual(decision["reason"], "")

    def test_flag_on_two_day_old_rss_pubdate_skips_with_stale_rss_entry(self):
        entry = self._entry(
            link="https://example.com/story",
            published_dt=datetime.fromisoformat("2026-05-03T09:00:00+09:00"),
        )

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "stale_rss_entry")

    def test_flag_on_same_day_rss_pubdate_stays_creatable(self):
        entry = self._entry(
            link="https://example.com/story",
            published_dt=datetime.fromisoformat("2026-05-05T10:30:00+09:00"),
        )

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertTrue(decision["allow"])
        self.assertEqual(decision["reason"], "")

    def test_flag_on_url_date_pattern_uses_shared_threshold(self):
        entry = self._entry(link="https://www.nikkansports.com/baseball/news/202605030001754.html")

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "stale_source_age")

    def test_flag_on_missing_all_source_time_skips_with_review_reason(self):
        entry = self._entry(link="https://example.com/story")

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "source_time_missing_review")

    def test_flag_on_off_field_keeps_broader_existing_threshold(self):
        entry = self._entry(
            link="https://example.com/ob-column",
            published_dt=datetime.fromisoformat("2026-05-04T06:00:00+09:00"),
        )

        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="off_field",
            env={FETCHER_FLAG: "1", STRICT_FLAG: "1"},
        )

        self.assertTrue(decision["allow"])
        self.assertEqual(decision["reason"], "")


if __name__ == "__main__":
    unittest.main()
