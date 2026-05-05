import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from src import guarded_publish_runner as runner
from tests.test_guarded_publish_runner import FIXED_NOW


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


if __name__ == "__main__":
    unittest.main()
