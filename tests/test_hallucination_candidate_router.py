import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src import hallucination_candidate_router as router
from src.tools import run_hallucination_candidate_router as runner


JST = ZoneInfo("Asia/Tokyo")
FIXED_NOW = datetime(2026, 4, 27, 12, 0, tzinfo=JST)


class HallucinationCandidateRouterTests(unittest.TestCase):
    def _history_row(self, post_id, ts, **overrides):
        row = {
            "post_id": post_id,
            "ts": ts,
            "status": "refused",
            "backup_path": None,
            "error": None,
            "judgment": "yellow",
            "publishable": False,
            "cleanup_required": False,
            "cleanup_success": False,
            "hold_reason": None,
        }
        row.update(overrides)
        return row

    def _yellow_row(self, post_id, ts, **overrides):
        row = {
            "post_id": post_id,
            "ts": ts,
            "title": f"post-{post_id}",
            "applied_flags": [],
            "yellow_reasons": [],
            "publish_link": f"https://yoshilover.com/{post_id}",
        }
        row.update(overrides)
        return row

    def _write_jsonl(self, path, rows):
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        Path(path).write_text(payload, encoding="utf-8")

    def _build_report(self, history_rows=None, yellow_rows=None, priorities=None):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_path = Path(tmpdir) / "yellow.jsonl"
            self._write_jsonl(history_path, history_rows or [])
            self._write_jsonl(yellow_path, yellow_rows or [])
            return router.build_hallucination_candidate_report(
                history_path=history_path,
                yellow_log_path=yellow_path,
                priorities=priorities,
                now=FIXED_NOW,
            )

    def test_high_priority_for_injury_keyword(self):
        report = self._build_report(
            yellow_rows=[
                self._yellow_row(
                    63809,
                    "2026-04-27T09:00:00+09:00",
                    title="巨人投手が登録抹消 診断結果と復帰時期を確認へ",
                )
            ]
        )

        self.assertEqual(report["total_candidates"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "high")
        self.assertIn("medical_roster_keyword", candidate["risk_reason"])

    def test_high_priority_for_title_body_mismatch(self):
        report = self._build_report(
            yellow_rows=[
                self._yellow_row(
                    63810,
                    "2026-04-27T09:10:00+09:00",
                    title="巨人が接戦を制した",
                    applied_flags=["title_body_mismatch_partial"],
                    yellow_reasons=["title_body_mismatch_partial"],
                )
            ]
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "high")
        self.assertIn("title_body_mismatch", candidate["risk_reason"])

    def test_high_priority_for_dangerous_hard_stop(self):
        report = self._build_report(
            history_rows=[
                self._history_row(
                    63811,
                    "2026-04-27T09:20:00+09:00",
                    title="unsupported fact",
                    judgment="hard_stop",
                    error="hard_stop:unsupported_named_fact",
                    hold_reason="hard_stop_unsupported_named_fact",
                )
            ]
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "high")
        self.assertIn("hard_stop:unsupported_named_fact", candidate["risk_reason"])

    def test_medium_priority_for_source_missing(self):
        report = self._build_report(
            yellow_rows=[
                self._yellow_row(
                    63812,
                    "2026-04-27T09:30:00+09:00",
                    applied_flags=["weak_source_display"],
                    yellow_reasons=["missing_primary_source"],
                )
            ]
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "medium")
        self.assertIn("source_missing_or_weak", candidate["risk_reason"])

    def test_medium_priority_for_subtype_unresolved(self):
        report = self._build_report(
            history_rows=[
                self._history_row(
                    63813,
                    "2026-04-27T09:40:00+09:00",
                    error="subtype_unresolved_no_resolution",
                    hold_reason="cleanup_failed_post_condition",
                    cleanup_required=True,
                    cleanup_success=False,
                )
            ],
            yellow_rows=[
                self._yellow_row(
                    63813,
                    "2026-04-27T09:39:00+09:00",
                    applied_flags=["subtype_unresolved"],
                    yellow_reasons=["subtype_unresolved"],
                )
            ],
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "medium")
        self.assertIn("subtype_unresolved_cleanup_failed", candidate["risk_reason"])

    def test_low_priority_for_single_warning(self):
        report = self._build_report(
            yellow_rows=[
                self._yellow_row(
                    63814,
                    "2026-04-27T09:50:00+09:00",
                    applied_flags=["light_structure_break"],
                    yellow_reasons=["light_structure_break"],
                )
            ]
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["priority"], "low")
        self.assertEqual(candidate["risk_reason"], ["light_structure_break"])

    def test_excludes_already_resolved_articles(self):
        report = self._build_report(
            history_rows=[
                self._history_row(
                    63815,
                    "2026-04-27T08:00:00+09:00",
                    judgment="hard_stop",
                    error="hard_stop:unsupported_named_fact",
                    hold_reason="hard_stop_unsupported_named_fact",
                ),
                self._history_row(
                    63815,
                    "2026-04-27T10:00:00+09:00",
                    status="sent",
                    judgment="yellow",
                    error=None,
                    cleanup_success=None,
                ),
            ],
            yellow_rows=[
                self._yellow_row(
                    63815,
                    "2026-04-27T08:05:00+09:00",
                    applied_flags=["weak_source_display"],
                    yellow_reasons=["missing_primary_source"],
                )
            ],
        )

        self.assertEqual(report["total_input"], 1)
        self.assertEqual(report["total_candidates"], 0)
        self.assertEqual(report["candidates"], [])

    def test_dry_run_no_gemini_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.jsonl"
            yellow_path = Path(tmpdir) / "yellow.jsonl"
            self._write_jsonl(history_path, [])
            self._write_jsonl(
                yellow_path,
                [
                    self._yellow_row(
                        63816,
                        "2026-04-27T10:10:00+09:00",
                        applied_flags=["light_structure_break"],
                        yellow_reasons=["light_structure_break"],
                    )
                ],
            )
            stdout = io.StringIO()
            with patch("src.pre_publish_fact_check.llm_adapter_gemini.GeminiFlashAdapter.detect") as detect:
                with redirect_stdout(stdout):
                    exit_code = runner.main(
                        [
                            "--history",
                            str(history_path),
                            "--yellow-log",
                            str(yellow_path),
                            "--dry-run",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        detect.assert_not_called()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["total_candidates"], 1)

    def test_output_json_schema(self):
        report = self._build_report(
            yellow_rows=[
                self._yellow_row(
                    63817,
                    "2026-04-27T10:20:00+09:00",
                    title="巨人が競り勝った",
                    applied_flags=["weak_source_display"],
                    yellow_reasons=["missing_primary_source"],
                )
            ]
        )

        candidate = report["candidates"][0]
        self.assertEqual(
            set(candidate),
            {
                "post_id",
                "title",
                "url",
                "subtype",
                "risk_reason",
                "priority",
                "source",
                "next_action",
                "recommended_next_action",
            },
        )

    def test_priority_counts_aggregation(self):
        report = self._build_report(
            history_rows=[
                self._history_row(
                    63818,
                    "2026-04-27T10:30:00+09:00",
                    judgment="hard_stop",
                    error="hard_stop:unsupported_named_fact",
                    hold_reason="hard_stop_unsupported_named_fact",
                )
            ],
            yellow_rows=[
                self._yellow_row(
                    63819,
                    "2026-04-27T10:31:00+09:00",
                    applied_flags=["weak_source_display"],
                    yellow_reasons=["missing_primary_source"],
                ),
                self._yellow_row(
                    63820,
                    "2026-04-27T10:32:00+09:00",
                    applied_flags=["light_structure_break"],
                    yellow_reasons=["light_structure_break"],
                ),
            ],
        )

        self.assertEqual(report["priority_counts"], {"high": 1, "medium": 1, "low": 1})


if __name__ == "__main__":
    unittest.main()
