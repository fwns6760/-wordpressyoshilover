import json
import os
import unittest
from unittest.mock import patch

from src import guarded_publish_evaluator as evaluator
from tests.test_guarded_publish_runner import FIXED_NOW, _post


STRICT_FLAG = evaluator.ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS_ENV


class GuardedPublishStrictBreakingThresholdTests(unittest.TestCase):
    def _freshness_entry(
        self,
        post_id: int,
        *,
        subtype: str,
        source_published_at: str,
        title: str,
    ) -> dict:
        post = _post(
            post_id,
            title,
            (
                "<p>スポーツ報知によると、記事の要点を整理した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
            meta={"article_subtype": subtype, "source_published_at": source_published_at},
        )
        record = evaluator.extractor.extract_post_record(post)
        return evaluator.freshness_check(post, record, now=FIXED_NOW)

    def test_flag_off_manager_48h_boundary_stays_fresh(self):
        with patch.dict(os.environ, {STRICT_FLAG: "0"}, clear=False):
            freshness = self._freshness_entry(
                7001,
                subtype="manager",
                source_published_at="2026-04-24T08:00:00+09:00",
                title="阿部監督が試合後に打線の意図を説明",
            )

        self.assertEqual(freshness["freshness_class"], "fresh")
        self.assertIsNone(freshness["hard_stop_flag"])

    def test_flag_on_manager_within_24h_stays_fresh(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False):
            self.assertEqual(evaluator._freshness_threshold_hours("manager"), 24.0)
            freshness = self._freshness_entry(
                7002,
                subtype="manager",
                source_published_at="2026-04-25T09:00:00+09:00",
                title="阿部監督が起用意図を説明",
            )

        self.assertEqual(freshness["freshness_class"], "fresh")

    def test_flag_on_manager_25h_is_held_with_stale_source_age(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False), self.assertLogs(
            "guarded_publish_evaluator",
            level="INFO",
        ) as cm:
            freshness = self._freshness_entry(
                7003,
                subtype="manager",
                source_published_at="2026-04-25T07:00:00+09:00",
                title="阿部監督が打線の反応を説明",
            )

        self.assertEqual(freshness["freshness_class"], "stale")
        self.assertEqual(freshness["hard_stop_flag"], "stale_for_breaking_board")
        self.assertIn('"event": "stale_source_age"', "\n".join(cm.output))

    def test_flag_on_manager_48h_incident_shape_is_held(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False):
            freshness = self._freshness_entry(
                7004,
                subtype="manager",
                source_published_at="2026-04-24T07:30:00+09:00",
                title="阿部監督が試合後コメントを整理",
            )

        self.assertEqual(freshness["freshness_class"], "stale")
        self.assertEqual(freshness["hard_stop_flag"], "stale_for_breaking_board")

    def test_flag_on_lineup_within_6h_stays_fresh(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False):
            freshness = self._freshness_entry(
                7005,
                subtype="lineup",
                source_published_at="2026-04-26T03:00:00+09:00",
                title="巨人スタメンが発表された",
            )

        self.assertEqual(freshness["freshness_class"], "fresh")
        self.assertFalse(freshness["backlog_only"])

    def test_flag_on_lineup_7h_is_backlog_only_source_age(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False), self.assertLogs(
            "guarded_publish_evaluator",
            level="INFO",
        ) as cm:
            freshness = self._freshness_entry(
                7006,
                subtype="lineup",
                source_published_at="2026-04-26T01:00:00+09:00",
                title="巨人スタメンが発表された",
            )

        self.assertEqual(freshness["freshness_class"], "expired")
        self.assertTrue(freshness["backlog_only"])
        self.assertIn('"event": "backlog_only_source_age"', "\n".join(cm.output))

    def test_flag_on_manager_exact_24h_boundary_is_out(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False):
            freshness = self._freshness_entry(
                7007,
                subtype="manager",
                source_published_at="2026-04-25T08:00:00+09:00",
                title="阿部監督が前日コメントを整理",
            )

        self.assertEqual(freshness["freshness_class"], "stale")
        self.assertEqual(freshness["hard_stop_flag"], "stale_for_breaking_board")

    def test_flag_on_structured_log_includes_required_fields(self):
        with patch.dict(os.environ, {STRICT_FLAG: "1"}, clear=False), self.assertLogs(
            "guarded_publish_evaluator",
            level="INFO",
        ) as cm:
            self._freshness_entry(
                7008,
                subtype="manager",
                source_published_at="2026-04-25T07:00:00+09:00",
                title="阿部監督がコメントを整理",
            )

        payload_lines = [line for line in cm.output if '"event": "stale_source_age"' in line]
        self.assertTrue(payload_lines)
        payload = json.loads(payload_lines[-1].split("INFO:guarded_publish_evaluator:")[-1])
        self.assertEqual(payload["article_subtype"], "manager")
        self.assertEqual(payload["decision"], "hold")
        self.assertEqual(payload["reason"], "stale_source_age")
        self.assertEqual(payload["freshness_basis"], "source_time")
        self.assertIn("source_published_at", payload)
        self.assertIn("source_age_hours", payload)


if __name__ == "__main__":
    unittest.main()
