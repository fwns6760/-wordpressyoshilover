import io
import os
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import guarded_publish_evaluator as evaluator
from src import guarded_publish_runner as runner
from tests.test_guarded_publish_runner import FIXED_NOW

JST = timezone(timedelta(hours=9), name="JST")


SOURCE_FLAG = runner.SOURCE_TIME_PRIORITY_FRESHNESS_ENV
STRICT_FLAG = runner.STRICT_BREAKING_NEWS_THRESHOLDS_ENV


class GuardedPublishFreshnessSourceTimeTests(unittest.TestCase):
    def _entry(self, **overrides) -> dict:
        payload = {
            "post_id": 64384,
            "title": "阿部監督が打線について語る",
            "resolved_subtype": "manager",
            "template_key": "manager_v1",
            "backlog_only": True,
            "modified": "2026-05-05T17:30:00+09:00",
        }
        payload.update(overrides)
        return payload

    def test_flag_off_keeps_created_at_baseline(self):
        entry = self._entry(
            created_at="2026-05-05T15:30:00+09:00",
            source_published_at="2026-05-03T17:22:00+09:00",
        )

        with patch.dict(os.environ, {SOURCE_FLAG: "0", STRICT_FLAG: "0"}, clear=False):
            age_hours = runner._entry_freshness_age_hours(entry, now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30))

        self.assertEqual(age_hours, 2.0)

    def test_flag_on_prefers_source_published_at_and_emits_source_time_basis(self):
        entry = self._entry(
            created_at="2026-05-05T15:30:00+09:00",
            source_published_at="2026-05-03T17:22:00+09:00",
        )

        stderr = io.StringIO()
        with patch.dict(os.environ, {SOURCE_FLAG: "1", STRICT_FLAG: "0"}, clear=False), redirect_stderr(stderr):
            age_hours = runner._entry_freshness_age_hours(entry, now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30))

        self.assertAlmostEqual(age_hours or 0.0, 48.13, places=2)
        self.assertEqual(entry["_freshness_context_cache"]["freshness_basis"], "source_time")
        self.assertIn('"freshness_basis": "source_time"', stderr.getvalue())

    def test_flag_on_falls_back_to_created_at_with_warning(self):
        entry = self._entry(created_at="2026-05-05T15:30:00+09:00")

        with patch.dict(os.environ, {SOURCE_FLAG: "1", STRICT_FLAG: "0"}, clear=False), self.assertLogs(
            "guarded_publish_runner",
            level="WARNING",
        ) as cm:
            age_hours = runner._entry_freshness_age_hours(entry, now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30))

        self.assertEqual(age_hours, 2.0)
        self.assertIn('"freshness_basis": "created_at_fallback"', "\n".join(cm.output))

    def test_flag_on_uses_older_source_time_even_when_created_at_is_newer(self):
        entry = self._entry(
            created_at="2026-05-05T17:00:00+09:00",
            source_datetime="2026-05-04T08:00:00+09:00",
        )

        with patch.dict(os.environ, {SOURCE_FLAG: "1", STRICT_FLAG: "0"}, clear=False):
            age_hours = runner._entry_freshness_age_hours(entry, now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30))

        self.assertEqual(entry["_freshness_context_cache"]["source_field"], "source_datetime")
        self.assertAlmostEqual(age_hours or 0.0, 33.5, places=2)

    def test_flag_on_uses_source_date_even_when_created_at_is_fresher(self):
        entry = self._entry(
            created_at="2026-05-05T16:45:00+09:00",
            source_date="2026-05-03",
        )

        with patch.dict(os.environ, {SOURCE_FLAG: "1", STRICT_FLAG: "0"}, clear=False):
            age_hours = runner._entry_freshness_age_hours(entry, now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30))

        self.assertEqual(entry["_freshness_context_cache"]["source_field"], "source_date")
        self.assertAlmostEqual(age_hours or 0.0, 65.5, places=2)

    def test_flag_on_missing_all_times_becomes_source_time_missing_review(self):
        entry = self._entry(modified="")

        with patch.dict(os.environ, {SOURCE_FLAG: "1", STRICT_FLAG: "1"}, clear=False):
            decision = runner._backlog_narrow_publish_decision(
                entry,
                now=FIXED_NOW.replace(month=5, day=5, hour=17, minute=30),
            )

        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["reason"], "source_time_missing_review")


class EvaluatorYoshiloverMetaFieldTests(unittest.TestCase):
    """MANUAL-INTAKE-002B: evaluator picks up
    `_yoshilover_source_published_at` directly from raw_post.meta so manual
    intake drafts don't need a body_date fallback to resolve freshness.
    """

    def _now(self) -> datetime:
        return datetime(2026, 5, 7, 17, 30, tzinfo=JST)

    def test_meta_field_resolves_to_source_time(self):
        raw_post = {
            "id": 64500,
            "date": "2026-05-07T17:00:00+09:00",
            "meta": {
                "_yoshilover_source_published_at": "2026-05-06T18:30:00+09:00",
            },
        }
        record = {
            "title": "巨人 試合終了 0-5 ヤクルト",
            "body_text": "本文に日付なし",
            "created_at": "2026-05-07T17:00:00+09:00",
        }

        info = evaluator._resolve_content_datetime(
            raw_post, record, now=self._now()
        )

        self.assertEqual(info["freshness_basis"], "source_time")
        self.assertEqual(
            info["source_published_at"], "2026-05-06T18:30:00+09:00"
        )
        self.assertIn(
            "_yoshilover_source_published_at",
            info["detected_by"],
        )

    def test_meta_field_present_at_top_level_also_resolves(self):
        raw_post = {
            "id": 64501,
            "date": "2026-05-07T17:00:00+09:00",
            "_yoshilover_source_published_at": "2026-05-06T09:00:00+09:00",
            "meta": {},
        }
        record = {
            "title": "巨人 試合速報",
            "body_text": "本文に日付なし",
            "created_at": "2026-05-07T17:00:00+09:00",
        }

        info = evaluator._resolve_content_datetime(
            raw_post, record, now=self._now()
        )

        self.assertEqual(info["freshness_basis"], "source_time")
        self.assertEqual(
            info["source_published_at"], "2026-05-06T09:00:00+09:00"
        )

    def test_meta_field_has_priority_over_body_date(self):
        raw_post = {
            "id": 64502,
            "date": "2026-05-07T17:00:00+09:00",
            "meta": {
                "_yoshilover_source_published_at": "2026-05-06T18:30:00+09:00",
            },
        }
        record = {
            "title": "巨人 試合終了",
            # Body has a different (older) date that body_date fallback would
            # otherwise pick up — meta key must win.
            "body_text": "2026年5月1日の試合を振り返る。",
            "created_at": "2026-05-07T17:00:00+09:00",
        }

        info = evaluator._resolve_content_datetime(
            raw_post, record, now=self._now()
        )

        self.assertEqual(info["freshness_basis"], "source_time")
        self.assertEqual(
            info["source_published_at"], "2026-05-06T18:30:00+09:00"
        )

    def test_meta_field_absent_falls_through_to_body_date_or_created_at(self):
        raw_post = {
            "id": 64503,
            "date": "2026-05-07T17:00:00+09:00",
            "meta": {},
        }
        record = {
            "title": "巨人 試合終了",
            "body_text": "",
            "created_at": "2026-05-07T17:00:00+09:00",
        }

        info = evaluator._resolve_content_datetime(
            raw_post, record, now=self._now()
        )

        self.assertNotEqual(info["freshness_basis"], "source_time")


if __name__ == "__main__":
    unittest.main()
