import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src import guarded_publish_evaluator as evaluator
from src import guarded_publish_runner as runner
from src import rss_fetcher


UTC = timezone.utc
RUNNER_SOURCE_FLAG = runner.SOURCE_TIME_PRIORITY_FRESHNESS_ENV
STRICT_FLAG = runner.STRICT_BREAKING_NEWS_THRESHOLDS_ENV
FETCHER_FLAG = rss_fetcher.ENABLE_FETCHER_STALE_SOURCE_GUARD_ENV_FLAG


def _raw_post(
    post_id: int,
    title: str,
    *,
    subtype: str,
    source_url: str,
    source_meta: dict[str, str] | None = None,
    body_html: str | None = None,
    date: str = "2026-05-05T12:00:00",
    modified: str = "2026-05-05T12:30:00",
) -> dict:
    meta = {"article_subtype": subtype, "_yoshilover_source_url": source_url}
    meta.update(source_meta or {})
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {
            "raw": body_html
            or (
                f"<p>{title}を整理した。</p>"
                f"<p>参照元: スポーツ報知 {source_url}</p>"
            )
        },
        "excerpt": {"raw": "", "rendered": ""},
        "featured_media": 10,
        "modified": modified,
        "date": date,
        "categories": [],
        "tags": [],
        "meta": meta,
    }


class StaleFreshnessIncident64384Tests(unittest.TestCase):
    def _runner_entry(
        self,
        *,
        subtype: str = "manager",
        source_published_at: str | None = None,
        created_at: str = "2026-05-05T21:30:00+00:00",
        modified: str = "2026-05-05T22:00:00+00:00",
        freshness_age_hours: float | None = None,
        freshness_basis: str | None = None,
        backlog_only: bool = True,
        post_id: int = 64384,
        title: str = "阿部監督が打線の反応を説明",
    ) -> dict:
        entry = {
            "post_id": post_id,
            "title": title,
            "resolved_subtype": subtype,
            "template_key": f"{subtype}_v1",
            "backlog_only": backlog_only,
            "created_at": created_at,
            "modified": modified,
        }
        if source_published_at is not None:
            entry["source_published_at"] = source_published_at
        if freshness_age_hours is not None:
            entry["freshness_age_hours"] = freshness_age_hours
        if freshness_basis is not None:
            entry["freshness_basis"] = freshness_basis
        return entry

    def _fetcher_entry(
        self,
        *,
        link: str,
        published_at: str | None = None,
        updated_at: str | None = None,
        title: str = "阿部監督が打線の反応を説明",
    ) -> dict:
        entry = {
            "title": title,
            "summary": "スポーツ報知のコメント記事",
            "link": link,
        }
        if published_at is not None:
            published_dt = datetime.fromisoformat(published_at)
            entry["published_parsed"] = published_dt.astimezone(UTC).timetuple()
            entry["published"] = published_dt.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        if updated_at is not None:
            updated_dt = datetime.fromisoformat(updated_at)
            entry["updated_parsed"] = updated_dt.astimezone(UTC).timetuple()
            entry["updated"] = updated_dt.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return entry

    def _x_status_url(self, source_dt: datetime) -> str:
        timestamp_ms = int(source_dt.astimezone(UTC).timestamp() * 1000)
        status_id = (timestamp_ms - rss_fetcher.X_SNOWFLAKE_EPOCH_MS) << 22
        return f"https://twitter.com/TokyoGiants/status/{status_id}"

    def _runner_decision(self, entry: dict, *, now: datetime, source_flag: bool, strict_flag: bool) -> dict:
        with patch.dict(
            os.environ,
            {
                RUNNER_SOURCE_FLAG: "1" if source_flag else "0",
                STRICT_FLAG: "1" if strict_flag else "0",
            },
            clear=False,
        ):
            return runner._backlog_narrow_publish_decision(dict(entry), now=now)

    def _fetcher_decision(
        self,
        entry: dict,
        *,
        now: datetime,
        post_url: str,
        subtype: str,
        fetcher_flag: bool,
        strict_flag: bool,
    ) -> dict:
        with patch.dict(
            os.environ,
            {
                FETCHER_FLAG: "1" if fetcher_flag else "0",
                STRICT_FLAG: "1" if strict_flag else "0",
            },
            clear=False,
        ):
            return rss_fetcher._evaluate_fetcher_stale_source_guard(
                dict(entry),
                post_url=post_url,
                article_subtype=subtype,
                now=now,
            )

    def _evaluate_single(self, raw_post: dict, *, now: datetime, strict_flag: bool) -> tuple[str, dict]:
        with patch.dict(os.environ, {STRICT_FLAG: "1" if strict_flag else "0"}, clear=False):
            report = evaluator.evaluate_raw_posts([raw_post], window_hours=96, max_pool=10, now=now)
        for bucket in ("green", "yellow", "review", "red"):
            if report[bucket]:
                return bucket, report[bucket][0]
        self.fail("expected one evaluated entry")

    def test_f1_incident_64384_shape_rejects_with_flags_on_and_preserves_off(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        source_published_at = "2026-05-03T08:22:00+00:00"
        source_url = "https://hochi.news/articles/2026/05/03/64384.html"
        runner_entry = self._runner_entry(
            source_published_at=source_published_at,
            created_at="2026-05-05T21:22:00+00:00",
            modified="2026-05-05T22:00:00+00:00",
            freshness_age_hours=0.63,
            freshness_basis="created_at_fallback",
        )
        fetcher_entry = self._fetcher_entry(link=source_url, published_at=source_published_at)

        on_runner = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=True)
        off_runner = self._runner_decision(runner_entry, now=now, source_flag=False, strict_flag=False)
        on_fetcher = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=True,
        )
        off_fetcher = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=False,
            strict_flag=False,
        )

        self.assertFalse(on_runner["eligible"])
        self.assertEqual(on_runner["reason"], "stale_source_age")
        self.assertTrue(off_runner["eligible"])
        self.assertFalse(on_fetcher["allow"])
        self.assertEqual(on_fetcher["reason"], "stale_rss_entry")
        self.assertTrue(off_fetcher["allow"])

    def test_f2_same_day_manager_comment_stays_publishable(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        source_published_at = "2026-05-05T21:00:00+00:00"
        source_url = "https://hochi.news/articles/2026/05/05/64385.html"
        runner_entry = self._runner_entry(
            source_published_at=source_published_at,
            created_at="2026-05-05T21:05:00+00:00",
            modified="2026-05-05T21:30:00+00:00",
            freshness_age_hours=1.0,
            freshness_basis="source_time",
        )
        raw_post = _raw_post(
            64385,
            "阿部監督が試合後に打線の反応を説明",
            subtype="manager",
            source_url=source_url,
            source_meta={"rss_published": source_published_at},
        )
        fetcher_entry = self._fetcher_entry(link=source_url, published_at=source_published_at)

        on_bucket, on_eval = self._evaluate_single(raw_post, now=now, strict_flag=True)
        off_bucket, off_eval = self._evaluate_single(raw_post, now=now, strict_flag=False)
        on_runner = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=True)
        off_runner = self._runner_decision(runner_entry, now=now, source_flag=False, strict_flag=False)
        on_fetcher = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=True,
        )

        self.assertEqual(on_bucket, "green")
        self.assertEqual(off_bucket, "green")
        self.assertTrue(on_eval["publishable"])
        self.assertTrue(off_eval["publishable"])
        self.assertTrue(on_runner["eligible"])
        self.assertTrue(off_runner["eligible"])
        self.assertTrue(on_fetcher["allow"])

    def test_f3_manager_24h_plus_1m_rejects_only_when_strict_is_on(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        source_published_at = "2026-05-04T21:59:00+00:00"
        source_url = "https://hochi.news/articles/2026/05/04/64386.html"
        raw_post = _raw_post(
            64386,
            "阿部監督が前日コメントを整理",
            subtype="manager",
            source_url=source_url,
            source_meta={"rss_published": source_published_at},
        )
        runner_entry = self._runner_entry(
            source_published_at=source_published_at,
            freshness_age_hours=24.02,
            freshness_basis="source_time",
        )
        fetcher_entry = self._fetcher_entry(link=source_url, published_at=source_published_at)

        on_bucket, on_eval = self._evaluate_single(raw_post, now=now, strict_flag=True)
        off_bucket, off_eval = self._evaluate_single(raw_post, now=now, strict_flag=False)
        on_runner = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=True)
        off_runner = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=False)
        on_fetcher = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=True,
        )
        off_fetcher = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=False,
        )

        self.assertEqual(on_bucket, "yellow")
        self.assertTrue(on_eval["publishable"])
        self.assertTrue(on_eval["backlog_only"])
        self.assertIn("stale_for_breaking_board", on_eval["repairable_flags"])
        self.assertEqual(off_bucket, "green")
        self.assertTrue(off_eval["publishable"])
        self.assertFalse(on_runner["eligible"])
        self.assertEqual(on_runner["reason"], "stale_source_age")
        self.assertTrue(off_runner["eligible"])
        self.assertFalse(on_fetcher["allow"])
        self.assertEqual(on_fetcher["reason"], "stale_rss_entry")
        self.assertTrue(off_fetcher["allow"])

    def test_f4_manager_48h_plus_1m_hits_existing_relaxed_threshold(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        source_published_at = "2026-05-03T21:59:00+00:00"
        source_url = "https://hochi.news/articles/2026/05/03/64387.html"
        raw_post = _raw_post(
            64387,
            "阿部監督が2日前コメントを整理",
            subtype="manager",
            source_url=source_url,
            source_meta={"rss_published": source_published_at},
        )
        fetcher_entry = self._fetcher_entry(link=source_url, published_at=source_published_at)

        bucket, entry = self._evaluate_single(raw_post, now=now, strict_flag=False)
        fetcher_decision = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=False,
        )

        self.assertEqual(bucket, "yellow")
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["backlog_only"])
        self.assertIn("stale_for_breaking_board", entry["repairable_flags"])
        self.assertFalse(fetcher_decision["allow"])
        self.assertEqual(fetcher_decision["reason"], "stale_rss_entry")

    def test_f5_missing_source_time_becomes_review_reason(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        source_url = "https://example.com/story-without-date"
        raw_post = _raw_post(
            64388,
            "阿部監督が試合後にコメント",
            subtype="manager",
            source_url=source_url,
            source_meta={},
            date="2026-05-05T21:00:00",
            modified="2026-05-05T21:30:00",
        )
        runner_entry = self._runner_entry(
            source_published_at=None,
            created_at="2026-05-05T21:00:00+00:00",
            modified="2026-05-05T21:30:00+00:00",
            freshness_age_hours=None,
            freshness_basis=None,
        )
        fetcher_entry = self._fetcher_entry(link=source_url)

        bucket, entry = self._evaluate_single(raw_post, now=now, strict_flag=True)
        runner_decision = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=True)
        fetcher_decision = self._fetcher_decision(
            fetcher_entry,
            now=now,
            post_url=source_url,
            subtype="manager",
            fetcher_flag=True,
            strict_flag=True,
        )

        self.assertEqual(bucket, "review")
        self.assertFalse(entry["publishable"])
        self.assertIn("source_time_missing_review", entry["review_flags"])
        self.assertFalse(runner_decision["eligible"])
        self.assertEqual(runner_decision["reason"], "source_time_missing_review")
        self.assertFalse(fetcher_decision["allow"])
        self.assertEqual(fetcher_decision["reason"], "source_time_missing_review")

    def test_f6_backlog_flag_within_24h_stays_in_existing_backlog_flow(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        runner_entry = self._runner_entry(
            source_published_at="2026-05-05T21:00:00+00:00",
            freshness_age_hours=1.0,
            freshness_basis="source_time",
            backlog_only=True,
        )

        decision = self._runner_decision(runner_entry, now=now, source_flag=True, strict_flag=True)

        self.assertTrue(decision["eligible"])
        self.assertEqual(decision["reason"], "")

    def test_f7_same_day_postgame_stays_green_with_strict_on(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        raw_post = _raw_post(
            64389,
            "巨人が阪神に3-2で勝利",
            subtype="postgame",
            source_url="https://hochi.news/articles/2026/05/05/postgame64389.html",
            source_meta={"rss_published": "2026-05-05T21:30:00+00:00"},
        )

        bucket, entry = self._evaluate_single(raw_post, now=now, strict_flag=True)

        self.assertEqual(bucket, "green")
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["backlog_only"])

    def test_f8_same_day_lineup_stays_green_with_strict_on(self):
        now = datetime.fromisoformat("2026-05-05T18:00:00+09:00")
        raw_post = _raw_post(
            64390,
            "巨人スタメン 1番丸 4番岡本",
            subtype="lineup",
            source_url="https://hochi.news/articles/2026/05/05/lineup64390.html",
            source_meta={"rss_published": "2026-05-05T16:00:00+09:00"},
            body_html=(
                "<p>巨人のスタメンが発表された。</p>"
                "<p>試合開始 20:00</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/2026/05/05/lineup64390.html</p>"
            ),
            date="2026-05-05T16:10:00",
            modified="2026-05-05T16:20:00",
        )

        bucket, entry = self._evaluate_single(raw_post, now=now, strict_flag=True)

        self.assertEqual(bucket, "green")
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["backlog_only"])

    def test_f9_same_day_farm_result_stays_green_with_strict_on(self):
        now = datetime.fromisoformat("2026-05-05T22:00:00+00:00")
        raw_post = _raw_post(
            64391,
            "巨人2軍が西武に4-2で勝利",
            subtype="farm_result",
            source_url="https://hochi.news/articles/2026/05/05/farm64391.html",
            source_meta={"rss_published": "2026-05-05T21:00:00+00:00"},
            body_html=(
                "<p>巨人2軍が西武に4-2で勝利した。</p>"
                "<p>先発の山田投手は6回2失点、岡田の適時打で勝ち越した。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/2026/05/05/farm64391.html</p>"
            ),
        )

        bucket, entry = self._evaluate_single(raw_post, now=now, strict_flag=True)

        self.assertEqual(bucket, "green")
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["backlog_only"])


if __name__ == "__main__":
    unittest.main()
