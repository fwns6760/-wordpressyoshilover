import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.guarded_publish_readiness_guard import evaluate_guarded_publish_readiness
from src.tools import run_guarded_publish_readiness_check as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T12:30:00+09:00")
JST = ZoneInfo("Asia/Tokyo")


def _row(
    post_id: int,
    ts: str,
    *,
    status: str,
    error: str | None = None,
    hold_reason: str | None = None,
    judgment: str = "yellow",
    cleanup_required: bool = False,
    cleanup_success: bool | None = None,
    publishable: bool = True,
) -> dict:
    return {
        "post_id": post_id,
        "ts": ts,
        "status": status,
        "backup_path": None,
        "error": error,
        "judgment": judgment,
        "publishable": publishable,
        "cleanup_required": cleanup_required,
        "cleanup_success": cleanup_success,
        "hold_reason": hold_reason,
    }


class GuardedPublishReadinessGuardTests(unittest.TestCase):
    def _write_history(self, rows: list[dict]) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "history.jsonl"
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        return path

    def test_healthy_ramp_returns_status_ok(self):
        history_path = self._write_history(
            [
                _row(101, "2026-04-26T08:00:00+09:00", status="sent"),
                _row(102, "2026-04-26T08:30:00+09:00", status="sent"),
                _row(103, "2026-04-26T09:00:00+09:00", status="sent"),
                _row(104, "2026-04-26T09:30:00+09:00", status="refused", error="hard_stop:ranking_list_only", hold_reason="hard_stop_ranking_list_only", judgment="hard_stop", publishable=False),
            ]
        )

        report = evaluate_guarded_publish_readiness(history_path, now=FIXED_NOW)

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["metrics"]["sent_count"], 3)
        self.assertEqual(report["metrics"]["refused_count"], 1)
        self.assertEqual(report["metrics"]["sent_refused_ratio"], 3.0)
        self.assertEqual(report["warnings"], [])

    def test_high_refuse_ratio_returns_regression(self):
        history_path = self._write_history(
            [
                _row(201, "2026-04-26T07:00:00+09:00", status="sent"),
                _row(202, "2026-04-26T07:30:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(203, "2026-04-26T08:00:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(204, "2026-04-26T08:30:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(205, "2026-04-26T09:00:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
            ]
        )

        report = evaluate_guarded_publish_readiness(history_path, now=FIXED_NOW)

        self.assertEqual(report["status"], "regression")
        self.assertLess(report["metrics"]["sent_refused_ratio"], 0.3)
        self.assertEqual(report["warnings"][0]["code"], "high_refuse_ratio")

    def test_consecutive_cleanup_failed_warning(self):
        history_path = self._write_history(
            [
                _row(300, "2026-04-26T05:40:00+09:00", status="sent"),
                _row(306, "2026-04-26T05:50:00+09:00", status="sent"),
                _row(301, "2026-04-26T06:00:00+09:00", status="refused", hold_reason="cleanup_failed_post_condition", error="subtype_unresolved_no_resolution", cleanup_required=True, cleanup_success=False),
                _row(302, "2026-04-26T06:10:00+09:00", status="refused", hold_reason="cleanup_failed_post_condition", error="subtype_unresolved_no_resolution", cleanup_required=True, cleanup_success=False),
                _row(303, "2026-04-26T06:20:00+09:00", status="refused", hold_reason="cleanup_failed_post_condition", error="subtype_unresolved_no_resolution", cleanup_required=True, cleanup_success=False),
                _row(304, "2026-04-26T06:30:00+09:00", status="refused", hold_reason="cleanup_failed_post_condition", error="subtype_unresolved_no_resolution", cleanup_required=True, cleanup_success=False),
                _row(305, "2026-04-26T06:40:00+09:00", status="refused", hold_reason="cleanup_failed_post_condition", error="subtype_unresolved_no_resolution", cleanup_required=True, cleanup_success=False),
            ]
        )

        report = evaluate_guarded_publish_readiness(history_path, now=FIXED_NOW)

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["metrics"]["cleanup_failed_post_condition_max_streak"], 5)
        self.assertIn("cleanup_failed_post_condition_streak", [item["code"] for item in report["warnings"]])

    def test_flag_imbalance_warning(self):
        history_path = self._write_history(
            [
                _row(400, "2026-04-26T04:40:00+09:00", status="sent"),
                _row(406, "2026-04-26T04:50:00+09:00", status="sent"),
                _row(401, "2026-04-26T05:00:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(402, "2026-04-26T05:05:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(403, "2026-04-26T05:10:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(404, "2026-04-26T05:15:00+09:00", status="refused", error="hard_stop:injury_death", hold_reason="hard_stop_injury_death", judgment="hard_stop", publishable=False),
                _row(405, "2026-04-26T05:20:00+09:00", status="refused", error="hard_stop:ranking_list_only", hold_reason="hard_stop_ranking_list_only", judgment="hard_stop", publishable=False),
            ]
        )

        report = evaluate_guarded_publish_readiness(history_path, now=FIXED_NOW)

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["metrics"]["hard_stop_dominant_flag"], "injury_death")
        self.assertGreaterEqual(report["metrics"]["hard_stop_dominant_share"], 0.8)
        self.assertIn("hard_stop_flag_imbalance", [item["code"] for item in report["warnings"]])

    def test_daily_cap_exhausted_visible(self):
        rows = [
            _row(500 + index, "2026-04-26T01:00:00+09:00", status="sent")
            for index in range(100)
        ]
        rows.append(
            _row(
                650,
                "2026-04-26T11:00:00+09:00",
                status="skipped",
                error="daily_cap",
                hold_reason="daily_cap",
                judgment="hard_stop",
                publishable=False,
            )
        )
        history_path = self._write_history(rows)

        report = evaluate_guarded_publish_readiness(history_path, now=FIXED_NOW)

        self.assertTrue(report["metrics"]["daily_cap"]["exhausted"])
        self.assertTrue(report["metrics"]["daily_cap"]["reset_pending"])
        self.assertEqual(report["metrics"]["daily_cap"]["today_sent_count"], 100)
        self.assertEqual(report["metrics"]["daily_cap"]["window_daily_cap_skip_count"], 1)

    def test_human_format_renders_summary(self):
        now = datetime.now(JST)
        history_path = self._write_history(
            [
                _row(701, (now - timedelta(hours=2)).isoformat(), status="sent"),
                _row(
                    702,
                    (now - timedelta(hours=1)).isoformat(),
                    status="refused",
                    error="hard_stop:injury_death",
                    hold_reason="hard_stop_injury_death",
                    judgment="hard_stop",
                    publishable=False,
                ),
            ]
        )
        stdout = io.StringIO()

        with patch("sys.stdout", stdout):
            exit_code = cli.main(["--history-path", str(history_path), "--format", "human"])

        rendered = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Guarded Publish Readiness Guard", rendered)
        self.assertIn("summary: sent=1 refused=1 skipped=0", rendered)
        self.assertIn("Warnings", rendered)
